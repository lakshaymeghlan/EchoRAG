"""Answer generation — extractive by default, generative optional (AUDIT §2.4, §7).

Path A (extractive) always runs and always fits the budget. Path B (a model)
races the remaining deadline and is dropped if it loses.
"""

import os
import re

import numpy as np

from echorag import embed, guards, harness, tools
from echorag.index import split_sentences
from echorag.schemas import Abstention, Answer, Evidence


def _source_text(query: str, ev: Evidence) -> str:
    """Answer in the language the user asked in, when we have that text."""
    if not query.isascii() and ev.text_translated:
        return ev.text_translated
    return ev.text_en


_WORD = re.compile(r"\w+", re.UNICODE)

SHORTLIST = 3  # sentences worth paying to embed

# Below this top-1 cosine the first search is judged weak enough to widen.
# Sits just under the measured in-corpus minimum (EN 0.842 / HI 0.813).
WIDEN_BELOW = 0.78
WIDEN_MIN_BUDGET_MS = 130  # a second hop plus the answer stage must both fit


def _lexical_scores(query: str, sentences: list[str]) -> list[float]:
    """Free proxy for relevance: what fraction of the query's words appear.

    Costs ~0.1 ms against ~30 ms/sentence for Devanagari embedding, so it is
    what lets the extractive path stay inside the budget.
    """
    q = set(_WORD.findall(query.lower()))
    if not q:
        return [0.0] * len(sentences)
    return [len(q & set(_WORD.findall(s.lower()))) / len(q) for s in sentences]


def extract(
    query: str,
    evidence: list[Evidence],
    qvec: np.ndarray,
    budget_ms: float = 1e9,
) -> Answer | None:
    """Path A — the sentence of the top passage closest to the query.

    Grounded by construction: the answer is a verbatim span of retrieved text,
    so there is nothing to hallucinate (AUDIT §2.3).

    Two-stage by design. Lexical overlap shortlists cheaply; only the shortlist
    is embedded, and only if the budget allows. Devanagari tokenizes to roughly
    3x the tokens of equivalent English, so embedding every sentence of every
    Hindi passage was costing more than the rest of the pipeline combined.
    """
    if not evidence:
        return None

    top = evidence[0]
    text = _source_text(query, top)
    sentences = split_sentences(text) or [text]

    lex = _lexical_scores(query, sentences)
    order = sorted(range(len(sentences)), key=lambda i: lex[i], reverse=True)
    shortlist = order[:SHORTLIST]

    # Embedding is the upgrade, not the requirement. Out of budget -> ship the
    # lexical pick, which is still a grounded span of the retrieved passage.
    if budget_ms > 40 and len(shortlist) > 1:
        vecs = embed.encode([sentences[i] for i in shortlist], is_query=False)
        scores = vecs @ qvec
        best = shortlist[int(np.argmax(scores))]
        confidence = float(np.max(scores))
    else:
        best = shortlist[0]
        confidence = float(lex[best])

    return Answer(
        text=sentences[best],
        passage_id=top.passage_id,
        source="extractive",
        confidence=confidence,
        citations=[top.passage_id],
    )


async def generate(query: str, evidence: list[Evidence]) -> Answer | None:
    """Path B — optional. Returns None when no generator is configured.

    Off by default: for this corpus the answer is a span of the passage, so a
    model is an upgrade, never a requirement (AUDIT §2.4).
    """
    mode = os.environ.get("ECHORAG_GENERATOR", "none")
    if mode == "none" or not evidence:
        return None
    raise NotImplementedError(f"generator '{mode}' not wired yet")


async def answer_question(query: str, budget_ms: float = harness.BUDGET_MS) -> Answer | Abstention:
    """The full pipeline. Every exit is a valid response — there is no 500.

    Ordering is deliberate: the cheap gates run before retrieval so a garbled or
    unsafe transcript never costs a search.
    """
    d = harness.Deadline(budget_ms)
    spans: dict[str, float] = {}

    # All three are query-only, so they run before retrieval — an unsafe or
    # unanswerable transcript never costs a search.
    for gate in (guards.check_input, guards.check_safety, guards.check_answerable):
        if (stop := gate(query)) is not None:
            stop.spans = {"total": d.elapsed_ms()}
            return stop

    qvec = embed.encode([query], is_query=True)[0]
    spans["embed"] = d.elapsed_ms()

    # Retrieval runs as a validated tool call, not a direct function call, so
    # the same registry serves the rule-driven pipeline and an LLM generator.
    trace: list[dict] = []
    t = d.elapsed_ms()
    call = tools.call("search_corpus", deadline=d, query=query, k=5, widen=False, qvec=qvec)
    trace.append({"tool": call.name, "ok": call.ok, "ms": round(call.latency_ms, 1)})
    evidence = call.evidence

    # Second hop: weak evidence and budget left -> widen the view set and retry.
    # A real multi-step loop, decided by rule here and by the model when a
    # generator is configured.
    weak = not evidence or evidence[0].dense_score < WIDEN_BELOW
    if weak and d.remaining_ms() > WIDEN_MIN_BUDGET_MS:
        again = tools.call("search_corpus", deadline=d, query=query, k=5, widen=True, qvec=qvec)
        trace.append({"tool": again.name, "ok": again.ok, "ms": round(again.latency_ms, 1)})
        if again.ok and again.evidence:
            best = max(evidence + again.evidence, key=lambda e: e.dense_score, default=None)
            if best is not None and (not evidence or best.dense_score > evidence[0].dense_score):
                evidence = again.evidence

    spans["retrieve"] = d.elapsed_ms() - t

    if (stop := guards.check_relevance(query, evidence)) is not None:
        stop.spans = {**spans, "total": d.elapsed_ms()}
        stop.tool_calls = trace
        return stop

    t = d.elapsed_ms()
    result = extract(query, evidence, qvec, budget_ms=d.remaining_ms())
    spans["extract"] = d.elapsed_ms() - t

    # Path B races whatever budget is left. Losing is normal, not an error —
    # the extractive answer already satisfies the SLO (AUDIT §2.3).
    better = await harness.with_deadline(generate(query, evidence), d)
    if better is not None:
        spans["generate"] = d.elapsed_ms() - spans.get("extract", 0)
        if guards.check_grounding(better, evidence) is None:
            result = better  # only accept a model answer that verifies

    if result is None:
        return Abstention(
            reason="off_topic",
            message="I don't have anything on that.",
            spans={**spans, "total": d.elapsed_ms()},
            tool_calls=trace,
        )

    if (stop := guards.check_grounding(result, evidence)) is not None:
        stop.spans = {**spans, "total": d.elapsed_ms()}
        stop.tool_calls = trace
        return stop

    result.spans = {**spans, "total": d.elapsed_ms()}
    result.tool_calls = trace
    return result
