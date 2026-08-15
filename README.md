# EchoRAG

Voice-enabled RAG over [MSMARCO-XI](https://huggingface.co/datasets/ai4bharat/MSMARCO-XI).
Speak a question in Hindi or English, get a grounded, cited answer.

**[AUDIT.md](AUDIT.md) is the design contract.** Read §2 before changing anything — the
200 ms SLO is what the architecture is shaped around, and every locked decision carries a
measured number you can re-check.

```
voice ─▶ Sarvam saaras:v3 ─▶ [ guards ─▶ retrieve (6 views + RRF) ─▶ answer ─▶ ground ]
                              └────────── T_pipeline: P100 < 200 ms ──────────┘
```

## Setup

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env      # add SARVAM_API_KEY
```

`pip install -e ".[learn]"` additionally pulls `sentence-transformers` (~2 GB, includes
torch). Required today — Phase 1 uses it as the encoder.

## Run

```sh
uvicorn echorag.api:app --reload
curl -s localhost:8000/health
```

## Build the index

```sh
python -m echorag.index --lang hin --rows 10000        # ~20 min, writes index/
python -m echorag.index --lang hin --rows 200 --stats  # inspect the shard, no build
```

Language shards: `hin`, `tam`, `ben`, `mar`, `asm`, `guj`, `kan`, `mal`, `nep`, `ori`,
`pan`, `san`, `tel`, `urd`.

## Checks

```sh
python test_chunkers.py            # V1/V2/V3 chunkers
python learn/01_embeddings.py      # regression check for D2 + D7
python -m bench.embed              # query embed latency
python -m echorag.stt sample.wav   # live Sarvam call (<=30s, 16kHz mono)
```

## Measured so far

| | |
|---|---|
| Query embed (fp32, batch-of-1) | **P50 5.2 ms · P100 7.8 ms** — 4% of budget |
| Cross-lingual match (HI query → EN passage) | **0.854** vs 0.692 unrelated — D7 holds |
| Chunks per passage | 5.50 |
| Index size | 10k rows → 100k passages → 0.55M chunks → ~0.84 GB |

Numbers are from an M-series laptop. The deploy host will be slower — AUDIT §15 requires
re-measuring there before trusting them.

## Status

| Phase | | |
|---|---|---|
| 0 | Skeleton, health, Sarvam client | ✅ |
| 1 | Ingest + index (V1/V2/V3 + BM25 + metadata) | ✅ |
| 2 | Retrieval + RRF fusion | ← next |
| 3 | Answering + harness | |
| 4 | Guardrails + threshold calibration | |
| 5 | Deploy + mic UI | |
| 6 | Benchmark + writeup | |
| 7 | Videos + submission | |

V4 (semantic-drift splitting) is deferred — real passages measured `p50 50 words`, so it
would fire on a thin tail. The Phase 2 ablation decides whether it is ever worth writing.

## Layout

```
echorag/
  stt.py       Sarvam saaras:v3 + retry
  embed.py     encoder, e5 query/passage prefixes
  index.py     offline: load shard, chunk, write LanceDB (vector + BM25)
  schemas.py   Transcript, Passage, Chunk
  api.py       FastAPI
bench/embed.py  latency
learn/          design regression checks (not shipped)
```

Modules arrive in their phase — empty placeholder files are deliberately not created.

## Cost

Runs free by default: the encoder is local, generation is extractive (AUDIT §2.4), and the
benchmark makes zero STT calls. Only Sarvam is metered. See [AUDIT §17](AUDIT.md#17-cost).
