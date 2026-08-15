"""Query and chunk encoder (AUDIT D2).

Loaded once at import so a cold model load can never land inside a request.
Phase 1 uses sentence-transformers; Step 5 swaps in ONNX int8 behind this same
`encode()` signature.
"""

import numpy as np

MODEL_NAME = "intfloat/multilingual-e5-small"
DIM = 384

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def encode(texts: list[str], is_query: bool = False, batch_size: int = 64) -> np.ndarray:
    """Return L2-normalized vectors, shape (len(texts), 384).

    e5 is trained with asymmetric prefixes — questions get "query: ", documents
    get "passage: ". Using the wrong one silently costs accuracy, so the caller
    must say which side it is on rather than guessing here.

    Normalizing at write time means cosine is a plain dot product at read time.
    """
    prefix = "query: " if is_query else "passage: "
    return _get_model().encode(
        [prefix + t for t in texts],
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
