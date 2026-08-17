"""Offline index build — never runs in the request path.

    python -m echorag.index --lang hin --rows 25000
"""

import argparse
import collections
import re
import time

from echorag import embed
from echorag.schemas import Chunk, Passage

REPO = "ai4bharat/MSMARCO-XI"

# No per-language config exists — only per-language parquet files (AUDIT §5.0).
SHARD = {"train": "train/{lang}train.parquet", "validation": "validation/{lang}val.parquet"}

_LEADING_JUNK = re.compile(r"^[\s.,;:!?\-–—]+")
# Devanagari ends sentences with danda (।), not a period. Omitting it meant
# Hindi passages never split — one giant "sentence", slower to embed and useless
# as an extractive answer.
_SENTENCE_END = re.compile(r"(?<=[.!?।॥])\s*")


def normalize_query(text: str) -> str:
    """Strip leading punctuation. Real rows look like '. what is a corporation?'"""
    return _LEADING_JUNK.sub("", text).strip()


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def load_passages(lang: str = "hin", split: str = "validation", rows: int | None = None):
    """Stream one language shard, flattened to one Passage per passage."""
    # Imported here, not at module scope: answer.py pulls split_sentences out of
    # this module on the serving path, and a top-level import would drag
    # datasets (pyarrow, pandas, fsspec, multiprocess) into every server
    # process to support a regex. Index building is the only caller.
    from datasets import load_dataset

    ds = load_dataset(REPO, data_files=SHARD[split].format(lang=lang), split="train", streaming=True)

    for i, row in enumerate(ds):
        if rows is not None and i >= rows:
            break

        p = row["passages"]
        query_en = normalize_query(row["Eng_Query"])

        for rank, (en, translated, selected) in enumerate(
            zip(p["English_passages"], p["Translated_passages"], p["is_selected"])
        ):
            if not en or not en.strip():
                continue
            yield Passage(
                passage_id=f"{row['query_id']}:{rank}",
                query_id=row["query_id"],
                text_en=en.strip(),
                text_translated=(translated or "").strip(),
                query_type=row["query_type"].lower(),
                lang=row["target_lang"],
                is_gold=bool(selected),
                query=row["query"],
                query_en=query_en,
            )


# --- chunkers (AUDIT §5.1) -------------------------------------------------


def sentence_window(passage: Passage, window: int = 1) -> list[Chunk]:
    """V3 — embed sentence+neighbours, return the parent passage (small-to-big)."""
    sentences = split_sentences(passage.text_en)
    chunks = []

    for i in range(len(sentences)):
        # Clamped so i-window can't go negative and wrap to the end of the list.
        start = max(0, i - window)
        end = min(len(sentences), i + window + 1)

        chunks.append(
            Chunk(
                chunk_id=f"{passage.passage_id}:v3:{i}",
                parent_id=passage.passage_id,
                text=" ".join(sentences[start:end]),
                view="v3",
            )
        )

    return chunks


def whole_passage(passage: Passage) -> list[Chunk]:
    """V1 + V2 — the passage as one chunk per language."""
    chunks = [
        Chunk(
            chunk_id=f"{passage.passage_id}:v1",
            parent_id=passage.passage_id,
            text=passage.text_en,
            view="v1",
        )
    ]

    # Empty translations exist. Embedding "" burns an index slot and matches nothing.
    if passage.text_translated:
        chunks.append(
            Chunk(
                chunk_id=f"{passage.passage_id}:v2",
                parent_id=passage.passage_id,
                text=passage.text_translated,
                view="v2",
            )
        )

    return chunks


def chunks_for(passage: Passage) -> list[Chunk]:
    # sentence_window (V3) is deliberately not called — the ablation measured it
    # as negative on recall, MRR and latency (AUDIT §5.2). Kept in the codebase
    # because the ablation still needs to be reproducible.
    return whole_passage(passage)


# --- index build -----------------------------------------------------------

INDEX_DIR = "index"


