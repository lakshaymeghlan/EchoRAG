"""Typed boundaries. AUDIT.md §8: no dicts cross module lines.

Types arrive as their phase needs them. Query/Evidence/Answer/Abstention land in
Phase 2-4; adding them now would be scaffolding for later (AUDIT.md §0).
"""

from pydantic import BaseModel


class Transcript(BaseModel):
    """Output of the STT stage. The pipeline deadline starts *after* this."""

    text: str
    language_code: str | None = None
    request_id: str | None = None
    latency_ms: float


class Passage(BaseModel):
    """One retrievable unit: a single MS MARCO passage, flattened out of the
    nested `passages` dict (AUDIT.md §5.0). This is the *parent* — chunks made
    by V3/V4 point back at `passage_id`."""

    passage_id: str  # f"{query_id}:{rank}" — stable and reconstructible
    query_id: int
    text_en: str
    text_translated: str
    query_type: str  # case-folded from the dataset's UPPERCASE
    lang: str  # FLORES code, e.g. "hin_Deva"
    is_gold: bool  # from is_selected — EVAL ONLY, never a retrieval input
    query: str  # in-language query, for building the eval set
    query_en: str  # normalized Eng_Query


class Chunk(BaseModel):
    """A unit we embed and index. Several chunks can point at one Passage.

    Retrieval matches on `text`, but the pipeline returns the *parent* passage —
    this is the small-to-big idea (AUDIT.md §5.1 V3).
    """

    chunk_id: str
    parent_id: str  # Passage.passage_id
    text: str
    view: str  # "v1" | "v2" | "v3" | "v4" — which strategy produced it
