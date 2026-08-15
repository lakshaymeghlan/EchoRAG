"""Tool registry and dispatcher (AUDIT §8).

Retrieval is not called directly by the pipeline — it is invoked as a *tool*
through this registry, which validates inputs against a JSON schema, enforces
the deadline, retries transient failures, and records a structured trace.

The same registry serves both callers:
  - the default pipeline, which decides which tool to call by rule
  - an LLM generator (ECHORAG_GENERATOR=anthropic), which gets `SCHEMAS`
    verbatim as its `tools` parameter and decides for itself

so tool calling is a live code path with no generator configured, rather than a
capability that only exists when a key is present.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from echorag import retrieve
from echorag.schemas import Evidence

# Anthropic-compatible tool definitions. strict=True guarantees the input
# validates exactly, so the dispatcher never sees a malformed call.
SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_corpus",
        "description": (
            "Search the MSMARCO-XI passage corpus and return the best-matching "
            "passages. Call this whenever answering needs information from the "
            "corpus rather than from the conversation."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "k": {"type": "integer", "description": "How many passages to return."},
                "widen": {
                    "type": "boolean",
                    "description": (
                        "Search deeper — consider many more candidates per view before "
                        "fusing. Slower; use only when a first search returned weak "
                        "results."
                    ),
                },
            },
            "required": ["query", "k", "widen"],
            "additionalProperties": False,
        },
    },
    {
        "name": "lookup_passage",
        "description": "Fetch one passage by id, to quote or verify it.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"passage_id": {"type": "string"}},
            "required": ["passage_id"],
            "additionalProperties": False,
        },
    },
]

_SCHEMA_BY_NAME = {s["name"]: s for s in SCHEMAS}


@dataclass
class ToolResult:
    """Structured result. Errors are values, not exceptions — a failed tool call
    is information the caller acts on, not a crash (AUDIT §8 fallback chain)."""

    name: str
    ok: bool
    latency_ms: float
    evidence: list[Evidence] = field(default_factory=list)
    error: str | None = None
    attempts: int = 1


class ToolError(RuntimeError):
    pass


def _search_corpus(query: str, k: int = 5, widen: bool = False, qvec=None) -> list[Evidence]:
    # Widening deepens the candidate pool rather than adding views: the ablation
    # measured V2 as noise for English queries (-2.0 recall), so "search every
    # view" would make exactly the queries we are trying to rescue worse.
    evidence, _ = retrieve.retrieve(query, k=k, per_view=60 if widen else 20, qvec=qvec)
    return evidence


def _lookup_passage(passage_id: str, **_: Any) -> list[Evidence]:
    _, passages = retrieve._tables()
    rows = passages.search().where(f"passage_id = '{passage_id}'").limit(1).to_list()
    if not rows:
        return []
    p = rows[0]
    return [
        Evidence(
            passage_id=p["passage_id"],
            text_en=p["text_en"],
            text_translated=p["text_translated"],
            query_type=p["query_type"],
            score=1.0,
            dense_score=1.0,
            views=["lookup"],
            matched_text=p["text_en"],
        )
    ]


REGISTRY: dict[str, Callable[..., list[Evidence]]] = {
    "search_corpus": _search_corpus,
    "lookup_passage": _lookup_passage,
}


def _validate(name: str, args: dict[str, Any]) -> None:
    schema = _SCHEMA_BY_NAME.get(name)
    if schema is None:
        raise ToolError(f"unknown tool '{name}'")
    props = schema["input_schema"]["properties"]
    unknown = set(args) - set(props) - {"qvec"}
    if unknown:
        raise ToolError(f"{name}: unexpected arguments {sorted(unknown)}")
    types = {"string": str, "integer": int, "boolean": bool}
    for key, value in args.items():
        expected = types.get(props.get(key, {}).get("type", ""))
        # bool is a subclass of int in Python, so check it before integer.
        if expected and not isinstance(value, expected):
            raise ToolError(f"{name}.{key}: expected {props[key]['type']}")


def call(name: str, deadline=None, attempts: int = 2, **args: Any) -> ToolResult:
    """Invoke a tool with validation, deadline awareness and bounded retry."""
    started = time.perf_counter()

    try:
        _validate(name, args)
    except ToolError as exc:
        return ToolResult(name, False, (time.perf_counter() - started) * 1000, error=str(exc))

    if deadline is not None and deadline.expired():
        return ToolResult(name, False, 0.0, error="deadline expired before call")

    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            evidence = REGISTRY[name](**args)
            return ToolResult(
                name, True, (time.perf_counter() - started) * 1000, evidence, attempts=attempt
            )
        except Exception as exc:  # a tool failing must not take the request down
            last = exc
            if deadline is not None and deadline.expired():
                break

    return ToolResult(
        name,
        False,
        (time.perf_counter() - started) * 1000,
        error=f"{type(last).__name__}: {last}",
        attempts=attempts,
    )


if __name__ == "__main__":
    from echorag.harness import Deadline

    r = call("search_corpus", query="what is a corporation?", k=3, widen=False)
    assert r.ok and r.evidence, r.error
    print(f"✅ search_corpus  {len(r.evidence)} passages  {r.latency_ms:.1f}ms")

    top = r.evidence[0].passage_id
    r2 = call("lookup_passage", passage_id=top)
    assert r2.ok and r2.evidence[0].passage_id == top
    print(f"✅ lookup_passage {top}  {r2.latency_ms:.1f}ms")

    bad = call("search_corpus", query="x", k="three", widen=False)
    assert not bad.ok and "expected integer" in (bad.error or "")
    print(f"✅ schema validation rejects bad input: {bad.error}")

    assert not call("nope", query="x").ok
    print("✅ unknown tool rejected")

    expired = Deadline(budget_ms=0)
    assert not call("search_corpus", deadline=expired, query="x", k=1, widen=False).ok
    print("✅ expired deadline blocks the call")
