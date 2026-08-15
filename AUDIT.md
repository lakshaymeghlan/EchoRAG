# EchoRAG — System Design Audit

**HH Goa 2026 · Task 2 · Voice-Enabled RAG**
Author: build team · Written: 2026-08-15 · Deadline: 2026-08-22 23:59 IST

---

## 0. How this document is used

This is the **contract**, not a proposal. Every decision below is locked with a stated
reason and a stated rejected alternative. During the build:

- If you are about to write code that contradicts a locked decision → stop, change this
  doc first with a one-line reason, then write the code.
- Every phase in §13 has an **exit criterion**. Do not start phase N+1 until phase N's
  exit criterion is demonstrably met (a command that prints a number, not a vibe).
- Anything not in §12's "we are not building" list and not in a phase is scope creep.

Working style: **lazy senior dev**. Fewest files, fewest dependencies, stdlib first,
shortest diff that works. Complexity is added only when a measurement demands it.

---

## 1. What is actually being graded

The brief lists six technical requirements. Judges will look for *evidence*, not claims.
This is the evidence matrix we build backwards from — every row must have an artifact.

| # | Requirement | Evidence artifact we ship |
|---|---|---|
| 1 | Sarvam **or** ElevenLabs STT | `echorag/stt.py` calls Sarvam `saaras:v3`; demo video shows live mic |
| 2 | Chunking must be "vast" | `echorag/index.py` builds **6 indexed views**; `docs/CHUNKING.md` explains each, with an ablation table showing recall@10 per view |
| 3 | < 200 ms end-to-end | `bench/results.md` — a hard deadline enforced in code, not a hope |
| 4 | P50 / P70 / P100 | `bench/latency.py` over ≥ 300 queries, per-stage breakdown + histogram PNG |
| 5 | Harness, not a raw prompt | `echorag/harness.py` — deadline propagation, typed I/O, retries, circuit breaker, fallback chain, tool calls |
| 6 | Guardrails | `echorag/guards.py` + `bench/guardrails.md` — a table of adversarial inputs and the abstain decision for each |

**The unstated seventh requirement is that the live link works while a judge clicks it.**
That is weighted more heavily than any of the above in practice. Phase 5 exists for it.

---

## 2. The hard constraint: 200 ms

Everything else in this design is downstream of this section. Read it first.

### 2.1 What "the full process" can honestly mean

The brief says *"chunking + vector DB retrieval + everything through to final output"*.
Two observations:

1. **Chunking is not in the request path.** Chunking is index-build work — done offline,
   once. Nobody chunks 8.8M passages per query. If we chunked at query time we would be
   building the wrong system to satisfy a literal reading of a sentence. We chunk offline
   and *report the offline build time separately* so nothing is hidden.
2. **STT cannot be inside 200 ms.** Sarvam publishes sub-150 ms time-to-first-token and
   sub-250 ms median for `saaras:v3`. That is their number, before our network RTT. A
   200 ms budget that includes a third-party network round trip is not achievable by
   anyone, including the people who wrote the brief.

So the SLO we commit to, state on screen, and measure:

> **T_pipeline** = from *"final transcript string in hand"* to *"answer bytes leaving the
> server"*. Target: **P100 < 200 ms**, not P50. A P50 target with a fat tail is a system
> that misses its SLO for one user in twenty.

And we **additionally** report, in the same table, without spin:
- `T_stt` — mic → transcript (Sarvam, network-bound)
- `T_e2e` — mic → answer (the number a human actually experiences)

Hiding STT would be dishonest and a judge will ask. Reporting three clearly-labelled
numbers is stronger than reporting one flattering one.

### 2.2 Why the obvious architecture fails

The default RAG shape is: embed query → ANN search → stuff top-k into an LLM prompt →
stream the answer. Budget that honestly:

| Stage | Realistic cost | Notes |
|---|---|---|
| Guard + normalize | ~1 ms | pure Python |
| Embed query (ONNX int8, short query, CPU) | 8–15 ms | measured in Phase 1, not assumed |
| ANN search, 250k vecs, hnsw ef=64 | 2–6 ms | |
| BM25 lexical view | 5–10 ms | |
| RRF fusion + parent dedup | < 1 ms | plain Python |
| Grounding check + assembly | 3–8 ms | |
| **Subtotal — retrieval core** | **~20–40 ms** | comfortably inside budget |
| **LLM generation (hosted, incl. RTT)** | **300–900 ms** | **blows the budget by 4×** |

The retrieval half is easy. **The generation half is impossible over a network.** No model
choice fixes this — the floor is the round trip, not the model.

### 2.3 The decision: deadline-raced dual-path answering

This is the central architectural idea of EchoRAG and the thing worth defending in the
demo video.

```
transcript ──▶ guards ──▶ retrieve (multi-view + RRF) ──▶ evidence set
                                                            │
                                    ┌───────────────────────┴──────────────────────┐
                                    ▼                                              ▼
                       PATH A — EXTRACTIVE (local)                     PATH B — GENERATIVE (Claude)
                       span selection over top passage                 fluent grounded answer
                       ~5–20 ms, cannot miss the SLO                   300–900 ms, streams
                                    │                                              │
                                    └──────────────▶ DEADLINE RACE ◀───────────────┘
                                       B wins if it lands inside the remaining
                                       budget; otherwise A ships and B streams
                                       in as a refinement.
```

