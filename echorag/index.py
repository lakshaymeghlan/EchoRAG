"""Offline index build. Never runs in the request path (AUDIT.md §2.1).

Phase 1 step 2 — load + flatten. Chunkers (V3/V4) land in step 3.

    python -m echorag.index --lang hin --rows 25000
"""

import argparse
import re

from datasets import load_dataset

from echorag.schemas import Passage

REPO = "ai4bharat/MSMARCO-XI"

# The dataset has no per-language config — only per-language parquet files
# (AUDIT.md §5.0). Point data_files straight at the shard.
SHARD = {"train": "train/{lang}train.parquet", "validation": "validation/{lang}val.parquet"}

_LEADING_JUNK = re.compile(r"^[\s.,;:!?\-–—]+")


def normalize_query(text: str) -> str:
    """Strip the leading-punctuation garbage seen in Eng_Query (AUDIT.md §5.0).

    Observed in real rows: '. what is a corporation?'
    """
    return _LEADING_JUNK.sub("", text).strip()


def load_passages(lang: str = "hin", split: str = "validation", rows: int | None = None):
    """Stream one language shard and flatten it into Passage records.

    Each row holds 10 parallel passages, so `rows=25_000` yields ~250k passages
    (AUDIT.md D6).
    """
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
                continue  # empty passages exist; indexing them wastes a slot
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="hin", help="shard prefix: hin, tam, ben, asm, ...")
    ap.add_argument("--split", default="validation", choices=list(SHARD))
    ap.add_argument("--rows", type=int, default=200, help="dataset rows (x10 passages)")
    args = ap.parse_args()

    passages = list(load_passages(args.lang, args.split, args.rows))

    golds = sum(p.is_gold for p in passages)
    lengths = sorted(len(p.text_en.split()) for p in passages)

    print(f"rows requested : {args.rows}")
    print(f"passages       : {len(passages)}")
    print(f"gold passages  : {golds}  ({golds / max(len(passages), 1):.1%})")
    print(f"words/passage  : min {lengths[0]}  p50 {lengths[len(lengths) // 2]}  max {lengths[-1]}")
    print(f"query_types    : {sorted({p.query_type for p in passages})}")
    print()
    print("--- sample ---")
    s = next(p for p in passages if p.is_gold)
    print(f"query    : {s.query}")
    print(f"query_en : {s.query_en}")
    print(f"passage  : {s.text_en[:160]}...")
