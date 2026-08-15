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


class Answer(BaseModel):
    text: str
    passage_id: str
    source: str  # extractive | local | anthropic
    confidence: float
    citations: list[str]
    spans: dict[str, float] = {}
    tool_calls: list[dict] = []  # dispatcher trace (AUDIT §8)


class Abstention(BaseModel):
    """A first-class response, not an error. Knowing when not to answer is a
    deliverable (AUDIT §9)."""

    reason: str  # machine-readable: no_speech | unsafe | off_topic | ungrounded
    message: str
    spans: dict[str, float] = {}
    tool_calls: list[dict] = []


class Evidence(BaseModel):
    """A retrieved parent passage, after fusion. What the answer stage sees."""

    passage_id: str
    text_en: str
    text_translated: str
    query_type: str
    score: float  # fused RRF score — comparable within one query only
    dense_score: float  # best cosine of any chunk of this passage; 0.0 if BM25-only
    views: list[str]  # which views retrieved it, for debugging the ablation
    matched_text: str  # the chunk that actually matched, for extractive answering
