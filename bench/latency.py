"""T_pipeline latency — the SLO number (AUDIT §2.1, §10).

    python -m bench.latency --queries 300

Measures transcript -> answer. STT is excluded by design and reported
separately; it is a network call to a third party and cannot fit 200 ms.
Reports per language, because Hindi and English have different cost profiles.
"""

import argparse
import asyncio
import collections
import json
import random
import statistics

import lancedb

from echorag.answer import answer_question

WARMUP = 20
BUDGET_MS = 200.0


def load_queries(index_dir: str, n: int) -> list[tuple[str, str]]:
    """(query, lang) sampled from the validation split, stratified by query_type."""
    rows = lancedb.connect(index_dir).open_table("passages").search().limit(10**9).to_list()

    by_type: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    seen = set()
    for r in rows:
        if r["query_id"] in seen or not r["is_gold"]:
            continue
        seen.add(r["query_id"])
        by_type[r["query_type"]].append((r["query"], "hi"))
        by_type[r["query_type"]].append((r["query_en"], "en"))

    rng = random.Random(42)
    per_type = max(1, n // max(len(by_type), 1))
    out: list[tuple[str, str]] = []
    for qs in by_type.values():
        rng.shuffle(qs)
        out.extend(qs[:per_type])
    rng.shuffle(out)
    return out[:n]


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile.

    Nearest-index picking is off by up to one whole sample, which matters at
    p95/p99 where few samples sit above the mark.
    """
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (q / 100)
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (k - lo) * (xs[hi] - xs[lo])


PCTS = [("avg", None), ("p50", 50), ("p70", 70), ("p95", 95), ("p99", 99), ("p100", 100)]


def row(name: str, values: list[float]) -> str:
    cells = "".join(
        f"{statistics.mean(values):>9.1f}" if q is None else f"{percentile(values, q):>9.1f}"
        for _, q in PCTS
    )
    return f"{name:<12}{cells}"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=int, default=300)
    ap.add_argument("--index", default="index")
    ap.add_argument("--out", default="bench/runs.jsonl")
    args = ap.parse_args()

    queries = load_queries(args.index, args.queries)

    for q, _ in queries[:WARMUP]:
        await answer_question(q)

    runs = []
    for q, lang in queries:
        r = await answer_question(q)
        runs.append({"lang": lang, "kind": type(r).__name__, "spans": r.spans})

    with open(args.out, "w") as f:
        for r in runs:
            f.write(json.dumps(r) + "\n")

    print(f"queries : {len(runs)}  (after {WARMUP} warm-up, discarded)")
    print(f"budget  : {BUDGET_MS:.0f} ms\n")

    stages = ["embed", "retrieve", "extract", "total"]
    header = f"{'stage':<12}" + "".join(f"{name:>9}" for name, _ in PCTS) + "   (ms)"

    for lang in ("en", "hi", None):
        subset = [r for r in runs if lang is None or r["lang"] == lang]
        if not subset:
            continue
        label = {"en": "English", "hi": "Hindi", None: "ALL"}[lang]
        print(f"--- {label}  (n={len(subset)}) ---")
        print(header)
        for s in stages:
            vals = [r["spans"][s] for r in subset if s in r["spans"]]
            if vals:
                print(row(s, vals) + ("   <-- SLO" if s == "total" else ""))

        over = sum(1 for r in subset if r["spans"].get("total", 0) > BUDGET_MS)
        print(f"over budget : {over}/{len(subset)}  ({over / len(subset):.1%})\n")

    print("outcomes:", dict(collections.Counter(r["kind"] for r in runs)))

    # Exit non-zero on a miss so this can gate a deploy instead of being a
    # number someone reads and shrugs at.
    totals = [r["spans"]["total"] for r in runs]
    worst, over = max(totals), sum(1 for t in totals if t > BUDGET_MS)
    print(f"\nbudget {BUDGET_MS:.0f} ms | p100 {worst:.1f} ms | p99 {percentile(totals, 99):.1f} ms")
    if over:
        print(f"FAIL: {over}/{len(totals)} over budget")
        raise SystemExit(1)
    print(f"PASS: {len(totals)}/{len(totals)} within budget")


if __name__ == "__main__":
    asyncio.run(main())
