# Chunking, indexing and retrieval

The brief asks for a chunking strategy that is *vast* — "not a single naive fixed-size
chunking approach". This is what we built, what we measured, and what we deleted.

**The short version:** we built six strategies, measured each one against gold labels, and
shipped three. The two we cut are the interesting part.

---

## 1. Why fixed-size chunking is the wrong answer here

Before choosing a strategy we measured the corpus (`python -m echorag.index --stats`):

```
passages      : 1997
words/passage : min 3   p50 50   max 169
```

**MS MARCO passages are already human-curated retrieval units of ~50 words.** A 512-character
splitter would cut a ~300-character passage that already has a good boundary. Fixed-size
chunking here is not merely naive — it actively destroys structure that the dataset authors
put in.

So the design question for this corpus is not *"how do I cut text up"*. It is:

> **How many different views of the same passage do I index, and how do I fuse them?**

That reframing is the substance of our chunking work.

---

## 2. The six views

Every view indexes the *same* passages differently. All chunks carry `parent_id`, so
retrieval matches a chunk but always returns the whole parent passage.

| | View | Unit indexed | Intended job |
|---|---|---|---|
| **V1** | Passage-dense (English) | whole passage → 1 vector | broad, paraphrased queries |
| **V2** | Passage-dense (translated) | whole Indic passage → 1 vector | in-language matching for Indic queries |
| **V3** | Sentence-window | sentence + 1 neighbour each side → 1 vector, returns parent | precision on multi-topic passages (small-to-big) |
| **V4** | Semantic-drift split | long passages only, split where consecutive-sentence cosine drops | topic shifts inside long passages |
| **V5** | Lexical BM25 | full passage text, tokenized | exact tokens: names, numbers, dates |
| **V6** | Metadata-aware | `query_type`, `lang`, `parent_id` on every row | type-conditioned filtering and reranking |

**Overlap handling.** V3's windows overlap by one sentence on each side, so an answer
straddling a sentence boundary is never cut in half. The overlap is then *undone at fusion
time*: after RRF we keep only the best-scoring chunk per `parent_id`. Retrieval recall gets
the overlap; the answer context does not get the duplication.

**Fusion — Reciprocal Rank Fusion.** Views return incomparable scores (cosine `0.13` vs BM25
`12.7`). RRF discards scores and uses rank only:

```
score(passage) = Σ over views  1 / (k + rank_in_that_view),   k = 60
```

Chosen over weighted score-blending because it needs no per-view normalization and degrades
safely: a view returning garbage contributes ~nothing rather than swamping the others with
wild scores. `k=60` flattens the curve so one confident-but-wrong view can't dominate.

**Parent dedup before fusion.** A passage with 8 sentence-windows would otherwise occupy 8
slots in one view's ranking and collect 8× the RRF weight — long passages would win for
being long. Each view's ranking is collapsed to unique parents, keeping the best rank.

---

## 3. What the measurements said

150 gold-labelled queries per language (`is_selected` from the dataset, used **only** for
scoring — never as a retrieval input, which would be leakage). `python -m bench.ablation`.

| Combination | HI recall@10 | HI MRR | EN recall@10 | EN MRR | P50 |
|---|---|---|---|---|---|
| V1 only | 0.633 | 0.384 | 0.967 | **0.702** | 20.5 ms |
| V1+V5 | 0.667 | 0.378 | 0.973 | 0.595 | 22 ms |
| V1+V3+V5 | 0.667 | 0.371 | 0.980 | 0.634 | 31 ms |
| **V1+V2** | 0.760 | **0.462** | 0.947 | 0.557 | 26 ms |
| **V1+V2+V5** | **0.767** | 0.448 | 0.960 | 0.559 | 29 ms |
| all six | 0.753 | 0.433 | 0.980 | 0.603 | 38 ms |

### V3 was cut — it made the system worse

Adding sentence-windows to V1+V2+V5 **lowered Hindi recall (0.767 → 0.753) and MRR
(0.448 → 0.433) while costing 9 ms.** Negative on every axis.

The cause is in the corpus measurement above. Passages are `p50 50 words` ≈ 3.5 sentences,
so a `window=1` chunk spans about **85% of its own parent**. We were indexing 67,597 near
duplicates of V1 that competed with the passages they came from.

Small-to-big is a technique for *long documents*. These passages are too short to split.

Consequence: chunks per passage dropped **5.50 → 2.0**, and the index shrank ~63%.

### V4 was never built

V4 only fires on passages over 120 tokens. Measured `max = 169 words`, `p50 = 50` — a very
thin tail. Building it would have meant offline compute and a code path for ~2% of passages,
with V3's result suggesting splitting short passages hurts anyway. Documented as deferred
rather than silently skipped.

### V2 is language-specific — in both directions

V2 gives Hindi **+12.7 recall points**. It costs English **−2.0** — indexing Hindi text adds
noise to English queries. So views are selected per query language rather than globally:

| Query language | Views used |
|---|---|
| Indic (non-ASCII) | V1 + V2 + V5 |
| English (ASCII) | V1 + V5 |

A single global configuration would have been wrong for one of the two languages regardless
of which we picked.

### V5 (BM25) is kept despite costing MRR

BM25 lowers MRR in both languages on this eval. We kept it anyway: the eval is built from
`is_selected` on natural-language MS MARCO questions, which under-represents exactly the
exact-token queries (names, model numbers, dates) that BM25 exists for. Cutting it on this
evidence would be overfitting to the eval. Flagged for re-testing per `query_type`.

### Why MRR, not recall@10

The answer stage reads the top 5 and the extractive path uses the **top 1**. A gold passage
sitting at rank 9 is "recalled" and useless. Where the two metrics disagree, MRR wins.

---

## 4. Indexing

- **Store:** LanceDB, in-process — a real vector DB, but no network hop inside the 200 ms
  budget. Gives vector search, BM25 full-text and metadata filtering in one dependency.
- **Two tables.** `chunks` (searched) and `passages` (returned). Denormalizing parent text
  onto every chunk would duplicate the corpus on disk and slow every scan; retrieval narrows
  to ≤5 parents first, so the join is one small batched lookup.
- **ANN index:** `IvfFlat`, cosine. Without it LanceDB brute-force scans every vector —
  measured 62 ms → 38 ms for 1.4 points of Hindi recall. Flat rather than PQ keeps full
  vectors, so the only recall loss is partition pruning.
- **Embedding:** `multilingual-e5-small`, 384-dim, L2-normalized at write time so cosine is
  a plain dot product at read time. e5's asymmetric prefixes are respected — `query:` for
  questions, `passage:` for documents.

## 5. Reproducing

```sh
python -m echorag.index --lang hin --rows 200 --stats   # corpus statistics
python -m echorag.index --lang hin --rows 10000         # build the index
python -m bench.ablation --queries 150 --lang hi        # the table above
python -m bench.ablation --queries 150 --lang en
python test_chunkers.py                                 # chunker unit checks
```

`sentence_window()` is still in `echorag/index.py` even though `chunks_for()` no longer
calls it — the ablation has to stay reproducible. "We built it, measured it, cut it" is a
stronger claim than "we never tried it."
