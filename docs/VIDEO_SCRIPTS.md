# Video scripts — EchoRAG, HH Goa 2026

Two videos. Read the pre-flight checklist first; one item on it is the
difference between a clean demo and an embarrassing one.

---

## Pre-flight — do this before you hit record

1. **Warm the service.** Open https://echorag.vercel.app and ask one throwaway
   question. Discard it. A cold request measured **290 ms**; warm is **43–135 ms**.
   The first request pays for loading the model, and that is the one that would
   blow the 200 ms budget on camera.
2. **Use only verified queries.** The list below is checked by
   `python scripts/verify_demo.py` — the live service cites a passage the
   dataset itself marked correct. Anything else risks a confidently wrong
   related answer.
3. **Close other apps.** Benchmarks drifted 3x under CPU contention from a
   background build. The same applies to your screen recorder.
4. **Mic check.** Record 5 seconds, play it back. Sarvam transcribes what it
   actually hears, and a bad mic looks like a bad product.
5. **Zoom the browser to ~125%** so the latency numbers are legible after
   compression.

### Verified queries — safe to say on camera

| Lang | Query | Expected answer |
|---|---|---|
| EN | how fast does an eagle travel | Eagles fly 30 to 55 mph and dive at over 100 mph |
| HI | बाज़ कितनी तेजी से यात्रा करता है | the same fact, in Hindi |
| EN | stubhub toll free number | StubHub toll-free number 866-788-2482 |
| HI | स्टबहब टोल फ्री नंबर | the same number, in Hindi |
| EN | what is a corporation? | A corporation is a company or group of people authorized to… |
| EN | how long for cantaloupe to mature | Cantaloupe vines normally take 90 days… |
| HI | ईमानदारी या सच्चाई की परिभाषा | definition of honesty |
| — | what is my bank account balance | **refuses** — `unanswerable_personal` |

### Do NOT say on camera

- `कॉर्पोरेशन क्या है?` — cites a non-gold passage about a government-owned
  corporation, even though the English form of the same question passes.
- `who invented the telephone` — answers "RICHARDSON, Texas — Paragon
  Wireless", which is the failure mode exactly.
- Any question you invented and did not run through `verify_demo.py` first.

---

## Video 1 — Process (90 seconds, hard limit)

The brief asks for **how the team works, not the product**. So: no UI. Show the
repo, the audit doc, terminal output, commits. About 210 spoken words — read it
once out loud and time it before recording.

### 0:00–0:12 — the constraint

**Screen:** `AUDIT.md` open, scrolled to §2.

> "The brief gave us a 200 millisecond budget. Our first move wasn't code — it
> was measuring whether that was even possible. Speech-to-text alone took 513
> milliseconds. So we defined the budget as transcript-to-answer, wrote that
> down, and reported speech-to-text separately instead of quietly folding it in."

### 0:12–0:30 — the audit as a contract

**Screen:** scroll AUDIT.md so the decision entries (D1, D2, D6…) flick past.

> "Everything starts in this file. Every decision gets an entry, a reason, and a
> number. When a decision turned out wrong we didn't delete it — we appended the
> correction underneath. D2.1, D6.1, D9.1 are all reversals we can still read
> back."

### 0:30–0:55 — measure, don't guess

**Screen:** terminal. Run `python -m bench.ablation --queries 300 --lang en`
beforehand and have the finished table on screen.

> "This is the ablation table that decides what ships. One chunking strategy
> looked obviously good on paper. Measured, it was worse on recall, worse on
> ranking, and nine milliseconds slower — so we cut it, and the index got 63%
> smaller. Another test showed that searching both languages at once destroyed
> ranking quality, so each query only searches its own language. Neither of
> those was a guess we'd have got right."

### 0:55–1:15 — what measuring caught

**Screen:** `git log --oneline` scrolling.

> "Measuring also found bugs reading the code never would. A deprecated API that
> returned an object instead of a list, so an index silently never got created.
> A missing Devanagari full stop, which meant Hindi passages never split into
> sentences. A leaked coroutine whenever we ran out of budget."

### 1:15–1:30 — the honest part

**Screen:** AUDIT.md §9.-1, titled "G3 doesn't work as designed".

