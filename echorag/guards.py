"""Guardrails — four gates, each returning a typed Abstention (AUDIT §9).

Knowing when NOT to answer is a deliverable, not an error path.
"""

import re

from echorag.schemas import Abstention, Answer, Evidence

MIN_TOKENS = 2

# A nonsense floor, NOT the off-topic gate. Retrieval score cannot separate
# answerable from unanswerable on a broad web corpus — the distributions overlap
# almost entirely (AUDIT §9.-1). Intent does that job; this only catches strings
# that match nothing at all. Set below the measured in-corpus minimum
# (EN 0.842 / HI 0.813) so it never refuses a real question.
TAU_EN = 0.78
TAU_INDIC = 0.75

GROUNDING_MIN_OVERLAP = 0.5

# What a static corpus structurally cannot answer, whatever it retrieves.
# False-positive rates measured over 6,535 real corpus queries — each rule is
# under 2%, so the cost in wrongly-refused questions is small.
_UNANSWERABLE = (
    # personal data we do not hold (EN 0.4% / HI 0.8% FP)
    (re.compile(r"\b(my|mine)\b|मेरा|मेरे|मेरी|मुझे|मैंने", re.I), "personal"),
    # an action, not a question (EN 0.0% / HI 0.0% FP)
    (
        re.compile(
            r"^\s*(send|play|book|call|email|remind|open|buy|order|text|set)\b"
            r"|भेजो|चलाओ|बुक करो|खोलो",
            re.I,
        ),
        "action",
    ),
    # live state a static corpus cannot know (EN 0.2% / HI 1.9% FP).
    # कल is deliberately excluded — it means both yesterday and tomorrow and is
    # common in ordinary questions.
    (
        re.compile(r"\b(right now|today|tonight|currently|this week|yesterday)\b|अभी", re.I),
        "live",
    ),
)

_UNSAFE = re.compile(
    r"\b(kill|suicide|bomb|explosive|weapon|hack into|steal|credit card number)\b", re.I
)
_WORD = re.compile(r"\w+", re.UNICODE)


def tau_for(query: str) -> float:
    return TAU_EN if query.isascii() else TAU_INDIC


def check_input(transcript: str) -> Abstention | None:
    """G1 — did we actually get a question?"""
    text = transcript.strip()
    if not text:
        return Abstention(reason="no_speech", message="I didn't catch that — please try again.")
    if len(_WORD.findall(text)) < MIN_TOKENS:
        return Abstention(reason="no_speech", message="That was too short to understand.")
    return None


def check_safety(transcript: str) -> Abstention | None:
    """G2 — refuse before retrieving, so unsafe queries never touch the corpus."""
    if _UNSAFE.search(transcript):
        return Abstention(reason="unsafe", message="I can't help with that.")
    return None


def check_answerable(query: str) -> Abstention | None:
    """G3a — intent gate, runs BEFORE retrieval.

    "What is my bank balance" retrieves passages about bank balances at 0.857 —
    indistinguishable by score from a real question (AUDIT §9.-1). It is not
    out-of-domain, it is unanswerable: it needs data we do not have. That is a
    property of the query, so we detect it from the query.
    """
    for pattern, kind in _UNANSWERABLE:
        if pattern.search(query):
            return Abstention(
                reason=f"unanswerable_{kind}",
                message={
                    "personal": "I don't have access to your personal information.",
                    "action": "I can answer questions, but I can't perform actions.",
                    "live": "I can't look up live or real-time information.",
                }[kind],
            )
    return None


MIN_LEXICAL_OVERLAP = 0.2


def check_relevance(query: str, evidence: list[Evidence]) -> Abstention | None:
    """G3b — nonsense backstop, runs after retrieval.

    Demoted from the primary off-topic gate: it catches strings that match
    nothing, not questions about things we lack.

    Cosine cannot detect gibberish — the encoder maps any string somewhere, and
    "somewhere" is always within ~0.85 of something. Lexical grounding can: real
    queries share 40-100% of their words with what they retrieve, invented words
    share 0%.

    Measured ASCII-only. On Devanagari the same signal gives real p50 1.00 /
    min 0.85 against nonsense p50 0.84 / max 0.86 — no separation — so applying
    it there would refuse real questions to catch nothing (AUDIT §9.1).
    """
    if not evidence:
        return Abstention(reason="off_topic", message="I don't have anything on that.")

    if evidence[0].dense_score < tau_for(query):
        return Abstention(
            reason="off_topic",
            message="That doesn't appear to be in the knowledge base.",
        )

    if query.isascii():
        words = set(_WORD.findall(query.lower()))
        corpus: set[str] = set()
        for e in evidence[:5]:
            corpus |= set(_WORD.findall((e.text_en + " " + e.text_translated).lower()))
        if words and len(words & corpus) / len(words) < MIN_LEXICAL_OVERLAP:
            return Abstention(
                reason="off_topic",
                message="That doesn't appear to be in the knowledge base.",
            )

    return None


def check_grounding(answer: Answer, evidence: list[Evidence]) -> Abstention | None:
    """G4 — the anti-hallucination gate.

    Two conditions: the cited passage must be one we actually retrieved, and
    the answer's words must appear in it. Extractive answers pass trivially —
    that is the point. A model's answer has to earn it.
    """
    retrieved = {e.passage_id for e in evidence}
    if not set(answer.citations) or not set(answer.citations) <= retrieved:
        return Abstention(
            reason="ungrounded",
            message="I couldn't verify that against the source.",
        )

    cited = next((e for e in evidence if e.passage_id == answer.citations[0]), None)
    if cited is None:
        return Abstention(reason="ungrounded", message="I couldn't verify that.")

    answer_words = set(_WORD.findall(answer.text.lower()))
    if not answer_words:
        return Abstention(reason="ungrounded", message="Empty answer.")

    source_words = set(_WORD.findall((cited.text_en + " " + cited.text_translated).lower()))
    overlap = len(answer_words & source_words) / len(answer_words)

    if overlap < GROUNDING_MIN_OVERLAP:
        return Abstention(
            reason="ungrounded",
            message="I couldn't verify that against the source.",
        )
    return None
