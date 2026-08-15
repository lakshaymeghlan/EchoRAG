"""Phase 2 exit criterion — does each view earn its latency? (AUDIT §5.1)

    python -m bench.ablation
    python -m bench.ablation --queries 300 --lang en

Ground truth is `is_gold` from the dataset. It is used ONLY to score results —
never as a retrieval input, which would be leakage.
"""

import argparse
import collections
import random
import statistics

import lancedb

from echorag.retrieve import retrieve

K = 10

# (label, dense views, use_bm25)
COMBOS = [
    ("V1 only (passage-dense EN)", ("v1",), False),
    ("V1+V5 (+BM25)", ("v1",), True),
    ("V1+V3+V5 (+sentence-window)", ("v1", "v3"), True),
    ("V1+V2 (+translated, no BM25)", ("v1", "v2"), False),
    ("V1+V2+V5 (no sentence-window)", ("v1", "v2"), True),
    ("all views", ("v1", "v2", "v3"), True),
]


def build_eval_set(index_dir: str, n: int, lang: str) -> list[tuple[str, set[str]]]:
    """(query_text, {gold passage_ids}) pairs.

    Grouped by query_id because a query can have more than one gold passage —
    scoring each separately would punish a retriever that found a different
    correct one.
    """
    passages = lancedb.connect(index_dir).open_table("passages")
    rows = passages.search().limit(10**9).to_list()

    gold: dict[int, set[str]] = collections.defaultdict(set)
    text: dict[int, str] = {}
    for r in rows:
        if r["is_gold"]:
            gold[r["query_id"]].add(r["passage_id"])
            text[r["query_id"]] = r["query_en"] if lang == "en" else r["query"]

    pairs = [(text[qid], ids) for qid, ids in gold.items() if text.get(qid)]
    random.Random(42).shuffle(pairs)  # seeded so runs are comparable
    return pairs[:n]


def score(pairs, views, use_bm25):
    # Warm-up, discarded (AUDIT §10). The first call pays model load and a cold
    # page cache; leaving it in makes P100 a measure of startup, not of search.
    for query, _ in pairs[:3]:
        retrieve(query, k=K, views=views, use_bm25=use_bm25, per_view=20)

    hits, rr, latencies = 0, [], []
    for query, gold_ids in pairs:
        results, spans = retrieve(query, k=K, views=views, use_bm25=use_bm25, per_view=20)
        latencies.append(spans["total"])

        ranks = [i for i, e in enumerate(results, 1) if e.passage_id in gold_ids]
        if ranks:
            hits += 1
            rr.append(1.0 / ranks[0])
        else:
            rr.append(0.0)

    return {
        "recall": hits / len(pairs),
        "mrr": statistics.mean(rr),
        "p50_ms": statistics.median(latencies),
        "p100_ms": max(latencies),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--lang", default="hi", choices=["hi", "en"], help="query language")
    ap.add_argument("--index", default="index")
    args = ap.parse_args()

    pairs = build_eval_set(args.index, args.queries, args.lang)
    print(f"eval set : {len(pairs)} queries ({args.lang}), gold from is_selected")
    print(f"metric   : recall@{K} = gold found in top {K}; MRR = 1/rank of first gold\n")

    print(f"{'combination':<32} {'recall@10':>10} {'MRR@10':>8} {'P50':>8} {'P100':>8}")
    print("-" * 70)
    for label, views, bm25 in COMBOS:
        s = score(pairs, views, bm25)
        print(
            f"{label:<32} {s['recall']:>10.3f} {s['mrr']:>8.3f} "
            f"{s['p50_ms']:>7.1f}ms {s['p100_ms']:>7.1f}ms"
        )


if __name__ == "__main__":
    main()
