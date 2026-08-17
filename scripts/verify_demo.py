"""Find demo queries that are actually safe to say on camera.

    python scripts/verify_demo.py --url https://echorag.vercel.app --n 12

The deployed corpus is a shard, not the full dataset, so most questions a person
invents have no matching passage. Retrieval still returns its nearest neighbour
and the extractor still quotes it, which produces a confidently wrong *related*
answer — "how tall is the eiffel tower" -> "The Eiffel Tower has 108 stories".
That is the documented failure mode (AUDIT), and on camera it reads as a
hallucination even though nothing was generated.

This picks queries whose gold passage is provably in the deployed index, asks
the live API, and checks the cited passage is one the dataset marked gold for
that query. `is_gold` is EVAL ONLY — scoring is the one legitimate use.

A query only PASSes if the live service cited a gold passage. Those are the
ones to script the demo around.
"""

import argparse
import collections
import json
import os
import sys
import urllib.parse
import urllib.request

import lancedb


def gold_by_query(index_dir: str, limit: int) -> list[dict]:
    """Queries that have at least one gold passage present in this index."""
    passages = lancedb.connect(index_dir).open_table("passages")
    rows = (
        passages.search()
        .where("is_gold = true")
        .limit(limit * 40)
        .to_list()
    )

    grouped: dict[str, dict] = {}
    for r in rows:
        q = grouped.setdefault(
            r["query_id"],
            {"query_en": r["query_en"], "query": r["query"], "type": r["query_type"], "gold": set()},
        )
        q["gold"].add(r["passage_id"])
    return list(grouped.values())[:limit]


def ask(url: str, text: str, timeout: float) -> dict:
    body = urllib.parse.urlencode({"text": text}).encode()
    req = urllib.request.Request(
        f"{url.rstrip('/')}/api/ask",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def check(url: str, label: str, text: str, gold: set[str], timeout: float) -> dict:
    try:
        d = ask(url, text, timeout)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "why": f"request failed: {str(exc)[:40]}", "label": label, "q": text}

    cited = set(d.get("citations") or [])
    hit = bool(cited & gold)
    return {
        "ok": hit and d["type"] == "answer",
        "why": (
            "cited gold"
            if hit
            else ("abstained" if d["type"] != "answer" else "cited a NON-gold passage")
        ),
        "label": label,
        "q": text,
        "ms": d["spans"]["total"],
        "text": d.get("text", "")[:60],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://echorag.vercel.app")
    ap.add_argument("--index", default=os.environ.get("ECHORAG_INDEX_DIR", "index"))
    ap.add_argument("--n", type=int, default=12, help="queries per language")
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()

    queries = gold_by_query(args.index, args.n)
    if not queries:
        print(f"no gold passages in {args.index}", file=sys.stderr)
        return 1

    print(f"index    : {args.index}")
    print(f"target   : {args.url}")
    print(f"criterion: live service must cite a passage the dataset marked gold\n")

    results = []
    for q in queries:
        for label, text in (("EN", q["query_en"]), ("HI", q["query"])):
            if not text:
                continue
            r = check(args.url, label, text, q["gold"], args.timeout)
            results.append(r)
            mark = "PASS" if r["ok"] else "----"
            ms = f"{r.get('ms', 0):6.1f}ms" if r.get("ms") is not None else "        "
            print(f"  [{mark}] {label} {ms}  {r['q'][:42]:44} {r['why']}")

    by_lang = collections.Counter(r["label"] for r in results if r["ok"])
    print(f"\nsafe to demo: {sum(by_lang.values())}/{len(results)}  " f"(EN {by_lang['EN']}, HI {by_lang['HI']})")

    good = [r for r in results if r["ok"]]
    if good:
        print("\nScript the demo around these — each cites a verified gold passage:\n")
        for r in sorted(good, key=lambda x: x["label"]):
            print(f"  {r['label']}  {r['q']}")
            print(f"      -> {r['text']}")

    bad = [r for r in results if not r["ok"] and r["why"].startswith("cited a NON")]
    if bad:
        print(f"\nAVOID these {len(bad)} — answered from a non-gold passage, which is")
        print("the confidently-wrong-related-answer failure mode:\n")
        for r in bad[:8]:
            print(f"  {r['label']}  {r['q'][:52]}")
            print(f"      -> {r['text']}")

    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
