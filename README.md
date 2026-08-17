---
title: EchoRAG
emoji: 🎙️
colorFrom: green
colorTo: yellow
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
pinned: false
license: mit
short_description: Voice RAG over MSMARCO-XI, transcript to answer in under 200ms
---

# EchoRAG

Voice-enabled RAG over [MSMARCO-XI](https://huggingface.co/datasets/ai4bharat/MSMARCO-XI).
Speak a question in Hindi or English, get a grounded, cited answer — or an honest refusal.

**[AUDIT.md](AUDIT.md) is the design contract.** Read §2 before changing anything. Every
locked decision carries a measured number you can re-check, and several have already been
overturned by measurement.

```
voice ─▶ Sarvam saaras:v3 ─▶ [ guards ─▶ retrieve (RRF) ─▶ answer ─▶ ground ]
                              └──────── T_pipeline P100 63 ms ─────────┘
```

## Setup

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[learn]"     # [learn] pulls sentence-transformers (~2GB, includes torch)
cp .env.example .env          # add SARVAM_API_KEY — never put it in .env.example
```

## Run

```sh
# backend
uvicorn echorag.api:app --reload          # :8000

# frontend (separate terminal)
cd frontend && npm run dev                # :3000
```

`POST /ask` (form field `text`) and `POST /ask-voice` (form field `audio`) both return the
same shape, including per-stage timings. An abstention is a normal 200 response, not an
error — knowing when not to answer is a feature (AUDIT §9).

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
python -m echorag.tools            # tool registry: schema validation, retries, deadline
python -m echorag.stt sample.wav   # live Sarvam call (<=30s, 16kHz mono)
```

## Measured

**T_pipeline** — transcript in, answer out. 300 queries, 20 warm-up discarded.
Full breakdown in [bench/results.md](bench/results.md), chart in `bench/latency.png`.

| | P50 | P70 | P95 | P99 | P100 |
|---|---|---|---|---|---|
| **All (n=300)** | **35.1 ms** | **39.1 ms** | **50.9 ms** | **57.7 ms** | **62.6 ms** |

`0/300 over the 200 ms budget.` `bench.latency` exits non-zero on a miss, so it gates a
deploy rather than printing a number someone shrugs at. STT is excluded by design and reported separately —
measured **513 ms**, which is 2.5x the entire budget and cannot fit inside it (AUDIT §2.1).

**Guardrails** — balanced classes, full pipeline (AUDIT §9.1).

| | answered | refused | |
|---|---|---|---|
| English answerable | 19 | 1 | |
| English unanswerable | **0** | **20** | 100% caught |
| Hindi answerable | 15 | 1 | |
| Hindi unanswerable | 4 | 12 | 75% caught |

Known gap: Devanagari nonsense strings are not caught — lexical grounding separates cleanly
in ASCII and not at all in Devanagari, so it is ASCII-gated rather than shipped broken.

**Retrieval quality** — 150 gold-labelled queries per language.

| Query | Views | recall@10 | MRR@10 |
|---|---|---|---|
| Hindi | V2 (Hindi passages) | 0.807 | 0.529 |
| English | V1 (English passages) | 0.967 | 0.620 |

Searching *both* languages leaves recall flat and drops MRR hard (HI 0.529 → 0.412) — see
[AUDIT §5.3](AUDIT.md). BM25 is off by default for the same reason, retained on the widen path.

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
| 4 | Guardrails + calibration | ✅ |
| 5 | Next.js frontend + voice API | ✅ (deploy pending) |
| 6 | Benchmark + writeup | ✅ |
| 7 | Videos + submission | |

## What measurement changed

Decisions overturned by data, not opinion — the reason the audit exists:

- **V3 (sentence-window) cut.** Passages are `p50 50 words` ≈ 3.5 sentences, so a window
  covered ~85% of its own parent. It lowered recall *and* MRR *and* cost 9 ms. Removing it
  shrank the index 63%.
- **ONNX int8 deferred.** Specified for speed; fp32 already runs at 5 ms. Its real
  justification turned out to be storage, not latency.
- **Search only the query's own language.** Searching both leaves recall unchanged and
  destroys MRR (HI 0.529 -> 0.412). Cut BM25 from the default path for the same reason.
  Result: P50 47.9 -> 35.1 ms, P100 161.9 -> 62.6 ms, MRR +0.08 in both languages.
- **G3 off-topic detection rebuilt.** Retrieval score cannot separate answerable from
  unanswerable on a broad web corpus — the distributions overlap almost entirely. Replaced
  with an intent gate (0-2% false-positive rate, measured on 6,535 real queries) plus a
  lexical-grounding backstop. English went 0% -> 100% caught.

## Deploy (HuggingFace Spaces)

One container serves the UI and the API on port 7860 — one URL, no CORS.

```sh
# 1. build the index locally, then push it to a Dataset repo (once)
python -m echorag.index --lang hin --rows 10000
hf auth login
python scripts/push_index.py <your-username>/echorag-index

# 2. create a Space (SDK: Docker), then push this repo to it
git remote add space https://huggingface.co/spaces/<your-username>/echorag
git push space main
```

In the Space settings:

| Where | Key | Value |
|---|---|---|
| **Secrets** | `SARVAM_API_KEY` | your key — never commit it |
| Variables | `ECHORAG_INDEX_REPO` | `<your-username>/echorag-index` |

The container downloads the index at boot (~1-2 min, since Spaces disk is
ephemeral), then stays warm. `/health` reports `index_ready` so a failed download
is visible rather than silent.

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
  tools.py     tool registry + dispatcher (schema-validated, deadline-aware)
  harness.py   Deadline, CircuitBreaker, retry
  schemas.py   typed boundaries
  api.py       FastAPI
bench/         embed, ablation, latency, guardrails, report
docs/          CHUNKING.md — the six strategies, ablated
               BACKEND.md  — every file and function explained
frontend/      Next.js app (mic + timings display)
learn/         design regression checks (not shipped)
```
