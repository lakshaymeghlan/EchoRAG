"""Multi-view retrieval + RRF fusion (AUDIT §6).

    from echorag.retrieve import retrieve
    retrieve("what is a corporation?")
"""

import collections
import os
import time

import lancedb

from echorag import embed
from echorag.schemas import Evidence

# Same env var scripts/fetch_index.py downloads into — it honoured
# ECHORAG_INDEX_DIR while this was hardcoded, so setting it put the index
# somewhere retrieval never looked.
INDEX_DIR = os.environ.get("ECHORAG_INDEX_DIR", "index")
RRF_K = 60  # flattens the curve so one confident-but-wrong view can't dominate

# Measured, not guessed (AUDIT §5.3). Search ONLY the view matching the query's
# language. Adding the other language's view leaves recall unchanged and drops
# MRR hard (HI 0.529 -> 0.412), because cross-lingual hits crowd the top ranks
# with passages that are merely topical. The cross-lingual capability is real —
# it is what makes one shared index possible — but using it *alongside* the
# native view is worse than using the native view alone.
VIEWS_INDIC = ("v2",)  # Hindi query -> Hindi passages
VIEWS_EN = ("v1",)  # English query -> English passages
DENSE_VIEWS = VIEWS_EN


def views_for(query: str) -> tuple[str, ...]:
    """Route by script: any non-ASCII codepoint means use the translated view."""
    return VIEWS_EN if query.isascii() else VIEWS_INDIC

_db = None


def _tables():
    global _db
    if _db is None:
        _db = lancedb.connect(INDEX_DIR)
    return _db.open_table("chunks"), _db.open_table("passages")


def _dedup_parents(rows: list[dict]) -> list[str]:
    """Collapse a ranked chunk list to a ranked parent list, keeping best rank.

    Without this a passage with 8 sentence-windows would occupy 8 slots in one
    view's ranking and get 8x the RRF weight — long passages would win purely
    for being long.
    """
    seen, out = set(), []
    for r in rows:
        pid = r["parent_id"]
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


def _rrf(rankings: dict[str, list[str]], k: int = RRF_K) -> dict[str, float]:
    scores: dict[str, float] = collections.defaultdict(float)
    for ids in rankings.values():
        for rank, pid in enumerate(ids, start=1):
            scores[pid] += 1.0 / (k + rank)
    return scores


def retrieve(
    query: str,
    k: int = 5,
    views: tuple[str, ...] | None = None,
    use_bm25: bool = True,
    per_view: int = 20,
    qvec=None,
) -> tuple[list[Evidence], dict[str, float]]:
    """Return top-k parent passages plus per-stage timings in ms.

    `views=None` routes by query language. Passing it explicitly is what lets
    bench/ablation.py measure every combination without a second code path.

    `qvec` accepts an already-computed query vector so the answer stage does not
    pay to embed the same query twice.
    """
    if views is None:
        views = views_for(query)
    chunks, passages = _tables()
    spans: dict[str, float] = {}
    t0 = time.perf_counter()

    if qvec is None:
        qvec = embed.encode([query], is_query=True)[0]
    spans["embed"] = (time.perf_counter() - t0) * 1000

    t = time.perf_counter()
    rankings: dict[str, list[str]] = {}
    matched: dict[str, str] = {}
    dense: dict[str, float] = {}

    for view in views:
        # prefilter=True filters before the ANN scan; the default filters after,
        # which silently returns fewer than `limit` rows.
        rows = (
            chunks.search(qvec)
            .where(f"view = '{view}'", prefilter=True)
            .limit(per_view)
            .to_list()
        )
        rankings[view] = _dedup_parents(rows)
        for r in rows:
            matched.setdefault(r["parent_id"], r["text"])
            # distance_type="cosine" means _distance == 1 - cosine.
            cos = 1.0 - float(r.get("_distance", 1.0))
            if cos > dense.get(r["parent_id"], -1.0):
                dense[r["parent_id"]] = cos

    if use_bm25:
        rows = chunks.search(query, query_type="fts").limit(per_view).to_list()
        rankings["bm25"] = _dedup_parents(rows)
        for r in rows:
            matched.setdefault(r["parent_id"], r["text"])

    spans["search"] = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    fused = _rrf(rankings)
    top = sorted(fused, key=fused.get, reverse=True)[:k]
    spans["fuse"] = (time.perf_counter() - t) * 1000

    if not top:
        spans["total"] = (time.perf_counter() - t0) * 1000
        return [], spans

    # One batched lookup for the parents — never per-result (AUDIT §6).
    t = time.perf_counter()
    quoted = ", ".join(f"'{pid}'" for pid in top)
    parents = {
        p["passage_id"]: p
        for p in passages.search().where(f"passage_id IN ({quoted})").limit(len(top)).to_list()
    }
    spans["parents"] = (time.perf_counter() - t) * 1000

    evidence = []
    for pid in top:
        p = parents.get(pid)
        if p is None:
            continue
        evidence.append(
            Evidence(
                passage_id=pid,
                text_en=p["text_en"],
                text_translated=p["text_translated"],
                query_type=p["query_type"],
                score=fused[pid],
                dense_score=dense.get(pid, 0.0),
                views=[v for v, ids in rankings.items() if pid in ids],
                matched_text=matched.get(pid, p["text_en"]),
            )
        )

    spans["total"] = (time.perf_counter() - t0) * 1000
    return evidence, spans


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "what is a corporation?"
    results, spans = retrieve(q)

    print(f"query: {q}\n")
    for i, e in enumerate(results, 1):
        print(f"{i}. [{e.score:.4f}] {'+'.join(e.views):<16} {e.text_en[:88]}")
    print()
    print("  " + "  ".join(f"{k} {v:.1f}ms" for k, v in spans.items()))
