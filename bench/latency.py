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


def pct(xs: list[float]) -> dict[str, float]:
    xs = sorted(xs)
    return {
        "p50": xs[len(xs) // 2],
        "p70": xs[min(int(len(xs) * 0.70), len(xs) - 1)],
        "p100": xs[-1],
    }


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
    for lang in ("en", "hi", None):
        subset = [r for r in runs if lang is None or r["lang"] == lang]
        if not subset:
            continue
        label = {"en": "English", "hi": "Hindi", None: "ALL"}[lang]
        print(f"--- {label}  (n={len(subset)}) ---")
        print(f"{'stage':<12}{'P50':>9}{'P70':>9}{'P100':>9}")
        for s in stages:
            vals = [r["spans"][s] for r in subset if s in r["spans"]]
            if not vals:
                continue
            p = pct(vals)
            mark = "  <-- SLO" if s == "total" else ""
            print(f"{s:<12}{p['p50']:>8.1f}{p['p70']:>8.1f}{p['p100']:>8.1f}{mark}")

        over = sum(1 for r in subset if r["spans"].get("total", 0) > BUDGET_MS)
        print(f"over budget : {over}/{len(subset)}  ({over / len(subset):.1%})")
        print(f"mean total  : {statistics.mean(r['spans']['total'] for r in subset):.1f} ms\n")

    kinds = collections.Counter(r["kind"] for r in runs)
    print("outcomes:", dict(kinds))


if __name__ == "__main__":
    asyncio.run(main())
