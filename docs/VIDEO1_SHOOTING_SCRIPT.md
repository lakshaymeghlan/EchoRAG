# Video 1 — shooting script (90 seconds)

Order: folder structure → latency numbers → backend → frontend → the honest bit.
No browser, no UI — that's video 2.

The spoken lines are written the way you'd actually talk, not the way docs are
written. Say them loose. If a word feels wrong in your mouth, change it — the
numbers are the only part that has to stay exact.

---

## Step 0 — before you record (5 min)

One terminal, three tabs, big font, `clear` between takes.

```bash
cd "/Users/lakshaymeghlan/projects/hackaton/ Rag hhGOA/EchoRAG"
```

**Tab 1 — the folders.** Run now, leave it up:

```bash
ls -1 | grep -v __pycache__
wc -l echorag/*.py | sort -n
```

**Tab 2 — the benchmark.** Run this *before* recording. It takes a few minutes
and you want the finished table sitting there, not a progress bar:

```bash
./.venv/bin/python -m bench.latency
```

Scroll so the **ALL** block and `PASS: 300/300 within budget` are both visible.

**Tab 3 — the live one:**

```bash
curl -s -X POST https://echorag.vercel.app/api/ask \
  -F "text=how fast does an eagle travel" | python3 -m json.tool
```

Run it **twice** and show the second. The first is a cold start (~290 ms), the
second is ~91 ms.

**Editor window:** `AUDIT.md`, minimap and sidebar hidden. Practise `Cmd+G` →
`505` until it's instant.

**Start the screen recorder before running the benchmark**, not after — the
recorder itself is CPU load, and CPU contention is what caused every latency
spike we ever chased.

---

## Beat 1 — 0:00–0:12 · what it is, and the folders

**Do:** Tab 1, the `ls -1` output. Run your cursor down the list as you name things.

**Say:**

> "So this is EchoRAG. You ask a question out loud, in Hindi or English, and it
> finds the answer in a real passage and reads it back to you. This is the whole
> repo. `echorag` is the backend, `frontend` is the interface, `bench` is where
> we measure everything, and this audit file is where every decision got written
> down before we built it."

*(57 words)*

---

## Beat 2 — 0:12–0:26 · the backend

**Do:** Same tab, the `wc -l` output, sorted small to large.

**Say:**

> "The backend's about sixteen hundred lines, that's all of it. Retrieve is the
> biggest file. Schemas is just the two things this can hand back — either an
> answer or a refusal. Guards is the safety checks. Harness deals with timeouts.
> And there's no language model in here at all, which was on purpose."

*(56 words)*

---

## Beat 3 — 0:26–0:50 · the numbers

**Do:** Tab 2. Point at the `total` row, then at `PASS: 300/300`.

**Read the numbers off your own screen.** The worst-case figure moves between
runs — I've seen 109 ms and 145 ms, both fine. Everything else is stable.

**Say:**

> "Okay, this is the one that matters. We ran three hundred questions through it.
> Embedding takes about two milliseconds, finding the passage nineteen, pulling
> the answer out eight. So around thirty all in. The worst single one was a
> hundred and forty-five. The budget was two hundred, and all three hundred came
> in under it.
>
> We look at the worst case rather than the average, because if the average is
> fine but one in twenty people waits too long, it's still a slow app.
>
> And to be clear about what that two hundred covers — it's from the text to the
> answer. The speech-to-text bit is a call out to Sarvam and that alone takes
> about half a second. We just report it as its own number instead of pretending
> it isn't there."

*(120 words — the longest beat by far. Don't rush the last paragraph; it's the
part that makes the rest believable.)*

**Only if you have room** — point at the two language blocks:

> "You can see it's a bit slower in Hindi, thirty-one against twenty-eight.
> That's because Hindi turns into roughly three times as many tokens, so there's
> just more to get through. The slowest step in the whole run is Hindi
> extraction."

*(44 words. Cut this first if you're long — but keep it in your head, because if
someone asks what your slowest stage is, that's the answer: Hindi extract,
worst case 112 ms.)*

---

## Beat 4 — 0:50–1:02 · it's actually live

**Do:** Tab 3, `spans` visible in the JSON.

**Say:**

