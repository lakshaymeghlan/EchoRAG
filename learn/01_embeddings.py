"""Regression check for D2 (embedding model) and D7 (one index, 13 languages).

Re-run after any encoder change — especially the ONNX int8 swap, where the
cross-lingual score is the first thing quantization would break.

    python learn/01_embeddings.py

Baseline, fp32:  EN/EN 0.935 | unrelated 0.692 | HI/EN 0.854
"""

import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("intfloat/multilingual-e5-small")

# e5 needs prefixes: "query: " for questions, "passage: " for documents.
# Skipping them quietly costs accuracy.
SENTENCES = [
    "query: How do I train a puppy?",
    "query: What is the best way to train a young dog?",  # same meaning, different words
    "query: The stock market closed higher today.",  # unrelated
    "query: पिल्ले को कैसे प्रशिक्षित करें?",  # same as #0, in Hindi
]

vectors = model.encode(SENTENCES, normalize_embeddings=True)

print(f"vectors shape : {vectors.shape}")
print(f"one vector    : {vectors[0][:5]} ... (384 total)")
print()


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Vectors are already normalized, so the denominator is 1 and dot == cosine."""
    return float(np.dot(a, b))


def report() -> None:
    print(f"0 vs 1  (same meaning, EN)   {cosine(vectors[0], vectors[1]):.3f}")
    print(f"0 vs 2  (unrelated)         {cosine(vectors[0], vectors[2]):.3f}")
    print(f"0 vs 3  (same meaning, HI)  {cosine(vectors[0], vectors[3]):.3f}")


if __name__ == "__main__":
    report()

    same_meaning = cosine(vectors[0], vectors[1])
    unrelated = cosine(vectors[0], vectors[2])
    cross_lingual = cosine(vectors[0], vectors[3])

    assert same_meaning > unrelated, "rewording should beat an unrelated topic"
    assert cross_lingual > unrelated, (
        "the Hindi version of the same question should beat an unrelated English "
        "one — this is what lets one index serve 13 languages (AUDIT D7)"
    )
    print("\n✅ both claims hold")
