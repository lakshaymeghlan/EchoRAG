# Video 1 — exact shooting script (90 seconds)

Every line number below is real and checked against `AUDIT.md` (812 lines). Every
number in the spoken text is one we actually measured.

No product, no UI, no browser. Editor and terminal only.

---

## Step 0 — set up before you record (5 minutes)

**Window layout.** Two windows only, and practise the switch:

- **Window A** — editor with `AUDIT.md` open. Nothing else in the tab bar.
- **Window B** — terminal, font size up, cleared.

**Prepare the terminal output now, so you never wait on camera.** The ablation
takes minutes to run; you are going to show a finished table, not a spinner.

```bash
cd "/Users/lakshaymeghlan/projects/hackaton/ Rag hhGOA/EchoRAG"

# Tab 1 — the ablation table (takes a few minutes; leave the result on screen)
./.venv/bin/python -m bench.ablation --queries 300 --lang en

# Tab 2 — the commit history, already scrolled to the top
git log --oneline | head -40
```

**Editor settings:** hide the minimap and the file tree, turn on word wrap. Zoom
until roughly 40 lines fill the screen — text must survive compression.

**Practise these four jumps** (`Cmd+G`, type the number, Enter):

| Beat | Go to line | What is there |
|---|---|---|
| 1 | **47** | §2.1 "What the full process can honestly mean" |
| 2 | **212** | D2.1 / D6.1 — corrections from Phase 1 measurement |
| 3 | **368** | §5.2 Ablation result — V3 cut |
| 4 | **505** | §9.-1 "G3 as designed does not work" |

Do a silent dry run of all four jumps before recording. Fumbling for a line on
camera costs you five of your ninety seconds.

---

## Beat 1 — 0:00 to 0:14 · the constraint

**Do:** Window A, `AUDIT.md` at **line 47**. The bold line
*"STT cannot be inside 200 ms"* should be visible. Scroll slowly, about three
lines, while you talk.

**Say:**

> "The brief gave us a 200 millisecond budget. Before writing any code we
> measured whether that was even possible — and it isn't. Speech-to-text alone
> measured 513 milliseconds, because it's a network round trip to a third party.
> So we wrote down exactly what we commit to: transcript in hand, to answer
> leaving the server. And we report speech-to-text as its own number, next to
> it, instead of quietly folding it in."

*(Beat is ~62 words. Do not rush it — this is the sentence that establishes you
measured before you built.)*

---

## Beat 2 — 0:14 to 0:32 · the audit as a contract

**Do:** `Cmd+G` → **212**. Land on "D2.1 / D6.1 — corrections from Phase 1
measurement". Scroll up a few lines so **D9.1** is briefly visible too.

**Say:**

> "Every decision lives in this file with a reason and a number. And when a
> decision turned out to be wrong, we didn't delete it — we appended the
> correction underneath it. D2.1, D6.1, D9.1 are all reversals. You can still
> read what we believed, what the measurement said, and what we changed. The
> document is a record, not a brochure."

*(~58 words.)*

---

## Beat 3 — 0:32 to 0:56 · measure, don't guess

**Do:** Switch to Window A **line 368** for two seconds so the ablation table is
on screen, then switch to Window B tab 1 with the finished `bench.ablation`
output. Put the cursor near the `V1 only` row.

**Say:**

> "This is the table that decides what ships. Sentence-window chunking is a
> textbook technique and we expected it to win. Measured, it lowered Hindi
> recall, lowered ranking quality, and cost nine milliseconds — worse on every
> axis. So we cut it, and the index got sixty-three percent smaller.
>
> The same table showed searching both languages at once destroys ranking. So
> each query now searches only its own language. Neither of those is a guess
> we'd have got right."

*(~74 words. The phrase "worse on every axis" is the one to land.)*

---

## Beat 4 — 0:56 to 1:14 · what measuring caught

**Do:** Window B tab 2, `git log --oneline`. Scroll it slowly and continuously
while you speak. Nobody reads it; the motion signals real history.

**Say:**

> "Measuring also found bugs that reading the code never would. A deprecated
> database call that returned an object instead of a list — so a check silently
> passed and an index never got built. A missing Devanagari full stop, which
> meant Hindi passages never split into sentences at all. And a leaked coroutine
> every time we ran out of budget mid-request. None of those three throw an
> error. They just quietly make the system worse."

*(~66 words.)*

---

## Beat 5 — 1:14 to 1:30 · the honest part

**Do:** `Cmd+G` → **505**. The heading *"G3 as designed does not work"* must be
clearly readable. Stop scrolling. Let it sit still on screen for the whole beat.

**Say:**

> "And the section we're most proud of is the one where we wrote down that our
> own guardrail didn't work. Our off-topic detector assumed a bad question
> retrieves bad matches. We measured it — the distributions almost completely
> overlap. Worse, our own calibration was rigged: a hundred and twenty good
> questions against eight bad ones, so 'always answer' scored best.
>
> So we rebuilt it as an intent gate and validated it against six and a half
> thousand real queries. Writing that down is the process."

*(~78 words. End on "is the process" and stop. Do not add a sign-off.)*

---

## Timing check

| Beat | Window | Runs | Words |
|---|---|---|---|
| 1 constraint | A · line 47 | 0:00–0:14 | 62 |
| 2 contract | A · line 212 | 0:14–0:32 | 58 |
| 3 ablation | A 368 → B tab 1 | 0:32–0:56 | 74 |
| 4 bugs | B tab 2 · git log | 0:56–1:14 | 66 |
| 5 honesty | A · line 505 | 1:14–1:30 | 78 |

**338 words in 90 seconds** — about 225 words per minute. That is brisk but
normal for a confident read. **Read it out loud with a timer twice before
recording.** If you land over 90 seconds, cut the second sentence of beat 4
("A missing Devanagari full stop…") rather than speaking faster.

---

## Rules while recording

- **Record the audio in one take.** Screen capture can be re-recorded and lined
  up afterwards; a spliced voice track is audible.
- **Keep scrolling slow.** Fast scrolling turns to mush after compression.
- **Never show the browser or the UI.** The brief says process, not product.
  Showing the demo here wastes the beat and duplicates video 2.
- **Do not say "we used AI to build it".** Nobody is asking. The measurements
  are the story.
- If you fumble a line, stop and restart the beat. Do not apologise on tape.

## Numbers you may say — all verified

- 200 ms budget · STT measured **513 ms**
- Sentence-window chunking: **−9 ms worse, lower recall AND lower MRR**
- Index shrank **63%** (chunks per passage 5.50 → 2.0)
- Off-topic detection: in-corpus min **0.842** vs off-topic max **0.887** — overlapping
- Rigged calibration: **120 positives vs 8–10 negatives**
- Rebuilt gate validated on **6,535 real queries**; English unanswerable **100% caught**

## Do not say

- Any latency number for the *live* site (this video has no product in it).
- "99,985 passages" as if the deployed demo searches them — that's video 2's
  careful wording, and it doesn't belong here.