**Why this is legitimate and not a dodge:**

- MS MARCO is, by construction, a dataset where **the answer span is inside the retrieved
  passage**. The dataset literally ships an `Answer` field and an `is_selected` flag on the
  gold passage. Extractive answering is the *native* answer form for this corpus, not a
  degraded one.
- An extractive answer is **grounded by construction** — it is a substring of retrieved
  evidence. That is requirement 6 satisfied structurally rather than by asking a model
  nicely not to hallucinate.
- The deadline is **enforced in code**, so the SLO is a property of the system, not a
  property of a good day. `asyncio.wait_for` on the generative path with the remaining
  budget computed from a monotonic clock.
- The generative path still exists, still uses tools, still has structured output — so
  requirement 5 ("harness your model") is genuinely met, not sidestepped.

---

### 2.4 Do we need a hosted LLM at all? No.

Worth stating plainly, because it is the most common misreading of this project.

**The dataset is not a model.** `ai4bharat/MSMARCO-XI` ships queries, passages and answers —
no weights. A RAG pipeline needs two models the dataset does not provide:

| Model | Role | Where it comes from | In the 200 ms budget? |
|---|---|---|---|
| **Embedder** | turns query + passages into vectors so retrieval works at all | Hugging Face, **runs locally** (`multilingual-e5-small`, D2) | **Yes — ~8–15 ms.** This is the load-bearing model |
| **Generator** | phrases the retrieved evidence as an answer | **optional** (§2.3 Path B) | No — hence the race |

The embedder was never an API and never could be: a network hop inside a 200 ms budget is
an instant fail. That decision is independent of any vendor.

The generator is the one people assume must be a hosted LLM. For **this corpus it does not
need to exist at all**:

- MS MARCO is a span-extraction dataset. The gold answer lives inside the `is_selected`
  passage. Generating fluent prose is *restating a sentence we already retrieved.*
- The extractive answer is grounded by construction (§9 G4), which is the guardrail we want
  anyway. An LLM would be introduced only to then be verified back down to the same span.
- Zero API keys, zero cost, zero rate limits, nothing to expire mid-demo.

So `ECHORAG_GENERATOR` defaults to `none`. Two optional upgrades share one function
signature — `generate(query, evidence, deadline) -> str | None`, returning `None` on
timeout so the caller falls through to extractive:

- **`local`** — a small HF seq2seq/causal model for answer rewriting. Honest caveat: a 0.5B
  model on a cheap CPU box is ~0.7–1.3 s for a short answer, so it loses the race almost
  every time and arrives as the streamed refinement (§7). It is not a way to win the budget.
- **`anthropic`** — `claude-haiku-4-5`, better answers, same race, same timeout.

**Neither is on the critical path, and requirement 3 does not depend on either.** If a key
is missing, expired, rate-limited, or the vendor is down, the system answers correctly and
inside the SLO regardless. That is the point of the deadline design (§2.3), and it is why
the generator is a config value rather than an import.

**Where this costs us:** requirement 5 lists "tool calls" among the harness features. Tool
calling needs a model. Mitigation in §8 — the tool is real and demonstrated on the
`?deep=1` path; the brief says "model/**pipeline**", and the pipeline carries the retries,
structured I/O, deadline propagation and error recovery on its own.

---

## 3. Locked decisions

