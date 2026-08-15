"""Phase 4 exit criterion — fit tau from data, not from feel (AUDIT §9).

    python -m bench.guardrails

Off-topic detection is a binary classifier: in-corpus queries must be answered,
off-corpus ones must be refused. We measure both score distributions, sweep the
threshold, and pick the one with the best F1 — then print the confusion matrix
so the tradeoff is visible rather than asserted.
"""

import argparse
import random

import lancedb

from echorag import embed, retrieve

# Deliberately outside a web-passage corpus: personal, live, local, or nonsense.
OFF_TOPIC_EN = [
    "what is my bank account balance",
    "what did I have for breakfast yesterday",
    "send an email to my manager about the delay",
    "what is the airspeed velocity of an unladen swallow on Jupiter",
    "gorpling flimwaddle zonk",
    "what time is my dentist appointment",
    "should I break up with my girlfriend",
    "what is the wifi password here",
    "play the next song on my playlist",
    "how many pebbles are in my left shoe right now",
]
OFF_TOPIC_HI = [
    "मेरे बैंक खाते में कितने पैसे हैं",
    "कल मैंने नाश्ते में क्या खाया था",
    "मेरे मैनेजर को ईमेल भेजो",
    "यहाँ का वाईफाई पासवर्ड क्या है",
    "मेरा अगला गाना चलाओ",
    "क्या मुझे अपनी नौकरी छोड़ देनी चाहिए",
    "मेरे जूते में कितने पत्थर हैं",
    "फ्लिमवाडल गोर्पलिंग ज़ोंक",
]


def top_score(query: str) -> float:
    qvec = embed.encode([query], is_query=True)[0]
    ev, _ = retrieve.retrieve(query, k=1, qvec=qvec)
    return ev[0].dense_score if ev else 0.0


def in_corpus(index_dir: str, n: int, lang: str) -> list[str]:
    rows = lancedb.connect(index_dir).open_table("passages").search().limit(10**9).to_list()
    seen, qs = set(), []
    for r in rows:
        if r["is_gold"] and r["query_id"] not in seen:
            seen.add(r["query_id"])
            qs.append(r["query"] if lang == "hi" else r["query_en"])
    random.Random(7).shuffle(qs)
    return qs[:n]


def sweep(pos: list[float], neg: list[float]) -> tuple[float, dict]:
    """Pick tau maximising F1. Recall here = 'answered a question we could answer'."""
    best = (0.0, {"f1": -1.0})
    candidates = sorted(set(round(x, 3) for x in pos + neg))
    for tau in candidates:
        tp = sum(s >= tau for s in pos)
        fn = len(pos) - tp
        fp = sum(s >= tau for s in neg)
        tn = len(neg) - fp
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        if f1 > best[1]["f1"]:
            best = (tau, {"f1": f1, "tp": tp, "fn": fn, "fp": fp, "tn": tn})
    return best


def report(lang: str, index_dir: str, n: int) -> None:
    pos_q = in_corpus(index_dir, n, lang)
    neg_q = OFF_TOPIC_HI if lang == "hi" else OFF_TOPIC_EN

    pos = [top_score(q) for q in pos_q]
    neg = [top_score(q) for q in neg_q]

    ps, ns = sorted(pos), sorted(neg)
    print(f"--- {'Hindi' if lang == 'hi' else 'English'} ---")
    print(f"in-corpus  (n={len(ps)})  min {ps[0]:.3f}  p10 {ps[len(ps) // 10]:.3f}  p50 {ps[len(ps) // 2]:.3f}")
    print(f"off-topic  (n={len(ns)})  p50 {ns[len(ns) // 2]:.3f}  p90 {ns[int(len(ns) * 0.9)]:.3f}  max {ns[-1]:.3f}")

    tau, m = sweep(pos, neg)
    print(f"\nbest tau = {tau:.3f}   F1 {m['f1']:.3f}")
    print("                 predicted answer   predicted abstain")
    print(f"  in-corpus  {m['tp']:>14}      {m['fn']:>15}")
    print(f"  off-topic  {m['fp']:>14}      {m['tn']:>15}")
    print(f"\n  answered off-topic (the dangerous error): {m['fp']}/{len(neg)}")
    print(f"  refused answerable (the annoying error)  : {m['fn']}/{len(pos)}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=int, default=120)
    ap.add_argument("--index", default="index")
    args = ap.parse_args()
    for lang in ("en", "hi"):
        report(lang, args.index, args.queries)
