# Video 1 — exact shooting script (90 seconds)

Structure you asked for: **folder structure → live latency command → how the
backend was built → how the frontend was built.** No product UI; the browser
stays closed. Everything below is real and checked.

90 seconds is brutally short for four topics, so every beat has a word count.
Total is 340 words ≈ 227 wpm, a brisk but natural read.

---

## Step 0 — prep before recording (5 minutes)

**One terminal, three tabs.** Font large, `clear` before each take.

```bash
cd "/Users/lakshaymeghlan/projects/hackaton/ Rag hhGOA/EchoRAG"
```

**Tab 1 — folder structure.** Run it now and leave the output on screen:

```bash
ls -1 | grep -v __pycache__
wc -l echorag/*.py | sort -n
```

**Tab 2 — the latency benchmark.** This is your money shot. Run it *before*
recording; it takes minutes and you want the finished table:

```bash
./.venv/bin/python -m bench.latency
```

Ends with `PASS: 300/300 within budget`. Scroll so the summary block and that
PASS line are both visible.

**Tab 3 — the live check.** Warm it first, then run:

```bash
curl -s -X POST https://echorag.vercel.app/api/ask \
  -F "text=how fast does an eagle travel" | python3 -m json.tool
```

You want the `spans` object visible: `embed`, `retrieve`, `extract`, `total`.

> Run it twice. The first is a cold start (~290 ms). The second is ~91 ms. Show
> the second.

**Editor:** `AUDIT.md` open in a second window, minimap and file tree hidden.
Practise `Cmd+G` → `505` (the "G3 does not work" section) until it's instant.

---

## Beat 1 — 0:00 to 0:12 · what it is and the structure

**Do:** Tab 1, the `ls -1` output. Move your cursor down the list as you name
things.

**Say:**

> "EchoRAG — ask a question out loud in Hindi or English, get an answer quoted
> from a real passage. Here's the whole repo. `echorag` is the backend,
> `frontend` is the interface, `bench` is how we measure everything, and
> `AUDIT.md` is the design document every decision goes into before it gets
> built."

*(52 words)*

---

## Beat 2 — 0:12 to 0:26 · the backend, by size

**Do:** Same tab, the `wc -l echorag/*.py` output — sorted, so it reads small to
large.

**Say:**

> "The entire backend is sixteen hundred lines. Retrieval is the biggest file at
> two hundred and thirty. `schemas` defines the two things this can return — an
> answer, or a typed refusal. `guards` is the guardrails. `harness` is the
> deadline and the circuit breaker. And there's deliberately no language model
> anywhere in here."

*(52 words)*

---

## Beat 3 — 0:26 to 0:48 · the latency proof

**Do:** Switch to Tab 2 with the finished `bench.latency` table. Point at the
`total` row, then at `PASS: 300/300`.

**Say:** (read the numbers off *your* screen — P100 moves between runs, 109 ms
and 145 ms both observed. Everything else is stable.)

> "Three hundred queries, warm-up discarded, timed per stage. Embed two
> milliseconds, retrieval nineteen, extraction eight. Total P50 thirty
> milliseconds, P95 thirty-six, worst case a hundred and forty-five — against a
> two hundred millisecond budget. Three hundred out of three hundred inside it.
> We target P100, not P50, because a good median with a fat tail still misses the
> budget for one user in twenty.
>
> And to be straight about it: that budget is transcript to answer.
> Speech-to-text is a network call to Sarvam and measured five hundred and
> thirteen milliseconds on its own. We report it separately instead of hiding it."

*(97 words — the longest beat. Do not rush the last sentence; it's the one that
buys you credibility.)*

**Optional, if you have room** — point at the two per-language blocks:

> "Split by language on purpose. English P50 twenty-eight, Hindi thirty-one.
> Hindi is consistently slower and we know why: Devanagari tokenizes to about
> three times as many tokens, so embedding and extraction both do more work.
> That's why the whole tail sits in Hindi extraction."

*(46 words. Cut this first if you're over time — but if a judge asks what your
slowest stage is, this is the answer: Hindi extract, P100 112.8 ms.)*

