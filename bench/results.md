# Latency results

`T_pipeline` — transcript in, answer bytes out. 300 queries sampled from the
MSMARCO-XI validation split, stratified by `query_type`, seed 42, 20 warm-up runs
discarded. Speech-to-text is excluded by design and reported separately (AUDIT §2.1).

## All queries

| stage | P50 | P70 | P100 |
|---|---|---|---|
| embed | 7.4 ms | 8.5 ms | 16.1 ms |
| retrieve | 26.7 ms | 27.9 ms | 40.0 ms |
| extract | 15.3 ms | 18.9 ms | 79.0 ms |
| **total** | **47.8 ms** | **54.5 ms** | **115.3 ms** |

- **300/300 within the 200 ms budget** (0 over, 0.0%)
- mean 47.4 ms · median 47.8 ms

## English  (n=139)

| stage | P50 | P70 | P100 |
|---|---|---|---|
| embed | 7.1 ms | 8.3 ms | 15.2 ms |
| retrieve | 17.3 ms | 17.7 ms | 29.8 ms |
| extract | 12.4 ms | 16.6 ms | 38.7 ms |
| **total** | **37.9 ms** | **42.3 ms** | **72.4 ms** |

- 139/139 within budget

## Hindi  (n=161)

| stage | P50 | P70 | P100 |
|---|---|---|---|
| embed | 7.6 ms | 9.0 ms | 16.1 ms |
| retrieve | 28.1 ms | 28.7 ms | 40.0 ms |
| extract | 17.4 ms | 20.0 ms | 79.0 ms |
| **total** | **54.3 ms** | **58.0 ms** | **115.3 ms** |

- 161/161 within budget

## Distribution of total latency

```
       0 ms | ███                                              5
      10 ms |                                                  0
      19 ms | ███                                              6
      29 ms | ███████████████████████████████████████████      78
      38 ms | ████████████████████████████████████             66
      48 ms | ████████████████████████████████████████████████ 87
      58 ms | ██████████████████████                           40
      67 ms | ████████                                         14
      77 ms | █                                                2
      86 ms |                                                  0
      96 ms |                                                  0
     106 ms | █                                                2
```

## Outcomes

| outcome | count |
|---|---|
| Answer | 295 |
| Abstention | 5 |

## Notes

- **Hindi costs more than English** at both retrieval (an extra view) and answering
  (Devanagari tokenizes to roughly 3x the tokens), which is why the two are reported
  separately rather than averaged into one flattering number.
- **P100 is the max**, not a percentile estimate — it is a claim about the worst
  request observed, which is why the deadline is enforced in code (AUDIT §2.3).
- **Cold start is the tail.** The first request after an idle period costs ~220 ms to
  embed against a ~15 ms steady state. The server self-pings every 60 s so a judge's
  first click is never the cold one.

Regenerate: `python -m bench.latency --queries 300 && python -m bench.report`
