# Latency results

`T_pipeline` — transcript in, answer bytes out. 300 queries sampled from the
MSMARCO-XI validation split, stratified by `query_type`, seed 42, 20 warm-up runs
discarded. Speech-to-text is excluded by design and reported separately (AUDIT §2.1).

## All queries

| stage | P50 | P70 | P95 | P99 | P100 |
|---|---|---|---|---|---|
| embed | 6.9 ms | 7.6 ms | 9.7 ms | 13.1 ms | 15.5 ms |
| retrieve | 16.7 ms | 17.0 ms | 17.9 ms | 19.8 ms | 27.9 ms |
| extract | 11.1 ms | 15.1 ms | 25.7 ms | 32.2 ms | 36.8 ms |
| **total** | **35.1 ms** | **39.1 ms** | **50.9 ms** | **57.7 ms** | **62.6 ms** |

- **300/300 within the 200 ms budget** (0 over, 0.0%)
- mean 36.4 ms · median 35.1 ms

## English  (n=139)

| stage | P50 | P70 | P95 | P99 | P100 |
|---|---|---|---|---|---|
| embed | 6.8 ms | 7.5 ms | 9.8 ms | 13.8 ms | 15.5 ms |
| retrieve | 16.1 ms | 16.3 ms | 17.1 ms | 17.9 ms | 19.6 ms |
| extract | 10.7 ms | 13.7 ms | 24.2 ms | 29.4 ms | 31.9 ms |
| **total** | **33.7 ms** | **36.9 ms** | **50.1 ms** | **56.1 ms** | **57.7 ms** |

- 139/139 within budget

## Hindi  (n=161)

| stage | P50 | P70 | P95 | P99 | P100 |
|---|---|---|---|---|---|
| embed | 7.0 ms | 7.9 ms | 9.7 ms | 11.7 ms | 14.0 ms |
| retrieve | 17.0 ms | 17.3 ms | 18.1 ms | 24.8 ms | 27.9 ms |
| extract | 12.2 ms | 16.8 ms | 26.3 ms | 36.2 ms | 36.8 ms |
| **total** | **36.4 ms** | **41.2 ms** | **51.5 ms** | **59.9 ms** | **62.6 ms** |

- 161/161 within budget

## Distribution of total latency

```
       0 ms | ██                                               5
       5 ms |                                                  0
      10 ms |                                                  0
      16 ms |                                                  0
      21 ms | █████                                            13
      26 ms | █████████                                        26
      31 ms | ████████████████████████████████████████████████ 133
      37 ms | ███████████████████████                          63
      42 ms | ████████████                                     33
      47 ms | ██████                                           17
      52 ms | ██                                               6
      57 ms | █                                                4
```

## Outcomes

| outcome | count |
|---|---|
| Answer | 294 |
| Abstention | 6 |

## Notes

- **Hindi costs more than English** at both retrieval (an extra view) and answering
  (Devanagari tokenizes to roughly 3x the tokens), which is why the two are reported
  separately rather than averaged into one flattering number.
- **P100 is the max**, not a percentile estimate — it is a claim about the worst
  request observed, which is why the deadline is enforced in code (AUDIT §2.3).
- **p95/p99 are interpolated**, not nearest-index — at the tail, picking the nearest
  sample is off by a whole observation.
- **Cold start was the tail.** Torch selects kernels per input shape, so warming one
  short string left longer ones cold: a 290 ms first encode against ~7 ms steady state.
  The server now re-warms a spread of lengths in both scripts every 20 s, which took
  the first request from 399 ms to 90 ms.
- **Benchmark on an idle machine.** Every outlier we chased (85, 131, 321 ms) turned
  out to be CPU contention from a concurrent build, not the pipeline.

Regenerate: `python -m bench.latency --queries 300 && python -m bench.report`
