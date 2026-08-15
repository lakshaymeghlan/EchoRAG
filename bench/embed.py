"""Phase 1 exit criterion — query embedding latency.

    python -m bench.embed

Measures batch-of-1 encoding, because that is what the request path does. Batch
throughput is irrelevant here: the SLO is about one user waiting.
"""

import time

from echorag import embed

WARMUP = 30  # discarded — first calls pay lazy init and page-cache misses (AUDIT §10)
RUNS = 300

QUERIES = [
    "what is a corporation?",
    "how much does a root canal cost",
    "कॉर्पोरेशन क्या है?",
    "who invented the telephone",
    "average rainfall in seattle in november",
    "बिजली का बिल कैसे कम करें",
]


def percentiles(xs: list[float]) -> dict[str, float]:
    xs = sorted(xs)
    at = lambda p: xs[min(int(len(xs) * p), len(xs) - 1)]  # noqa: E731
    return {"p50": at(0.50), "p70": at(0.70), "p100": xs[-1]}


def main() -> None:
    for i in range(WARMUP):
        embed.encode([QUERIES[i % len(QUERIES)]], is_query=True)

    timings = []
    for i in range(RUNS):
        q = QUERIES[i % len(QUERIES)]
        t0 = time.perf_counter()
        embed.encode([q], is_query=True)
        timings.append((time.perf_counter() - t0) * 1000)

    p = percentiles(timings)
    print(f"model   : {embed.MODEL_NAME}  (fp32, sentence-transformers)")
    print(f"runs    : {RUNS}  (after {WARMUP} warm-up, discarded)")
    print()
    print(f"  P50   : {p['p50']:6.1f} ms")
    print(f"  P70   : {p['p70']:6.1f} ms")
    print(f"  P100  : {p['p100']:6.1f} ms")
    print()

    budget = 200.0
    print(f"  P100 is {p['p100'] / budget:.0%} of the {budget:.0f} ms pipeline budget")


if __name__ == "__main__":
    main()
