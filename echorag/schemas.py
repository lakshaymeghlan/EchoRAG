"""Typed boundaries — no dicts cross module lines (AUDIT §8)."""

from pydantic import BaseModel


class Transcript(BaseModel):
    text: str
    language_code: str | None = None
    request_id: str | None = None
    latency_ms: float


class Passage(BaseModel):
    """One retrievable unit, flattened out of the nested `passages` dict."""

    passage_id: str  # f"{query_id}:{rank}"
    query_id: int
    text_en: str
    text_translated: str
    query_type: str
    lang: str
    is_gold: bool  # EVAL ONLY — feeding this to retrieval is leakage
    query: str
    query_en: str


class Chunk(BaseModel):
    """What we embed. Many chunks can share one parent Passage."""

    chunk_id: str
    parent_id: str
    text: str
    view: str  # v1 | v2 | v3 | v4