def build(lang: str = "hin", split: str = "validation", rows: int = 200, out: str = INDEX_DIR):
    """Write two LanceDB tables: `chunks` (searched) and `passages` (returned).

    Kept separate rather than denormalizing the parent text onto every chunk —
    each passage produces ~5 chunks, so inlining it would duplicate the corpus
    5x on disk and slow every scan. Retrieval narrows to <=5 parents first, so
    the join is one small batched lookup (AUDIT §6).
    """
    import lancedb

    db = lancedb.connect(out)
    chunk_rows, passage_rows = [], []
    n_chunks = 0
    started = time.monotonic()

    def flush():
        nonlocal chunk_rows, passage_rows, n_chunks
        if not chunk_rows:
            return
        vectors = embed.encode([r["text"] for r in chunk_rows], is_query=False)
        for row, vec in zip(chunk_rows, vectors):
            row["vector"] = vec.tolist()

        # .tables — list_tables() returns a response object, not a list.
        existing = set(db.list_tables().tables)
        for name, data in (("chunks", chunk_rows), ("passages", passage_rows)):
            if name in existing:
                db.open_table(name).add(data)
            else:
                db.create_table(name, data=data)

        n_chunks += len(chunk_rows)
        print(f"  {n_chunks:>7} chunks  ({time.monotonic() - started:.0f}s)")
        chunk_rows, passage_rows = [], []

    for p in load_passages(lang, split, rows):
        passage_rows.append(p.model_dump())
        for c in chunks_for(p):
            chunk_rows.append(
                {
                    **c.model_dump(),
                    # V6 metadata, denormalized so type/language filtering needs
                    # no parent lookup.
                    "query_type": p.query_type,
                    "lang": p.lang,
                }
            )
        if len(chunk_rows) >= 2000:
            flush()

    flush()

    from lancedb.index import FTS, IvfFlat

    chunks = db.open_table("chunks")

    # V5 — lexical index. Dense retrieval is weak on exact tokens (names, model
    # numbers, dates); BM25 covers that gap.
    chunks.create_index("text", config=FTS(), replace=True)

    # Without this LanceDB brute-force scans every vector on every query.
    # IvfFlat clusters vectors into partitions and searches only the nearest
    # few — approximate, but orders of magnitude faster. Flat (not PQ) keeps
    # the full vectors, so the only recall loss is from partition pruning.
    chunks.create_index("vector", config=IvfFlat(distance_type="cosine"), replace=True)

    return db


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="hin", help="shard prefix: hin, tam, ben, asm, ...")
    ap.add_argument("--split", default="validation", choices=list(SHARD))
    ap.add_argument("--rows", type=int, default=200, help="dataset rows (x10 passages)")
    ap.add_argument("--out", default=INDEX_DIR)
    ap.add_argument("--stats", action="store_true", help="inspect the shard, don't build")
    args = ap.parse_args()

    if args.stats:
        passages = list(load_passages(args.lang, args.split, args.rows))
        golds = sum(p.is_gold for p in passages)
        lengths = sorted(len(p.text_en.split()) for p in passages)
        print(f"passages      : {len(passages)}")
        print(f"gold          : {golds}  ({golds / max(len(passages), 1):.1%})")
        print(f"words/passage : min {lengths[0]}  p50 {lengths[len(lengths) // 2]}  max {lengths[-1]}")
        print(f"query_types   : {sorted({p.query_type for p in passages})}")
        raise SystemExit

    print(f"building {args.lang}/{args.split}, {args.rows} rows -> {args.out}/")
    db = build(args.lang, args.split, args.rows, args.out)

    chunks, passages = db.open_table("chunks"), db.open_table("passages")
    print(f"\npassages : {passages.count_rows()}")
    print(f"chunks   : {chunks.count_rows()}")
    by_view = collections.Counter(r["view"] for r in chunks.search().limit(10**9).to_list())
    for view, n in sorted(by_view.items()):
        print(f"  {view} : {n}")
