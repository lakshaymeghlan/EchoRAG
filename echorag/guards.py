"""Guardrails — four gates, each returning a typed Abstention (AUDIT §9).

Knowing when NOT to answer is a deliverable, not an error path.
"""

import re

from echorag.schemas import Abstention, Answer, Evidence

MIN_TOKENS = 2

# Placeholders. bench/guardrails.py fits these from the measured score
# distributions and writes the confusion matrix (AUDIT §9.0). Two thresholds,
# not one: cross-lingual scores sit systematically ~0.08 below same-language
# ones, so a single global value abstains more on Hindi than on English.
TAU_EN = 0.80
TAU_INDIC = 0.72

GROUNDING_MIN_OVERLAP = 0.5

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


def check_relevance(query: str, evidence: list[Evidence]) -> Abstention | None:
    """G3 — the retriever is the out-of-domain detector.

    If nothing in the corpus is close to the query, the honest answer is that
    we don't know — not a confident answer built on the least-bad match.
    """
    if not evidence:
        return Abstention(reason="off_topic", message="I don't have anything on that.")
    if evidence[0].dense_score < tau_for(query):
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
