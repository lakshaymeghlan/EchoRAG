# EchoRAG

Voice-enabled RAG over [MSMARCO-XI](https://huggingface.co/datasets/ai4bharat/MSMARCO-XI).
Speak a question in Hindi or English, get a grounded, cited answer.

**[AUDIT.md](AUDIT.md) is the design contract.** Read §2 before changing anything —
the 200 ms SLO is what the architecture is shaped around.

```
voice ──▶ Sarvam saaras:v3 ──▶ [ guards ─▶ retrieve (6 views + RRF) ─▶ answer ─▶ ground ]
                                └────────── T_pipeline: P100 < 200 ms ──────────┘
```

## Setup

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env      # add your SARVAM_API_KEY
```

## Run

```sh
uvicorn echorag.api:app --reload
curl -s localhost:8000/health
```

## Phase 0 exit criteria

```sh
curl -s localhost:8000/health                  # -> {"status":"ok", ...}
python -m echorag.stt sample.wav               # -> transcript + T_stt   (<=30s, 16kHz mono WAV)
```

## Status

Phase 0 of 7 — skeleton. See [AUDIT.md §13](AUDIT.md#13-phases) for the plan.
Modules arrive in their phase; empty placeholder files are deliberately not created.

| Phase | | |
|---|---|---|
| 0 | Skeleton, health, Sarvam verified | ✅ |
| 1 | Ingest + build the 6 index views | |
| 2 | Retrieval + RRF fusion | |
| 3 | Answering + harness | |
| 4 | Guardrails + threshold calibration | |
| 5 | Deploy + mic UI | |
| 6 | Benchmark + writeup | |
| 7 | Videos + submission | |

## Cost

Runs free by default — the embedder is local, generation is extractive, and the
300-query benchmark makes zero STT calls. See [AUDIT.md §17](AUDIT.md#17-cost).
