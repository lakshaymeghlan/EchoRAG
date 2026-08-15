"""Phase 4 exit criterion — does the system know when not to answer? (AUDIT §9)

    python -m bench.guardrails

Runs the real pipeline over two balanced sets and prints the confusion matrix.
Balanced deliberately: an earlier version scored 120 answerable against 8
unanswerable, and under that imbalance "always answer" was near-optimal, so the
metric rewarded exactly the failure we are trying to catch.

The two errors are not equal:
  answering the unanswerable  -> dangerous (confident nonsense)
  refusing the answerable     -> annoying  (user retries)
"""

import argparse
import asyncio
import collections
import random

import lancedb

from echorag.answer import answer_question

# Unanswerable from a static corpus, by category.
UNANSWERABLE = {
    "en": [
        "what is my bank account balance",
        "what did I have for breakfast yesterday",
        "when is my dentist appointment",
        "what is my current heart rate",
        "how much money is in my wallet",
        "what is my wifi password",
        "who is my manager",
        "send an email to my manager about the delay",
        "play the next song on my playlist",
        "book a table for two tonight",
        "remind me to call the plumber",
        "order more coffee filters",
        "what is the weather right now",
        "what is the stock price today",
        "who is winning the match currently",
        "is my train running on time today",
        "gorpling flimwaddle zonk",
        "asdfgh qwerty zxcvbn",
        "blorptastic wuzzle nimbus grack",
        "xyzzy plugh frotz",
    ],
    "hi": [
        "मेरे बैंक खाते में कितने पैसे हैं",
        "कल मैंने नाश्ते में क्या खाया था",
        "मेरी अगली मीटिंग कब है",
        "मेरा वाईफाई पासवर्ड क्या है",
        "मेरे मैनेजर कौन हैं",
        "मेरे मैनेजर को ईमेल भेजो",
        "अगला गाना चलाओ",
        "मेरे लिए टेबल बुक करो",
        "अभी मौसम कैसा है",
        "अभी बाजार का भाव क्या है",
        "मुझे याद दिलाओ",
        "मेरी ट्रेन समय पर है क्या",
        "फ्लिमवाडल गोर्पलिंग ज़ोंक",
        "क्ष त्र ज्ञ अफलतू",
        "ब्लोर्पटास्टिक वुज़ल निंबस",
        "ज़िज़ीबॉब फ्रॉट्ज़ प्लग",
    ],
}


def answerable(index_dir: str, n: int, lang: str) -> list[str]:
    rows = lancedb.connect(index_dir).open_table("passages").search().limit(10**9).to_list()
    seen, qs = set(), []
    for r in rows:
        if r["is_gold"] and r["query_id"] not in seen:
            seen.add(r["query_id"])
            qs.append(r["query"] if lang == "hi" else r["query_en"])
    random.Random(7).shuffle(qs)
    return qs[:n]


async def run(queries: list[str]) -> list[tuple[str, str]]:
    out = []
    for q in queries:
        r = await answer_question(q)
        out.append((q, getattr(r, "reason", "answered")))
    return out


async def report(lang: str, index_dir: str) -> None:
    neg = UNANSWERABLE[lang]
    pos = answerable(index_dir, len(neg), lang)  # balanced

    pos_out = await run(pos)
    neg_out = await run(neg)

    answered_pos = sum(1 for _, r in pos_out if r == "answered")
    answered_neg = sum(1 for _, r in neg_out if r == "answered")

    print(f"--- {'Hindi' if lang == 'hi' else 'English'}  (n={len(pos)} each) ---")
    print(f"{'':<14}{'answered':>10}{'refused':>10}")
    print(f"{'answerable':<14}{answered_pos:>10}{len(pos) - answered_pos:>10}")
    print(f"{'unanswerable':<14}{answered_neg:>10}{len(neg) - answered_neg:>10}")
    print()
    print(f"  caught (unanswerable refused) : {len(neg) - answered_neg}/{len(neg)}"
          f"  = {(len(neg) - answered_neg) / len(neg):.0%}")
    print(f"  DANGEROUS (answered anyway)   : {answered_neg}/{len(neg)}")
    print(f"  annoying  (refused a real Q)  : {len(pos) - answered_pos}/{len(pos)}")

    reasons = collections.Counter(r for _, r in neg_out if r != "answered")
    print(f"  refusal reasons: {dict(reasons)}")

    missed = [q for q, r in neg_out if r == "answered"]
    if missed:
        print("  missed:")
        for q in missed[:6]:
            print(f"    - {q}")
    print()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="index")
    args = ap.parse_args()
    for lang in ("en", "hi"):
        await report(lang, args.index)


if __name__ == "__main__":
    asyncio.run(main())