---

## Beat 4 — 0:48 to 1:02 · it's live, not just local

**Do:** Tab 3, the curl output with `spans` visible.

**Say:**

> "Same thing against the deployed service — this is curl, not a demo page. You
> get the answer, the passage ID it came from, and the timing for every stage.
> Ninety-one milliseconds on a free serverless tier, still under budget."

*(41 words)*

---

## Beat 5 — 1:02 to 1:14 · the frontend

**Do:** Editor or Tab 1, `ls frontend/app frontend/lib`.

**Say:**

> "The frontend is Next.js, exported static. `useSpeechPreview` shows your words
> in the box as you speak so it feels live, then the recorder sends the audio to
> Sarvam when you stop the mic. The latency meter draws the two hundred
> millisecond budget to scale, so you can see the answer land inside it."

*(52 words)*

---

## Beat 6 — 1:14 to 1:30 · the honest part

**Do:** Editor window, `Cmd+G` → **505**. The heading *"G3 as designed does not
work"* readable. Stop scrolling and let it sit.

**Say:**

> "And this is the section we're most proud of — where we wrote down that our own
> guardrail didn't work. It assumed a bad question retrieves bad matches. We
> measured it; the distributions overlap almost completely. Worse, our own test
> was rigged — a hundred and twenty good questions against eight bad ones, so
> 'always answer' scored best. We rebuilt it and validated against six and a half
> thousand real queries. That's the process."

*(67 words. End on "That's the process." Stop. No sign-off.)*

---

## Timing table

| Beat | Screen | Runs | Words |
|---|---|---|---|
| 1 structure | Tab 1 · `ls -1` | 0:00–0:12 | 52 |
| 2 backend | Tab 1 · `wc -l` | 0:12–0:26 | 48 |
| 3 latency | Tab 2 · bench.latency | 0:26–0:48 | 80 |
| 4 live | Tab 3 · curl | 0:48–1:02 | 41 |
| 5 frontend | `ls frontend/...` | 1:02–1:14 | 52 |
| 6 honesty | AUDIT.md line 505 | 1:14–1:30 | 67 |

**340 words / 90 s.** Read it aloud with a timer twice.

**If you run over**, cut in this order:
1. The `spans` sentence in beat 4 ("You get the answer, the passage ID…").
2. The `harness` clause in beat 2.
3. Never cut beat 3's speech-to-text disclosure or beat 6.

---

## Rules

- **Audio in one take.** Re-record screen capture and align it after; a spliced
  voice track is audible.
- **Never open the browser.** The brief says process, not product — the UI is
  video 2's job.
- **Scroll slowly.** Fast scrolling turns to mush after compression.
- Fumble a line → stop, restart that beat. Don't apologise on tape.
- Don't say "we used AI to build it". Nobody asked; the measurements are the story.

## Numbers you may say — all verified

- Backend **1,610 lines**; `retrieve.py` largest at 234
- Local, 300 queries: **P50 30 ms · P95 36 ms · P99 58 ms · P100 145 ms · 300/300 under 200 ms**
  - by language: **EN P50 28 ms** (n=139) · **HI P50 31 ms** (n=161), both 0 over budget
  - stage split: embed **2 ms** · retrieve **19 ms** · extract **8 ms**
  - slowest stage in the run: **Hindi extract, P100 112.8 ms** — that is the tail
  - outcomes: **294 answered, 6 refused**
  - P100 varies run to run (109 and 145 both seen). Read it off the screen.
- Live warm: **P50 91 ms · P95 165 ms · 0/20 over budget**
- STT measured **513 ms**, reported separately
- Off-topic detection: in-corpus min **0.842** vs off-topic max **0.887** — overlapping
- Rigged calibration: **120 positives vs 8–10 negatives**
- Rebuilt gate validated on **6,535 real queries**

## Do not say

- That the live demo searches 99,985 passages. The benchmark is on the full
  corpus; the hosted demo runs a smaller shard on a free tier. If you mention
  corpus size at all, say it that way.