> "And that's not just on my laptop. This is curl hitting the deployed one. You
> get the answer, which passage it came from, and the timing for each step.
> Ninety-one milliseconds, on a free tier."

*(38 words)*

---

## Beat 5 — 1:02–1:14 · the frontend

**Do:** `ls frontend/app frontend/lib`, or the files open in the editor.

**Say:**

> "Frontend's Next.js. This file shows your words in the box while you're still
> talking so it feels responsive, and when you stop the mic it sends the audio
> off. And the meter draws the two hundred milliseconds to scale, so you can
> actually watch the answer land inside it."

*(53 words)*

---

## Beat 6 — 1:14–1:30 · the honest bit

**Do:** Editor, `Cmd+G` → **505**. Heading *"G3 as designed does not work"*
readable. Stop scrolling. Let it sit still.

**Say:**

> "And this section is the one I'd actually point at. It's where we wrote down
> that our own safety check didn't work. The idea was that a bad question would
> pull back bad matches, so we could catch it that way. Then we measured it, and
> the good questions and the bad questions scored about the same. It couldn't
> tell them apart.
>
> And our own test was rigged, honestly — a hundred and twenty good questions
> against eight bad ones. So 'just answer everything' came out on top. We threw
> it away and rebuilt it, and checked the new one against sixty-five hundred real
> queries."

*(110 words. Just stop at the end. Don't add a closing line.)*

---

## Timing

| Beat | Screen | Runs | Words |
|---|---|---|---|
| 1 folders | Tab 1 · `ls -1` | 0:00–0:12 | 57 |
| 2 backend | Tab 1 · `wc -l` | 0:12–0:26 | 56 |
| 3 numbers | Tab 2 · bench.latency | 0:26–0:50 | 120 |
| 4 live | Tab 3 · curl | 0:50–1:02 | 38 |
| 5 frontend | `ls frontend/...` | 1:02–1:14 | 53 |
| 6 honest bit | AUDIT.md line 505 | 1:14–1:30 | 110 |

**434 words in 90 seconds is too many** — that's 290 wpm and you'd be
sprinting. Pick one:

- **Drop the per-language paragraph** in beat 3 (−44) and **the middle paragraph
  of beat 3** about worst case vs average (−32). Lands you near 358 words / 240
  wpm, which is a fast but normal read.
- Or cut beat 5 to one sentence: *"Frontend's Next.js — it shows your words as
  you talk, and the meter draws the budget to scale."* (−30)

**Never cut:** the speech-to-text sentence in beat 3, or beat 6.

Read it aloud with a timer twice before you record. Whatever you naturally skip
on the second read is what should go.

---

## While recording

- **Do the audio in one take.** You can re-record the screen and line it up
  after. A spliced voice track is audible.
- **Don't open the browser.** Brief says process, not product.
- **Scroll slowly.** Fast scrolling turns to mush once it's compressed.
- Fumble a line → stop, restart that beat. Don't apologise on tape.
- Don't mention using AI to build it. Nobody asked, and the measurements are the
  interesting part.

## Numbers you can say — all verified

- Backend **1,610 lines**; `retrieve.py` biggest at 234
- 300 queries local: **P50 30 ms · P95 36 ms · P99 58 ms · worst 145 ms · 300/300 under 200 ms**
  - by language: **EN 28 ms** (n=139) · **HI 31 ms** (n=161), neither went over
  - per step: embed **2 ms** · retrieve **19 ms** · extract **8 ms**
  - slowest step in the run: **Hindi extract, worst case 112.8 ms**
  - outcomes: **294 answered, 6 refused**
  - the worst-case number moves between runs (109 and 145 both seen) — read it off screen
- Live, warm: **P50 91 ms · P95 165 ms · none over budget**
- Speech-to-text measured **513 ms**, reported separately
- The overlapping guardrail scores: in-corpus low **0.842** vs off-topic high **0.887**
- The rigged test: **120 good questions vs 8–10 bad ones**
- Rebuilt gate checked against **6,535 real queries**

## Don't say

- That the live site searches 99,985 passages. The benchmark is on the full
  corpus; the deployed demo runs a smaller slice because it's on a free tier. If
  corpus size comes up at all, say it that way.
- Any made-up number. Everything above is measured and reproducible from the repo.