| # | Decision | Choice | Why | Rejected |
|---|---|---|---|---|
| D1 | STT vendor | **Sarvam** `saaras:v3` (`mode="transcribe"`), `saaras:v3-realtime` over WebSocket for the live demo | Corpus queries are Indic. Sarvam covers all 22 scheduled languages + English; ElevenLabs is weaker on Indic. Sub-150 ms TTFT. | ElevenLabs — worse Indic coverage. `saarika:v2.5` — **being deprecated by Sarvam**, do not build on it. |
| D2 | Embedding model | `intfloat/multilingual-e5-small`, 384-dim. **fp32 for now — ONNX int8 deferred** (§D2.1) | Cross-lingual: one shared space for Indic queries and English passages. **Measured 5.2 ms P50 / 7.8 ms P100 in fp32** — 4% of budget, so int8 is not needed for latency. | BGE-M3 (568M — 5× too slow). OpenAI/Cohere embeddings (network hop inside the budget = instant fail). |
| D3 | Vector store | **LanceDB**, in-process | It is a real vector DB (satisfies the brief literally), but **in-process** — no gRPC hop inside our budget. Ships vector search + BM25 full-text + metadata filtering in one dependency, killing three others. | Qdrant server (+1–3 ms network hop, +1 container). Raw hnswlib (fast, but then we owe our own BM25, metadata store, and persistence). Pinecone (network hop). |
| D4 | Generation | **Extractive by default — no hosted LLM required.** Optional `generate()` upgrade behind `ECHORAG_GENERATOR` (`none` \| `local` \| `anthropic`), default `none` | MS MARCO answers are spans inside the retrieved passage (§2.4). Zero vendor dependency, zero API keys, zero cost, and the SLO holds by construction. | LLM-always (misses SLO, adds a vendor the corpus doesn't need). Hard-wiring one vendor (a dead key on demo day kills the demo). |
| D5 | Answer strategy | Deadline-raced dual path (§2.3) | Only design that makes the SLO a code invariant. | LLM-only (misses SLO). Extractive-only (fails req. 5's spirit). |
| D6 | Corpus scope | **10k rows ≈ 100k passages** (0.55M chunks, ~0.84 GB fp32), Hindi + English; more languages are a stretch | Revised after measurement — see §D6.1. Fits a small box in fp32 with no quantization step. 100k passages is a serious corpus, not a toy. | 25k rows (2.11 GB fp32 — needs quantization we don't otherwise need). Full corpus (cannot deploy). |
| D7 | Language routing | Index the **English passage** as canonical; embed the Indic query into the same space | One index serves 13 languages instead of 13 indices. The dataset gives us parallel English + translated text for free. | Per-language indices (13× memory, 13× build time). Translate query → English first (+150 ms — budget gone). |
| D8 | Backend | FastAPI + `uvloop`, single process, models preloaded at import | Warm start is non-negotiable at a 200 ms P100. A cold model load inside a request is an instant P100 violation. | Serverless / Lambda (cold starts destroy P100). |
| D9 | Frontend | One `index.html`, `MediaRecorder` → `POST /ask` | The demo needs a mic button and an answer. A React app is a day we do not have. | Next.js / React (unrequested build step). |
| D10 | Hosting | Render or Fly.io persistent container, warm | Needs a warm process with ~1 GB RAM. HF Spaces sleeps. | Vercel (no persistent process). HF Spaces free tier (cold-sleeps mid-demo). |

---

### D2.1 / D6.1 — corrections from Phase 1 measurement

**Measured, not estimated** (`python -m bench.embed`, `du -sh index`, M-series laptop):

| | |
|---|---|
| Query embed, fp32, batch-of-1 | **P50 5.2 ms · P70 5.3 ms · P100 7.8 ms** |
| Chunks per passage | **5.50** (1 × v1 + 1 × v2 + ~3.5 × v3) |
| Index build throughput | ~450 chunks/s ⇒ 10k rows ≈ 20 min offline |

**ONNX int8 deferred.** D2 specified it to reach 8–15 ms. fp32 already does 5.2 ms — 4% of
budget. Converting would add a build step, a deploy artifact, and a real risk to the
weakest measured score (cross-lingual, 0.854 — §9.0), to save ~2 ms we do not need.
Revisit only if the **deploy host** measures badly (§15 already requires measuring there,
not on a laptop). `learn/01_embeddings.py` is the regression check if we ever do convert.

**D6 was wrong and is now corrected.** The original sizing counted *passages* and forgot
that chunking multiplies vector count by 5.5×. "250k × 384 × int8 ≈ 96 MB" should have read
~530 MB. Corrected sizing:

| Rows | Passages | Chunks | fp32 | int8 |
|---|---|---|---|---|
| 10k | 100k | 0.55M | **0.84 GB** | 0.21 GB |
| 25k | 249k | 1.37M | 2.11 GB | 0.53 GB |

Taking **10k rows in fp32**: fits a small box, needs no quantization step, and keeps the
whole encoder story to one dependency. Scale to 25k only if the deploy host has the room.

**The lesson worth keeping:** int8's real justification was always *storage*, never latency.
The original decision was right for a reason that turned out to be false — which is why
every locked decision here carries a number that can be checked.

---

## 4. System design

```
 ┌─────────────┐   audio    ┌──────────────┐  transcript  ┌────────────────────────────┐
 │  Browser    │──────────▶ │ Sarvam       │─────────────▶│  HARNESS  (deadline clock  │
 │ MediaRecorder│  webm/pcm │ saaras:v3    │              │            starts here)    │
 └─────────────┘            └──────────────┘              └──────────────┬─────────────┘
        ▲                                                                │
        │                                        ┌───────────────────────▼─────────────┐
        │                                        │ 1. INPUT GUARDS                     │
        │                                        │    empty / noise / unsafe / lang    │
        │                                        └───────────────────────┬─────────────┘
        │                                        ┌───────────────────────▼─────────────┐
        │                                        │ 2. RETRIEVE (§6)                    │
        │                                        │    6 views → RRF → parent dedup     │
        │                                        └───────────────────────┬─────────────┘
        │                                        ┌───────────────────────▼─────────────┐
        │                                        │ 3. RELEVANCE GATE  (off-topic = τ)  │
        │                                        └───────────────────────┬─────────────┘
        │                                        ┌───────────────────────▼─────────────┐
        │                                        │ 4. ANSWER RACE (§7)                 │
        │                                        │    A: extractive   B: claude-haiku  │
        │                                        └───────────────────────┬─────────────┘
        │                                        ┌───────────────────────▼─────────────┐
        │            JSON + citations            │ 5. GROUNDING GATE (§9)              │
        └────────────────────────────────────────│    overlap + citation or ABSTAIN    │
                                                 └─────────────────────────────────────┘
```

Offline, run once: `ingest.py` → download subset → build 6 views → write LanceDB tables +
ONNX embeddings → `index/` artifact committed to object storage, downloaded at boot.

---

## 5. Corpus and chunking design

Requirement 2 is the one most teams will under-serve. "Don't submit a single naive
fixed-size chunking approach" is a direct instruction. Our position:

> **Fixed-size chunking of MS MARCO is not merely naive, it is actively wrong.** MS MARCO
> passages are already human-curated retrieval units of ~50–100 words. Slicing them at 512
> characters *destroys* an existing high-quality boundary. The interesting design question
> for this corpus is not "how do I cut text up" but **"how many different views of the same
> passage do I index, and how do I fuse them?"**

### 5.0 Verified dataset facts (probed 2026-08-15, not taken from the card)

The dataset card is misleading in two places that would have cost a day each.

| Fact | Value | Consequence |
|---|---|---|
| Configs | Only `default` — **no per-language config** | `load_dataset(..., "hi")` raises. Card implies otherwise |
| File layout | Sharded per language: `validation/hinval.parquet`, `train/hintrain.parquet`, 27 files | Point `data_files` straight at the shard |
| Row ordering | **Grouped by language**, not interleaved | Streaming `default` from row 0 yields only Assamese. Filtering for Hindi this way scans millions of rows — the trap the shard path avoids |
| `passages` | A **nested dict**: `English_passages[10]`, `Translated_passages[10]`, `is_selected[10]` — parallel lists | 10 passages/row ⇒ D6's 250k passages = **25k rows** |
| `is_selected` | 1 on the gold passage, 0 elsewhere | Ground truth for recall@k (§5 ablation) and τ calibration (§9). **Never a retrieval input — that is leakage** |
| `query_type` | UPPERCASE (`DESCRIPTION`) | V6's type-conditioned rerank must case-fold |
| `Eng_Query` | Dirty — observed `'. what is a corporation?'` | Normalize leading punctuation before embedding |
| Language codes | FLORES-style (`hin_Deva`, `asm_Beng`) in `target_lang`; filenames use 3-letter prefixes (`hin`, `asm`) | Two different code systems in one dataset |

**Every row carries `English_passages` and `Eng_Query` regardless of `target_lang`.** So the
canonical English index (D7) can be built from any shard, and language shards are needed
only for V2 (translated view) and for in-language demo queries.

### 5.1 The six views

That reframing is the intellectual content of our chunking work. Six views:

| # | View | Unit indexed | What it wins | Why it earns its place |
|---|---|---|---|---|
| V1 | **Passage-dense (EN)** | Whole English passage → 1 vector | Broad topical / paraphrase queries | The baseline. Everything is measured against it. |
| V2 | **Passage-dense (translated)** | Whole Indic passage → 1 vector | Queries whose phrasing survives better in-language | Insurance against cross-lingual drift in V1. Fused, never used alone. |
| V3 | **Sentence-window (small-to-big)** | Each sentence + 1 neighbour each side → 1 vector; **returns the parent passage** | Precision on multi-topic passages, where one sentence carries the answer and passage-level embedding dilutes it | Classic small-to-big. Cheap: reuses the same encoder. |
| V4 | **Semantic-drift split** | Long passages only (> 120 tokens); split at points where consecutive-sentence cosine similarity drops below a fitted percentile | Handles the tail of genuinely long, topic-shifting passages without an arbitrary character count | This is the "semantic vs fixed-size" the brief asks for, applied *only where it matters* — running it on all 250k passages would be offline compute burned for nothing. |
| V5 | **Lexical BM25** | Full passage text, tokenized | Exact matches: names, model numbers, dates, prices — precisely where dense embeddings are weakest | Free with LanceDB FTS. Dense-only retrieval on numeric MS MARCO queries is a known failure mode. |
| V6 | **Metadata-aware payload** | `query_type` (description / numeric / entity / location / person), language, passage length, doc id | Enables type-conditioned reranking: a `numeric` query should prefer a passage containing a digit | Uses a field the dataset already gives us. Zero extra compute, real precision gain. |

**Overlap handling.** V3's windows overlap by one sentence on each side — this is deliberate,
so an answer that straddles a sentence boundary is never cut in half. The overlap is then
*undone at fusion time*: every retrieved chunk carries `parent_id`, and after RRF we keep
only the best-scoring chunk per parent. Retrieval recall gets the overlap; the LLM context
does not get the duplication.

**Fusion.** Reciprocal Rank Fusion, `score = Σ 1/(k + rank_i)` with `k=60`. Chosen over
weighted score-blending because RRF needs no per-view score normalization and is robust
when one view returns garbage — the failure mode is "that view contributes nothing",
not "that view's wild scores swamp everyone else's".

### 5.2 Ablation result — V3 cut, views routed by language (Phase 2)

150 gold-labelled queries per language, ANN index, warm-up discarded.

| Combination | HI recall@10 | HI MRR | EN recall@10 | EN MRR | P50 |
|---|---|---|---|---|---|
| V1 only | 0.633 | 0.384 | 0.967 | **0.702** | 20.5 ms |
| V1+V5 | 0.667 | 0.378 | 0.973 | 0.595 | 22 ms |
| V1+V3+V5 | 0.667 | 0.371 | 0.980 | 0.634 | 31 ms |
| **V1+V2** | 0.760 | **0.462** | 0.947 | 0.557 | 26 ms |
| **V1+V2+V5** | **0.767** | 0.448 | 0.960 | 0.559 | 29 ms |
| all views (incl. V3) | 0.753 | 0.433 | 0.980 | 0.603 | 38 ms |

**V3 (sentence-window) is cut.** Adding it to V1+V2+V5 lowers Hindi recall *and* MRR while
costing 9 ms — negative on every axis. The cause is in the Phase 1 data: passages are
`p50 50 words` ≈ 3.5 sentences, so a `window=1` chunk spans ~85% of its own parent. We were
indexing 67,597 near-duplicates of V1 that competed with the passages they came from.
Small-to-big is a long-document technique; these passages are too short to split.

Consequence: **chunks/passage drops 5.50 → 2.0**, so the index shrinks ~63% (10k rows:
0.84 GB → ~0.31 GB) and D6 could be revisited upward if we want more corpus.

**Views are routed by query language**, because V2 helps Hindi (+12.7 recall) and *hurts*
English (−2.0 — Hindi text is noise for an English query):

| Query language | Views | Rationale |
|---|---|---|
| Indic | V1 + V2 + V5 | V2 is the single biggest win available |
| English | V1 + V5 | V2 adds noise; V1 alone has the best MRR |

**V5 (BM25) is kept despite costing MRR** in both languages. The eval set is built from
`is_selected` on natural-language MS MARCO questions, which under-represents the exact-token
queries (names, model numbers, dates) BM25 exists for. Cutting it on this evidence would be
overfitting to the eval. Revisit in Phase 4 with a per-`query_type` breakdown.

**MRR is the metric we optimize, not recall@10.** The answer stage reads the top 5 and the
extractive path uses the top 1 — a gold passage sitting at rank 9 is not usable. Where the
two metrics disagree, MRR wins.

**Ablation is mandatory, not optional.** `bench/ablation.py` reports recall@10 and MRR@10
for: V1 alone, V1+V5, V1+V3+V5, and all six. If a view does not earn its latency, **we cut
it and say so in the writeup.** A view kept without evidence is decoration; a view cut with
evidence is engineering, and reads better to a judge than six views we cannot justify.

---

## 6. Retrieval path

1. Normalize transcript (Unicode NFC, strip filler, lowercase for BM25 only).
2. Embed once (ONNX int8). **One** forward pass serves V1–V4; they share the encoder.
3. Query all views concurrently (`asyncio.gather`). Total ≈ max(view latency), not sum.
4. RRF fuse → dedup by `parent_id` → top-5 passages.
5. Type-conditioned rerank (V6): if `query_type == numeric`, boost passages containing a
   digit; if `entity`/`person`, boost passages containing a capitalized multi-token span.
   Pure Python, sub-millisecond, no cross-encoder.

**No cross-encoder reranker.** A MiniLM cross-encoder over 20 pairs is ~50 ms on CPU —
a quarter of the entire budget for a marginal ordering improvement. Revisit only if the
Phase 3 ablation shows retrieval quality is the binding constraint on answer accuracy.

---

## 7. Answer generation

**Path A — extractive (always runs, always inside budget).**
Score each sentence of the top passage against the query using the *already computed* query
embedding plus lexical overlap; return the best sentence, optionally trimmed to a span.
Cost: one dot product per sentence over vectors we already have. ~5–20 ms.

**Path B — generative (OFF by default, §2.4).** Enabled with `ECHORAG_GENERATOR=local|anthropic`.
One signature either way: `generate(query, evidence, deadline) -> str | None`.

- Launched with `asyncio.wait_for(deadline.remaining_ms())` from a monotonic clock at request entry. On timeout it is cancelled, returns `None`, Path A's answer ships, and the SLO holds. **This is the only behaviour the SLO depends on** — it is identical whether the generator is local, hosted, or absent.
- `max_tokens: 256` — a spoken answer, not an essay. Output tokens are the dominant latency term.
- `anthropic` mode only: structured output via `output_config.format` with a JSON schema — `{answer, cited_passage_ids, confidence}`. Not prose we then regex; the schema *forces* citation. `strict: true` on any tool definition.
- `anthropic` prompt-caching note: Haiku 4.5's minimum cacheable prefix is 4096 tokens. Our system prompt will not reach that, so caching silently will not fire — do not build a cache-hit-rate dashboard and then debug a phantom bug. (Opus 5's minimum is 512, so `?deep=1` *can* cache.)
- `local` mode: expect to lose the race (§2.4). It exists to demonstrate a generative path with no vendor, not to win the budget.

**Streaming refinement.** When B misses the deadline it is not wasted: the response is
`Transfer-Encoding: chunked` — Path A's answer flushes first (meeting the SLO), and B's
answer arrives as a second chunk that the UI swaps in. The user gets a fast answer *and* a
good one. This is the demo moment.

---

## 8. Harness design

Requirement 5 asks for "structured orchestration around the model rather than a single raw
prompt-in, text-out call". `echorag/harness.py`:

- **`Deadline`** — a monotonic-clock object created at request entry and threaded through
  every stage. Each stage asks `deadline.remaining_ms()` and may degrade rather than
  overrun. This single object is what makes the SLO structural.
- **Typed I/O end to end** — Pydantic models at every boundary: `Transcript`, `Query`,
  `Evidence`, `Answer`, `Abstention`. No dicts crossing module lines.
- **Retries** — Sarvam and Claude calls wrapped with bounded retry + jittered backoff.
  Retry only on 408/409/429/5xx and connection errors; **never** on 4xx. The Anthropic SDK
  retries by default (`max_retries=2`) — we set it explicitly rather than inheriting it
  silently, because a retry inside a 200 ms budget is a bug.
- **Circuit breaker** — N consecutive Claude failures ⇒ open the circuit for 30 s and serve
  Path A only. Prevents a vendor outage from turning every request into a timeout wait.
- **Fallback chain** — `generative → extractive → abstain`. Every step is a valid,
  user-shippable response. There is no path that returns a 500.
- **Tool call** — one tool, `search_corpus(query, k)`, exposed on the `?deep=1` path (which
  requires a generator, §2.4) so the model can re-query when the first evidence set is thin.
  Off by default: a tool round trip is a second hop and cannot live inside 200 ms. Say
  plainly in the writeup which path it runs on rather than implying it is in the hot path.
- **Per-stage spans** — every stage records `(name, start, end)` into the response's `debug`
  field. This *is* the latency instrumentation; §10 just aggregates it. One mechanism, two
  uses.

---

## 9. Guardrails

Requirement 6: *"Show that your system knows when not to answer."* Four gates, each
returning a typed `Abstention` with a machine-readable reason.

| Gate | Position | Mechanism | Abstains when |
|---|---|---|---|
| **G1 Input sanity** | pre-retrieval | Transcript length, Sarvam confidence, non-speech detection | Empty / silence / < 2 tokens / confidence below floor → `"I didn't catch that"` |
| **G2 Safety** | pre-retrieval | Rule-based deny list + PII pattern match over a small, auditable category set | Unsafe or out-of-policy request → refuse, do not retrieve |
| **G3 Off-topic** | post-retrieval | **The retriever is the OOD detector.** If top-1 fused score < τ, nothing in the corpus is relevant | `"That's not in the knowledge base"` |
| **G4 Grounding** | post-generation | Token-overlap ratio between answer and cited passage, **plus** the citation must be a passage we actually retrieved | Overlap below threshold or hallucinated citation → fall back to extractive; if that also fails → abstain |

### 9.-1 G3 as designed does not work (Phase 4 measurement)

**The premise "the retriever is the OOD detector" is false for this corpus.** Measured:

| | in-corpus | off-topic |
|---|---|---|
| English, top-1 cosine | min 0.842 · p10 0.870 · p50 0.904 | p50 0.857 · **max 0.887** |
| Hindi, top-1 cosine | min 0.813 · p10 0.845 · p50 0.888 | p50 0.864 · **max 0.891** |

The distributions overlap almost entirely — off-topic scores sit *inside* the in-corpus
range. Best-F1 τ still answers 4/10 off-topic (EN) and 8/8 (HI). A score-margin signal
(top-1 minus the mean of 2..10) was tested as an alternative and separates no better.

**Why:** MS MARCO is a broad web crawl. "What is my bank account balance" genuinely
retrieves passages about bank balances. The queries we called off-topic are not
out-of-domain — they are **unanswerable**: they need personal data, live data, or an
action. That is an *intent* property of the query, not a *distance* property of the corpus,
and no retrieval score can carry it.

**Also a bug in the calibration itself:** the F1 sweep ran 120 positives against 8–10
negatives. Under that imbalance "always answer" is near-optimal, so the objective actively
rewarded never abstaining. Any future sweep must use balanced classes and weight the
dangerous error (answering the unanswerable) above the annoying one (refusing the
answerable).

**Redesign, to build:** replace the score threshold with a cheap intent gate at G1 —
first-person possessives (`my`, `मेरे`), live-time references (`right now`, `today`,
`अभी`), and imperative actions (`send`, `play`, `book`, `भेजो`, `चलाओ`) mark a query as
unanswerable from a static corpus regardless of what it retrieves. Keep a *low* absolute
floor (≈0.75) purely to catch nonsense strings, not as the primary gate.

### 9.0 Measured on day 1 — two facts that constrain τ

`learn/01_embeddings.py`, `multilingual-e5-small`, normalized:

| Pair | Cosine |
|---|---|
| Same meaning, both English | **0.935** |
| Unrelated topics, both English | **0.692** |
| Same meaning, Hindi query vs English | **0.854** |

**1. The score floor is ~0.69, not 0.** Contrastive-trained encoders are anisotropic —
all outputs occupy a narrow cone, so the usable range is roughly 0.6–1.0. An intuitive
`τ = 0.5` would never fire and every off-topic query would be answered confidently. τ must
come from the measured distribution; any hand-picked round number is wrong by construction.

**2. Cross-lingual scores sit systematically below same-language ones** (0.854 vs 0.935 for
identical meaning). A single global τ therefore abstains more on Hindi than English —
the system would be quietly worst for its target users. Phase 4 must either fit **τ per
query language** or normalize scores per language before thresholding. Decide with the
confusion matrix, not by feel.

D7 is confirmed by row 3: cross-lingual (0.854) beats unrelated (0.692) with room to spare,
so one shared index is sound.

**τ and the overlap threshold are calibrated, not guessed.** Method: sample 200 in-corpus
queries and 200 deliberately off-corpus queries (weather, personal questions, other domains,
nonsense). Plot the score distributions. Pick τ at the crossover, and **report the confusion
matrix in `bench/guardrails.md`.** A guardrail with an unjustified magic number is a
guardrail a judge will poke at until it breaks on camera.

G4 is the anti-hallucination gate and is *why* the extractive path is more than a latency
trick: it is a grounded answer we can always fall back to when the model's answer fails
verification.

---

## 10. Latency measurement methodology

Requirement 4 asks for P50 / P70 / P100 "across a reasonable number of test queries — not a
single best-case run." Method:

- **≥ 300 queries** sampled from the MSMARCO-XI validation split, stratified across
  `query_type` and language. Sampling seed committed so the run is reproducible.
- **Warm-up: 30 queries discarded** before measurement. First-request JIT, lazy imports,
  and page-cache misses are real but are not the steady state; measuring them silently
  would understate the system, measuring them without saying so would overstate it. We
  report the discard explicitly and report cold-start separately.
- **Per-stage percentiles**, not just total. A single total number hides which stage owns
  the tail — and the tail is the whole game at a P100 target.
- **P100 is the max.** It is a promise about the worst request, which is why the deadline is
  enforced in code rather than hoped for.
- Deliverables: `bench/results.md` (table), `bench/latency.png` (per-stage histogram +
  CDF), raw `bench/runs.jsonl` so the numbers are auditable.

Reported table shape:

| Stage | P50 | P70 | P100 |
|---|---|---|---|
| embed | | | |
| retrieve (all views, fused) | | | |
| guards | | | |
| answer (path A) | | | |
| **T_pipeline (SLO)** | | | **< 200 ms** |
| T_stt (Sarvam, network) | | | *reported, not in SLO* |
| T_e2e (mic → answer) | | | *reported, not in SLO* |

---

## 11. Failure modes and responses

| Failure | Blast radius | Response |
|---|---|---|
| Sarvam API down | No voice input | Text input box always present in the UI; demo degrades, does not die |
| Generator (local or hosted) down / slow / key expired | Path B unavailable | Circuit breaker → extractive answers. **SLO unaffected, demo unaffected** — the default config has no generator at all, so this failure mode is opt-in |
| Index file missing at boot | Total outage | Health check fails loudly at startup, not at first request |
| Query in an unindexed language | Bad retrieval | G3 catches it (low score) → honest abstain, not a confident wrong answer |
| Host cold-starts mid-demo | P100 catastrophe | Keep-warm ping every 4 min; D10 chose a persistent container for exactly this |
| Corpus subset lacks the demo query's answer | Embarrassing live abstain | Demo queries drawn from and verified against the actual indexed subset, ahead of recording |

---

## 12. What we are deliberately NOT building

Named here so nobody "just quickly adds" one at 2am on the 21st.

- ❌ Cross-encoder reranker — ~50 ms for marginal gain (revisit only if §5's ablation demands it)
- ❌ Query translation to English — +150 ms, budget gone
- ❌ HyDE / query expansion — an extra LLM call inside the budget
- ❌ Conversation memory / multi-turn — not asked for
- ❌ User accounts, database, session storage — not asked for
- ❌ React / Next.js frontend — one HTML file does the job
- ❌ Docker Compose with a separate vector-DB container — D3 exists to avoid it
- ❌ Full 11.5M-row corpus — cannot deploy, proves nothing
- ❌ Fine-tuning anything — no time, no evidence it is the binding constraint

---

## 13. Phases

7 days. Each phase has an exit criterion that is a **command producing a number**.

**Phase 0 — Skeleton (Aug 15, 2h)**
Repo layout, `pyproject.toml`, `.env.example`, health endpoint, keys verified.
*Exit:* `curl localhost:8000/health` → `200`; one live Sarvam call transcribes a WAV.

**Phase 1 — Ingest + index (Aug 16, full day)**
Stream the HF subset, build V1–V6, write LanceDB. Measure encoder latency for real.
*Exit:* `python -m bench.embed` prints P50 embed latency; index on disk with 250k parents.

**Phase 2 — Retrieval + fusion (Aug 17)**
Multi-view query, RRF, parent dedup, type-conditioned rerank.
*Exit:* `python -m bench.ablation` prints the recall@10 table for all four view combinations.

**Phase 3 — Answering + harness (Aug 18)**
Extractive path, Claude path, `Deadline`, retries, circuit breaker, fallback chain.
*Exit:* `POST /ask` returns typed JSON with citations; kill the Claude key → still answers.

**Phase 4 — Guardrails + calibration (Aug 19)**
G1–G4; calibrate τ and the overlap threshold on the 200/200 split.
*Exit:* `bench/guardrails.md` contains the confusion matrix and the chosen thresholds.

**Phase 5 — Deploy + frontend (Aug 20)**
Mic UI, streaming refinement, deploy, keep-warm.
*Exit:* the public URL answers a spoken question from a phone on mobile data.

**Phase 6 — Benchmark + writeup (Aug 21)**
300-query latency run, charts, README, `docs/CHUNKING.md`.
*Exit:* `bench/results.md` shows **T_pipeline P100 < 200 ms**. If it does not, cut features until it does — the SLO is the deliverable.

**Phase 7 — Videos + submission (Aug 22, morning)**
Process video (90s), demo video, per-member posts on IG / X / LinkedIn with `#RAGInGoa`
(≥ 1 public Instagram account), form submitted.
*Exit:* form submitted **before 18:00 IST**, not 23:59. No resubmissions are allowed — the
buffer is not optional.

> **Hard rule: freeze code at Phase 6 exit.** Phase 7 is recording and posting only. A
> last-minute "improvement" that breaks the live link after the video is recorded is the
> single most likely way this submission fails.

---

## 14. Repo layout

```
echorag/
  stt.py         # Sarvam saaras:v3 client + retry
  embed.py       # ONNX int8 encoder, preloaded
  index.py       # offline: build V1–V6 into LanceDB
  retrieve.py    # multi-view query, RRF, dedup, type rerank
  answer.py      # extractive path + Claude path + the race
  guards.py      # G1–G4
  harness.py     # Deadline, retries, breaker, fallback chain, spans
  schemas.py     # Pydantic types
  api.py         # FastAPI app
  static/index.html
bench/
  latency.py  ablation.py  guardrails.py  results.md
docs/
  CHUNKING.md
AUDIT.md         # this file — the contract
README.md
```

Eleven source files. If a twelfth appears, it needs a reason in this document.

---

## 15. Risk register

| Risk | L | I | Mitigation |
|---|---|---|---|
| Cross-lingual retrieval (Indic query → EN passage) underperforms | Med | High | V2 fusion is the hedge; measured in Phase 2, before it can surprise us in Phase 6 |
| ONNX int8 embed > 20 ms on the deploy box | Med | High | Measure on the *host*, not the laptop, in Phase 1. Fallback: smaller max sequence length |
| 250k passages exceed host RAM | Low | High | int8 ≈ 96 MB; memory-map LanceDB; halve the subset if needed |
| Sarvam rate limits during the demo | Med | Med | Pre-recorded audio fallback in the demo video; text input always available |
| Team misses the promotion requirement | Med | **Fatal** | It is a Phase 7 checklist item with named owners, not a nice-to-have |

---

## 16. Confirm before Phase 1 (defaults are already locked; say so if you disagree)

1. **Hosting** — defaulting to Render persistent container (D10). If you have Fly.io or a
   VPS already, say so now; it changes the deploy step, not the design.
2. **Warm hosting — will we pay ~$5–7/month?** This is the one place free costs us
   something real (§17). A sleeping free-tier container is a P100 violation on the judge's
   first click. Answer this before Phase 5, not during it.
3. **Language scope** — defaulting to Hindi + English, with Tamil/Bengali/Marathi as a
   stretch. Adding languages is cheap (D7's single shared index); saying so now avoids a
   re-ingest later.

Silence on these = defaults stand and Phase 1 proceeds.

---

## 18. How we work (added Phase 1)

The build doubles as the team's learning path. This changes *who writes what*, not any
technical decision above.

**Split.** The owner writes the **concept core** of each phase — the 30–60 lines that are
the actual idea. Assistance covers **plumbing** — download loops, table setup, ONNX export,
HTML, deploy config. Plumbing teaches nothing and costs days we do not have.

| Phase | Owner writes (the concept) | Assisted (plumbing) |
|---|---|---|
| 1 | Pooling + normalize, the chunkers (V3, V4) | HF streaming download, ONNX export, LanceDB schema |
| 2 | Cosine, RRF, recall@k | Query fan-out wiring |
| 3 | Extractive scorer, the deadline race | Retry/breaker boilerplate |
| 4 | Threshold calibration + confusion matrix | Adversarial query set |
| 5 | — | Mic UI, deploy, keep-warm |
| 6 | Percentile maths, reading the tail | Chart rendering |

**Loop per phase:** concept explained → owner writes against a failing test → owner debugs
first (15 min) before asking → senior-dev review (what to cut) → phase exit number measured.

**Comprehension gate.** 2–3 questions before advancing. Phase 4 reuses Phase 2's ideas, so
an unanswered question compounds rather than staying local.

**`learn/`** holds throwaway exercise scripts. Not shipped, not imported by `echorag/`,
excluded from the file-count discipline in §14.

---

## 17. Cost

The default configuration is **free except for STT**, which the brief makes mandatory.

| Component | Cost | Note |
|---|---|---|
| Dataset (MSMARCO-XI) | **Free** | CC-licensed on Hugging Face |
| Embedder (`multilingual-e5-small`) | **Free** | MIT, open weights, runs locally — no inference API |
| LanceDB | **Free** | Apache-2.0, in-process |
| Generation (default `none`) | **Free** | Extractive — no model call at all (§2.4) |
| FastAPI / frontend | **Free** | |
| **Sarvam STT** | **Free tier, then paid** | The brief *requires* Sarvam or ElevenLabs. Signup credits comfortably cover build + demo; both vendors meter by audio duration. Budget nothing, but **do not burn credits looping the benchmark** — §10 benchmarks `T_pipeline` from a transcript string, so the 300-query latency run makes **zero** STT calls by design |
| **Hosting** | **$0 or ~$5–7/mo** | The honest one. Free tiers sleep; a cold start is an instant P100 violation on the judge's first click (§11). Free is *possible* with a keep-warm ping, but is the single largest avoidable demo risk |

**Verdict:** buildable for ₹0 with Sarvam's free credits and a keep-warm ping on a free
host. Paying for one month of a small persistent container is the cheapest risk reduction
available on this project — it protects the unstated seventh requirement (§1).

Cost is *not* why generation defaults to `none` — §2.4 is. It would still default to `none`
with unlimited credits, because for this corpus the extractive answer is the grounded one.
