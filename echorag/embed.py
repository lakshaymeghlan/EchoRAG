"""Query and chunk encoder (AUDIT D2).

Runs the ONNX export the model author already publishes, via onnxruntime —
not torch. That was always the plan (D2), and it became load-bearing when the
free tiers we could actually deploy to capped at 512 MB: torch's allocator put
peak RSS at 968-1070 MB, while this sits near 300 MB.

fp32 deliberately, not the int8 export. int8 would be smaller again, but it
perturbs the vectors, and the index on disk was written with fp32 — every
similarity threshold in guards.py was tuned against these exact numerics.
Identical arithmetic means no reindex and no re-tuning. Revisit only if 512 MB
turns out to be too tight.

Loaded lazily but warmed at startup, so a cold load can never land in a request.
"""

import os

import numpy as np

MODEL_NAME = "intfloat/multilingual-e5-small"
DIM = 384
MAX_SEQ_LEN = 192

# int8 by default, and it is not a compromise — measured on 300 EN queries
# against the fp32-built index (bench.ablation, V1-only shipped config):
#
#            recall@10   MRR@10   P50      peak RSS
#   fp32       0.967      0.643   20.4ms   ~1400 MB
#   int8       0.967      0.646   19.7ms   ~600-800 MB
#
# Same recall, marginally better MRR, faster, and roughly half the memory.
# Per-vector agreement with fp32 is 0.9988 cosine, far inside the 0.78/0.75
# thresholds in guards.py, so the existing index needs no rebuild.
#
# Xenova's mirror rather than intfloat's own int8 export: the latter is
# qint8_avx512_vnni, which needs AVX512-VNNI that a small cloud instance may
# not have, and measured 840 MB against this one's 600.
ONNX_REPO = os.environ.get("ECHORAG_ONNX_REPO", "Xenova/multilingual-e5-small")
ONNX_FILE = os.environ.get("ECHORAG_ONNX_FILE", "onnx/model_quantized.onnx")

_session = None
_tokenizer = None


def _load():
    """Fetch tokenizer + ONNX graph, cached on disk by huggingface_hub."""
    global _session, _tokenizer
    if _session is not None:
        return _session, _tokenizer

    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    _tokenizer = Tokenizer.from_file(hf_hub_download(MODEL_NAME, "tokenizer.json"))
    # Default is 512. Passages are p50 ~50 words, but Devanagari tokenizes to
    # roughly 3x English, so long Hindi sentences were hitting the ceiling and
    # dominating the budget. Capping bounds worst-case cost.
    _tokenizer.enable_truncation(max_length=MAX_SEQ_LEN)
    _tokenizer.enable_padding()

    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    _session = ort.InferenceSession(
        hf_hub_download(ONNX_REPO, ONNX_FILE),
        opts,
        providers=["CPUExecutionProvider"],
    )
    return _session, _tokenizer


def _forward(batch: list[str]) -> np.ndarray:
    session, tokenizer = _load()
    encoded = tokenizer.encode_batch(batch)

    ids = np.array([e.ids for e in encoded], dtype=np.int64)
    mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)

    # This export declares token_type_ids even though XLM-R never uses them, so
    # feed by the graph's own input names rather than a fixed dict — a different
    # export dropping or adding an input then costs nothing here.
    available = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
    feed = {i.name: available[i.name] for i in session.get_inputs() if i.name in available}

    # (batch, tokens, 384)
    hidden = session.run(None, feed)[0]

    # Mean pooling over real tokens only — padding must not dilute the mean.
    # This mirrors sentence-transformers' Pooling(mode="mean") exactly; using
    # CLS instead would silently degrade e5, which is trained for mean.
    m = mask[:, :, None].astype(np.float32)
    return (hidden * m).sum(axis=1) / np.maximum(m.sum(axis=1), 1e-9)


def encode(texts: list[str], is_query: bool = False, batch_size: int = 64) -> np.ndarray:
    """Return L2-normalized vectors, shape (len(texts), 384).

    e5 is trained with asymmetric prefixes — questions get "query: ", documents
    get "passage: ". Using the wrong one silently costs accuracy, so the caller
    must say which side it is on rather than guessing here.

    Normalizing at write time means cosine is a plain dot product at read time.
    """
    prefix = "query: " if is_query else "passage: "
    prefixed = [prefix + t for t in texts]

    out = np.concatenate(
        [_forward(prefixed[i : i + batch_size]) for i in range(0, len(prefixed), batch_size)]
    )
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)
