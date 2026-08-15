# EchoRAG

Voice-enabled RAG over [MSMARCO-XI](https://huggingface.co/datasets/ai4bharat/MSMARCO-XI).
Speak a question in Hindi or English, get a grounded, cited answer — or an honest refusal.

**[AUDIT.md](AUDIT.md) is the design contract.** Read §2 before changing anything. Every
locked decision carries a measured number you can re-check, and several have already been
overturned by measurement.

```
voice ─▶ Sarvam saaras:v3 ─▶ [ guards ─▶ retrieve (RRF) ─▶ answer ─▶ ground ]
                              └───────── T_pipeline P100 116 ms ────────┘
```

## Setup

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[learn]"     # [learn] pulls sentence-transformers (~2GB, includes torch)
cp .env.example .env          # add SARVAM_API_KEY — never put it in .env.example
```

## Run

```sh
uvicorn echorag.api:app --reload
curl -s localhost:8000/health
```

## Build the index

```sh
python -m echorag.index --lang hin --rows 10000        # ~17 min -> index/ (723 MB)
python -m echorag.index --lang hin --rows 200 --stats  # inspect a shard, no build
```

Shards: `hin` `tam` `ben` `mar` `asm` `guj` `kan` `mal` `nep` `ori` `pan` `san` `tel` `urd`.

## Checks and benchmarks

```sh
python test_chunkers.py            # chunkers
python -m echorag.harness          # deadline, circuit breaker, retry
python learn/01_embeddings.py      # regression check for D2 + D7
python -m bench.embed              # query embed latency
python -m bench.ablation           # which views earn their latency
python -m bench.latency            # T_pipeline P50/P70/P100  <- the SLO
python -m bench.guardrails         # off-topic threshold calibration
python -m echorag.stt sample.wav   # live Sarvam call (<=30s, 16kHz mono)
```

## Measured

**T_pipeline** — transcript in, answer out. 200 queries, 20 warm-up discarded.

| | P50 | P70 | P100 |
|---|---|---|---|
| English | 37.7 ms | 42.6 ms | 115.8 ms |
| Hindi | 56.0 ms | 62.5 ms | 77.4 ms |
| **All** | **51.1 ms** | **56.2 ms** | **115.8 ms** |

`0/200 over the 200 ms budget.` STT is excluded by design and reported separately —
measured **513 ms**, which is 2.5x the entire budget and cannot fit inside it (AUDIT §2.1).

**Retrieval quality** — 150 gold-labelled queries per language.

| Query | Views | recall@10 | MRR@10 |
|---|---|---|---|
| Hindi | V1 + V2 + BM25 | 0.767 | 0.448 |
| English | V1 + BM25 | 0.973 | 0.595 |

**Corpus** — 99,985 passages / 199,970 chunks / 723 MB, from 10k Hindi rows.

Numbers are from an M-series laptop. The deploy host will be slower — AUDIT §15 requires
re-measuring there.

## Status

| Phase | | |
|---|---|---|
| 0 | Skeleton, health, Sarvam verified live | ✅ |
| 1 | Ingest + index | ✅ |
| 2 | Retrieval + RRF fusion + ablation | ✅ |
| 3 | Answering + harness | ✅ |
| 4 | Guardrails | ⚠️ G1/G2/G4 done — **G3 needs redesign** (AUDIT §9.-1) |
| 5 | Deploy + mic UI | |
| 6 | Benchmark + writeup | |
| 7 | Videos + submission | |

## What measurement changed

Decisions overturned by data, not opinion — the reason the audit exists:

- **V3 (sentence-window) cut.** Passages are `p50 50 words` ≈ 3.5 sentences, so a window
  covered ~85% of its own parent. It lowered recall *and* MRR *and* cost 9 ms. Removing it
  shrank the index 63%.
- **ONNX int8 deferred.** Specified for speed; fp32 already runs at 5 ms. Its real
  justification turned out to be storage, not latency.
- **Views routed by language.** V2 helps Hindi +12.7 recall points and *hurts* English −2.0.
- **G3 off-topic detection doesn't work as designed.** Retrieval score cannot separate
  answerable from unanswerable on a broad web corpus.

## Cost

Free by default: the encoder is local, generation is extractive (AUDIT §2.4), and the
benchmarks make zero STT calls. Only Sarvam is metered. See [AUDIT §17](AUDIT.md#17-cost).

## Layout

```
echorag/
  stt.py       Sarvam saaras:v3 + retry
  embed.py     encoder, e5 prefixes, max_seq_len cap
  index.py     offline: load shard, chunk, write LanceDB (vector + BM25)
  retrieve.py  multi-view search, RRF fusion, parent dedup
  answer.py    extractive path, deadline race, pipeline
  guards.py    G1-G4
  harness.py   Deadline, CircuitBreaker, retry
  schemas.py   typed boundaries
  api.py       FastAPI
bench/         embed, ablation, latency, guardrails
learn/         design regression checks (not shipped)
```