> "And the section we're most proud of is this one — where we wrote down that
> our own off-topic detector didn't work. It assumed a bad question retrieves
> bad matches; measured, the distributions almost completely overlap. Worse, our
> own calibration was rigged — 120 good questions against eight bad ones, so
> 'always answer' scored best. We rebuilt it as an intent gate and validated
> that against 6,535 real queries. Writing that down is the process."

See `VIDEO1_SHOOTING_SCRIPT.md` for this video beat-by-beat, with the exact
`AUDIT.md` line numbers to jump to and per-beat word counts.

**Tips**

- Show real scrolling and real terminal output. Do not fake a progress bar.
- If two of you are on camera, split it: one takes 0:00–0:30, the other 0:30–end.
- 90 seconds is a hard limit. Read it aloud twice and cut a sentence if you run
  over, rather than speaking faster.

---

## Video 2 — Demo (aim for 2:00–2:30)

End to end, and let the numbers be visible the whole time.

### 0:00–0:15 — what it is

**Screen:** https://echorag.vercel.app, freshly loaded (already warmed).

> "This is EchoRAG. You ask a question out loud, in Hindi or English, and it
> answers from a retrieved passage — with the latency for every stage shown on
> screen. One URL serves both the interface and the API."

### 0:15–0:45 — voice, English

**Action:** click the mic, say **"how fast does an eagle travel"**, stop.

> "As I speak, the transcript appears live in the box. When I stop the mic, it
> sends automatically."

Let the answer land, then point at the meter.

> "Eagles fly 30 to 55 miles per hour. And that number there is the whole
> pipeline — embed, retrieve, extract — against the 200 millisecond budget drawn
> to scale."

### 0:45–1:15 — the same question in Hindi

**Action:** mic, say **"बाज़ कितनी तेजी से यात्रा करता है"**, stop.

> "Now the same question in Hindi. Not a translation layer — the same index, the
> same model. Hindi and English passages live in one shared vector space, so a
> Hindi question finds the Hindi passage directly."

Same fact comes back in Devanagari.

> "Same fact, same speed, different language."

### 1:15–1:45 — the refusal (do not skip this)

**Action:** type **"what is my bank account balance"**.

> "This one it should refuse — and refusing is a feature, not an error. It
> returns a typed abstention with a reason: unanswerable, personal. It never
> reached retrieval, which is why it took under a millisecond."

> "That matters because of how answers are produced: we don't generate them.
> There is no language model in the answer path. Every answer is a verbatim span
> copied out of a retrieved passage, with the passage ID cited — so there is
> nothing to hallucinate. When we can't ground an answer, we say so instead of
> inventing one."

### 1:45–2:15 — under the hood

**Screen:** open `https://echorag.vercel.app/api/health`, then a terminal with:

```bash
curl -s -X POST https://echorag.vercel.app/api/ask \
  -F "text=stubhub toll free number" | python3 -m json.tool
```

> "It's a real API, not just a demo page. Health check, and the same question
> over curl — you get the answer, the cited passage ID, per-stage timings, and
> the tool calls it made."

Then show `bench/results.md` or the latency table.

> "Benchmarked on the full corpus — just under 100,000 passages across both
> languages — recall at 10 is 0.967 and 300 out of 300 queries came in under the
> 200 millisecond budget, P50 at 29 milliseconds. The hosted demo runs a smaller
> shard of that corpus because it's on a free tier; the benchmark numbers are
> from the full index and anyone can reproduce them from the repo."

### Closing

> "Voice in, grounded answer out, under the budget, in two languages — and it
> tells you when it doesn't know."

**Tips**

- Say the refusal line with conviction. Most submissions will not have one, and
  "it tells you when it doesn't know" is the line judges remember.
- Keep the latency meter in frame for every query.
- Do not claim the live demo searches 100,000 passages. Say the benchmark is on
  the full corpus and the free-tier demo runs a shard. It's true, it's
  defensible, and someone will check.
- If a query misbehaves mid-take, stop and restart. Do not narrate around it.

---

## Submission

Google Form before **18:00 IST, 22 August 2026**. No resubmissions.

- **GitHub:** https://github.com/lakshaymeghlan/EchoRAG
- **Live:** https://echorag.vercel.app
- **Videos:** both of the above

Also required: both videos posted to Instagram, X and LinkedIn by **every team
member**, each including **#RAGInGoa**, with at least one public Instagram
account.

Final check before submitting: open the live link in a private window on
**mobile data**, not your home wifi. It's the only way to confirm a judge on a
phone sees what you see.
