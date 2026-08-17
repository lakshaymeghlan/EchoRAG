# How EchoRAG works — the complete explanation


Read it top to bottom. Each part builds on the one before.

---

# Part 0 — Words you will need

Six words do most of the work in this document. Learn these and the rest follows.

### A **model**

A program that has learned a pattern from examples. Ours has read enormous amounts of text
in many languages and learned which sentences *mean* similar things.

Important: our model does **not** write sentences. It does exactly one job — turn a piece of
text into a list of numbers. That's it. (ChatGPT is a different kind of model, one that
writes. We don't use one.)

### A **vector** (or "embedding")

A list of numbers that stands for the meaning of a piece of text. Ours are 384 numbers long.

Think of coordinates on a map. "Delhi" is two numbers — latitude and longitude — and those
two numbers place it somewhere specific. Cities near each other have similar coordinates.

An embedding is the same idea, but for *meaning*, and with 384 numbers instead of 2. Text
that means similar things gets similar numbers.

```
"how do I train a puppy"          →  [0.057, -0.026, -0.024, … ]   384 numbers
"best way to train a young dog"   →  [0.061, -0.021, -0.019, … ]   very similar numbers
"the stock market closed higher"  →  [-0.12,  0.340,  0.077, … ]   very different numbers
```

The first two share almost no words, but mean the same thing, so their numbers are close.
That is the single idea the entire system is built on.

### A **database**

An organised store of information you can search quickly. A phone book is a database.

Ours is a **vector database** — it stores those 384-number lists and can answer "which of my
200,000 entries has numbers closest to *these* numbers?" extremely fast.

### An **API**

A way for one program to ask another program for something over the internet. You send a
request, you get an answer back.

We use one: **Sarvam**, an Indian company whose API turns recorded speech into text.

### A **function**

A named piece of the program that does one job. You give it something, it gives something
back.

```
split_sentences("Cats sleep. They hunt.")   →   ["Cats sleep.", "They hunt."]
        ↑                  ↑                              ↑
     its name        what you give it              what it gives back
```

That's all a function is. This document walks through about 30 of them.

### **RAG** — Retrieval-Augmented Generation

The name for this whole approach:

1. **Retrieval** — go find the relevant documents
2. **Augmented** — use those documents rather than memory
3. **Generation** — produce the answer

The point is that the system doesn't answer from memory. It looks things up first, then
answers from what it found. That's why it can cite a source, and why it can say "I don't
have that."

---

# Part 1 — The big picture

## The problem we're solving

A user speaks a question out loud, in Hindi or English. We must give them a correct answer,
taken from a specific collection of documents, **in under a fifth of a second.**

## The library analogy

Imagine a library with 100,000 pages of information, and a librarian who must find the right
page in a fraction of a second.

A normal librarian reads titles and searches for matching words. Ours does something
different: **every page has been given a coordinate that represents its meaning.** When you
ask a question, the question also gets a coordinate. Then finding the right page is just
finding the nearest coordinate — which computers do very fast.

That coordinate system is what "embedding" means. Building it is the slow part, so we do it
once, in advance.

## Two halves

This is the most important structural idea in the project.

```
╔═══════════════════════════════════════════════════════════════╗
║  HALF 1 — BEFORE ANYONE ASKS ANYTHING       (once, 17 min)    ║
║                                                               ║
║  Download the documents                                       ║
║  Give every one a 384-number coordinate                       ║
║  Store them in a searchable database                          ║
╚═══════════════════════════════════════════════════════════════╝
                              │
                              ▼
                    a 723 MB folder: index/
                              │
                              ▼
╔═══════════════════════════════════════════════════════════════╗
║  HALF 2 — WHEN SOMEONE ASKS                (every question)   ║
║                                                               ║
║  Hear the question         (Sarvam)                           ║
║  Check it's worth answering (guards)                          ║
║  Give it a coordinate       (the model)                       ║
║  Find nearby documents      (the database)                    ║
║  Pick the best sentence     (comparison)                      ║
║  Check the answer is honest (guards again)                    ║
╚═══════════════════════════════════════════════════════════════╝
```

**Half 1 takes 17 minutes. Half 2 takes 50 milliseconds.** All the slow work happens before
any user arrives — that's the whole trick behind the speed.

## The thing that surprises people

**There is no ChatGPT-style AI writing the answers.**

The answer is a sentence **copied word-for-word** out of a document we found. Nothing is
composed. Nothing is written.

Why that's a feature, not a limitation:

- It cannot make things up. You cannot invent a sentence you copied.
- It's fast. Copying is instant; writing takes hundreds of milliseconds.
- We can point at the exact source of every answer.

Our documents come from a dataset where the answer is already *inside* the passage. So
writing a new sentence would just mean rephrasing one we already have — extra time, extra
cost, extra risk of error.

---

# Part 2 — Half 1: building the library

*(File: `index.py`. Runs once, takes 17 minutes.)*

## Step 1 — Get the documents

Our documents come from **MSMARCO-XI**, a public collection of real questions people typed
into a search engine, with candidate answer passages, translated into 13 Indian languages.

The full collection is **55.6 GB** — about 11.5 million entries. We deliberately took a
small slice: **10,000 entries, which unpack into 99,985 passages.**

**Why not all of it?** Arithmetic:

| If we indexed… | Storage needed | Time to build |
|---|---|---|
| What we did (10,000) | 0.7 GB | 17 minutes |
| 100,000 | 7 GB | 3 hours |
| Everything | **831 GB** | **14 days** |

The coordinates take about 15× more space than the text they describe. 55.6 GB of text
becomes 831 GB of coordinates. No affordable computer holds that, and 14 days is longer than
the whole competition.

So: a deliberate slice, sized to fit on a real server and stay fast.

## Step 2 — Unpack

The raw data arrives in bundles. One entry contains a question plus **ten** candidate
passages, packed together.

```
One raw entry
  ├── the question:  "what is a corporation?"
  └── ten passages bundled together:
        passage 1 (English + Hindi)
        passage 2 (English + Hindi)
        …
        passage 10 (English + Hindi)
```

`load_passages()` unpacks this into ten separate passages, each standing on its own.

**Unpacking is not cutting.** No text is shortened — it's just taken out of the bundle. This
distinction matters for the next step.

## Step 3 — Chunking (the important decision)

**Chunking means deciding what unit of text to give a coordinate to.**

Do you coordinate a whole page? A paragraph? Each sentence? This choice decides how well
search works, and the competition specifically asks for serious thought here.

### What most people do

Cut everything into fixed-size pieces — say every 500 characters — regardless of meaning.
This chops sentences in half.

### What we measured first

Before choosing, we measured our actual passages:

```
shortest passage:   3 words
typical passage:   50 words     ← about 3½ sentences
longest passage:  169 words
```

**Our passages are already small.** Someone has already cut this text into sensible pieces.
Cutting a 50-word passage into 500-character chunks would do nothing except destroy a good
boundary.

### What we tried anyway

We built the popular alternative — **"small-to-big"**: coordinate each sentence separately
(with its neighbours for context), but return the whole passage when one matches. It's a well
regarded technique.

We measured it against known-correct answers. It made things **worse**:

| | Without it | With it |
|---|---|---|
| Found the right passage | 76.7% | 75.3% ⬇ |
| Ranked it near the top | 0.448 | 0.433 ⬇ |
| Time taken | — | +9 ms ⬇ |

Worse on all three. **Why:** passages average 3½ sentences, so a 3-sentence window covers
~85% of the passage it came from. We were creating near-duplicates that competed with their
own originals.

Small-to-big is designed for long documents. Ours are too short for it to help.

**So we deleted it.** The code is still there so anyone can re-run the experiment, but it's
switched off.

### What we actually do

**Coordinate the whole passage, twice — once in English, once in Hindi.**

```
One passage
  ├── full English text  →  coordinate  (we call this "view 1")
  └── full Hindi text    →  coordinate  (we call this "view 2")
```

Two coordinates per passage. 99,985 passages → 199,970 coordinates.

The proper name for this: **document-level chunking with multi-representation indexing.**
Plain version: *don't cut the text; describe the same text in several different ways.*

## Step 4 — Give everything coordinates

Every piece of text goes through the model and comes out as 384 numbers. This is the slow
part — about 450 pieces per second, which is why the whole build takes 17 minutes.

## Step 5 — Build three search structures

The database gets three different ways to find things:

| | Name | What it finds | Like… |
|---|---|---|---|
| 1 | **Vector index** | passages with *similar meaning* | "find restaurants near me" |
| 2 | **Keyword index (BM25)** | passages containing the *exact words* | the index at the back of a book |
| 3 | **Labels** | filters by language, question type | coloured tabs on folders |

**Why both 1 and 2?** They fail in opposite ways.

- Meaning-search is great at *"corporation"* matching *"incorporated business entity"*, but
  bad at exact strings like *"iPhone 14 Pro"* — it thinks all phone models are similar.
- Keyword-search nails *"iPhone 14 Pro"* but has no idea *"puppy"* and *"young dog"* are
  related.

Using both covers each one's blind spot. The industry term is **hybrid search**.

### One detail worth knowing

Number 1 needs an extra structure or it's slow. Without it, the database compares your
question against all 199,970 coordinates one at a time. With it, coordinates are pre-grouped
into neighbourhoods and only the nearest few are searched.

```
without:  62 milliseconds
with:     38 milliseconds
```

The catch: it can occasionally miss something sitting just over a neighbourhood boundary. We
measured that cost — about 1.4% of results — and accepted it, because 24 milliseconds is a
lot when your entire budget is 200.

**Half 1 is done.** A 723 MB folder that can be searched instantly.

---

# Part 3 — Half 2: answering a question

*(Everything below happens per question, in about 50 milliseconds.)*

## Step 1 — Hearing

*(File: `stt.py`)*

Your browser records audio and sends it to **Sarvam**, whose API returns text.

```
🎤 "what is a corporation"   →   Sarvam   →   "What is a corporation?"
```

Two things about this:

**It takes about 513 milliseconds** — longer than our entire 200 ms budget. It's a round trip
across the internet to another company's servers. Nobody can make that fit inside 200 ms.

So we're explicit: **the 200 ms clock starts once the text arrives.** We measure and report
speech-to-text separately rather than hiding it inside one flattering number.

**Speech recognition makes mistakes.** In testing, "corporation" came back as "cooperation".
That's normal, and it's why the later checks matter.

### What happens when the API fails

Internet requests fail. `stt.py` handles it:

- Certain failures mean *"busy, try again"* → wait a moment, retry, up to 3 times
- Other failures mean *"your request was wrong"* → stop immediately, don't retry

Retrying a broken request just wastes money on something that can never work.

The waiting time also has a small random amount added. Otherwise every user who failed at the
same instant would retry at the same instant and knock the recovering service over again.

## Step 2 — The gates (should we even answer?)

*(File: `guards.py`)*

Before searching, three quick checks. Each can stop everything and refuse.

### Gate 1 — Did we get a real question?

Empty, silence, or one word → *"I didn't catch that."*

### Gate 2 — Is it safe?

Harmful requests are refused **before** we search. The dangerous content never gets touched.

### Gate 3 — Is this answerable *at all*?

This is the interesting one, and it came from an experiment that failed.

**What we tried first.** Assume that if a question is unrelated to our documents, the search
will return poor matches, so a low match score means "refuse."

**Why it didn't work.** We measured it:

```
real questions      match score  0.84 – 0.90
unanswerable ones   match score  0.86 – 0.89     ← the same range
```

No way to separate them. And the reason is obvious in hindsight: our documents are a broad
crawl of the web. Ask *"what is my bank account balance"* and it genuinely finds excellent
passages about bank account balances. The question isn't *unrelated*. It's **impossible** —
we don't have your bank details.

**That's a property of the question, not of the documents.** So we detect it from the
question:

| The question contains | Example | Why we can't answer |
|---|---|---|
| "my", "मेरे" | "what is my bank balance" | we don't have your personal data |
| "send", "play", "भेजो" | "remind me to call mom" | that's a command, not a question |
| "right now", "अभी" | "what's the weather right now" | our documents are fixed; they can't know today |

**We checked these rules don't misfire** before shipping them. Each was tested against 6,535
real questions to see how often it would wrongly refuse a good one: between 0% and 1.9%.

Two proposed rules were **rejected** by that test:

- Blocking the word "I" — because *"how do I train a puppy"* is a perfectly answerable
  question
- Blocking the Hindi word "कल" — it means both *yesterday* and *tomorrow*, and appears in
  ordinary questions

That's the method worth noticing: **measure whether a rule causes harm before you ship it.**

## Step 3 — Give the question a coordinate

*(File: `embed.py`)*

The same model that processed all the documents now processes your question. 384 numbers, in
about 7 milliseconds.

**It must be the same model.** Two different models produce coordinates in different systems —
like one map using latitude/longitude and another using street addresses. Neither is wrong;
they just can't be compared.

### The cross-language trick

Our model was trained on many languages **at once**, so it places the same meaning in the
same location regardless of language.

We measured it:

```
"how do I train a puppy"  vs  "best way to train a young dog"     0.935   (1.0 = identical)
"how do I train a puppy"  vs  "पिल्ले को कैसे प्रशिक्षित करें?"   0.854
"how do I train a puppy"  vs  "the stock market closed higher"     0.692
```

The Hindi version of the same question scores far above an unrelated English one. **A Hindi
question can find an English document.**

This is why we have *one* library instead of thirteen — one for each language would mean 13×
the storage and 13× the build time.

## Step 4 — The search

*(Files: `tools.py`, then `retrieve.py`)*

### Why it goes through a "tool"

Instead of the program calling the search directly, it goes through a middle layer that:

1. Checks the request makes sense (is the number actually a number?)
2. Checks there's still time left before starting
3. Runs it, retrying once if it fails
4. Returns a **result object** that says whether it worked

Point 4 matters. When something fails, we get back *"this didn't work, here's why"* — a piece
of information the program can act on. Not a crash.

This is also the structure a writing-AI would need if we ever added one: it would be handed
the same list of available tools and could choose for itself. Same machinery either way.

### The search itself

Three separate searches run:

```
your question
     │
     ├──▶  search English coordinates   →  list A
     ├──▶  search Hindi coordinates     →  list B      (only for Hindi questions)
     └──▶  search keywords              →  list C
```

Here's what three real lists look like for the question *"कॉर्पोरेशन क्या है?"*:

```
list A (English):   1057779,  1102432,  1057779,  1007776
list B (Hindi):     1036201,  1007972,  1048673,  1041043
list C (keywords):  1089557,  1041043,  1007972,  1046279
```

**They barely agree.** Three ways of looking at the same library, three different answers.

### Combining them — the voting system

We can't just add the scores together, because they're measured on incompatible scales — one
search returns 0.13, another returns 12.7. There's no sensible way to add those.

So we ignore the scores entirely and **use only the ranking positions.** A document gets
points based on where it placed in each list, and points add up across lists.

```
final:  1057779   0.0318   ← appeared in list A and list B
        1007972   0.0315   ← appeared in list B and list C
        1036201   0.0164   ← appeared in only one list — half the score
```

**Agreement is the signal.** Anything two independent methods both liked scores about twice
what one method alone gives it. This is called **Reciprocal Rank Fusion**.

It also fails gracefully: if one search returns rubbish, it contributes almost nothing rather
than dragging everyone down with wild numbers.

### One safeguard

If one long passage appeared several times in a single list, it would collect several votes
and win for being long rather than relevant. So each list is first reduced to *one entry per
passage* before voting.

### Which searches run

Not always all three:

| Question in | Searches used |
|---|---|
| Hindi | English + Hindi + keywords |
| English | English + keywords |

Because we measured that the Hindi search **helps** Hindi questions (+12.7%) and **hurts**
English ones (−2.0%) — Hindi text is just noise when you asked in English. One fixed setting
would have been wrong for one of the two languages.

## Step 5 — Choosing the answer

*(File: `answer.py`)*

We now have the 5 best passages. But a passage is several sentences and the user wants an
answer, not a paragraph.

So we pick the single best sentence out of the winning passage — in two stages, for speed:

**Stage 1 — cheap filter.** Count how many of the question's words appear in each sentence.
Nearly free. Keep the best 3.

**Stage 2 — careful comparison.** Give those 3 sentences coordinates and pick the one closest
to the question's coordinate. Costs about 7 ms.

**Why two stages?** Comparing every sentence carefully was costing more than the entire rest
of the pipeline, especially in Hindi (Devanagari script produces roughly 3× more processing
units than English). Filtering cheaply first, then paying only for 3 candidates, keeps us
inside the budget.

**And if time has run out**, stage 2 is skipped entirely and stage 1's answer is used. Still
a real sentence from a real document — just chosen more cheaply.

Answering happens in the language you asked in, using the stored translation.

## Step 6 — Checking our own answer

*(Back to `guards.py`)*

Two final checks before anything is sent.

**Is this nonsense?** If someone types `"xyzzy plugh frotz"`, the search still returns
*something* — it always returns its best guess. So we check whether the question's words
actually appear in the documents we found.

```
real questions:    40–100% of words appear
invented words:              0% appear      ← completely clean separation
```

Honest limitation: this works in English and **not** in Hindi — there the numbers overlap
(real 0.85–1.00, nonsense 0.84–0.86). Applying it to Hindi would reject real questions
without catching anything. So it's switched off for Hindi and documented as a known gap
rather than shipped broken.

**Is the answer actually in the source?** We check the answer's words appear in the passage
we're citing.

Because our answers are copied verbatim, this passes automatically — **which is exactly the
point.** The check exists so that if we ever did add a writing-AI, it would have to prove its
answer came from the source, or be rejected.

---

# Part 4 — The 200 millisecond promise

## How it's enforced

Most systems *hope* to be fast. Ours **measures continuously.**

When a question arrives, a stopwatch starts. Every stage checks it before acting:

```
question arrives          ⏱ 0 ms      200 ms remaining
gates                     ⏱ 1 ms      199 remaining
coordinate the question   ⏱ 8 ms      192 remaining
search                    ⏱ 36 ms     164 remaining
pick the sentence         ⏱ 51 ms     149 remaining     ✅ done, 149 to spare
```

If a stage sees the budget nearly gone, it takes the cheaper route instead of overrunning.
That's why the sentence-picking step has a fast fallback.

This is the difference between *"it's usually fast"* and *"it cannot be slow."*

## The measured results

300 questions, mixed Hindi and English:

| | Time |
|---|---|
| Half were faster than | **48 ms** |
| 70% were faster than | **57 ms** |
| The single slowest | **121 ms** |
| Went over 200 ms | **0 out of 300** |

That last row is the claim. Not "usually fast" — *never* slow, across 300 attempts.

## The problem we had to solve

Computers are slower on their **first** job — memory hasn't been arranged, shortcuts haven't
been prepared. We measured a first request at **290 ms** against a normal 7 ms.

That's a disaster, because the first request is the one a judge makes.

**Fix:** the server quietly asks itself a practice question every 20 seconds. It's never
idle, so it's never cold. First-request time dropped from 399 ms to 90 ms.

## Two safety nets

*(File: `harness.py`)*

**The stopwatch (Deadline)** — described above. Passed to every stage.

**The fuse (Circuit Breaker)** — if an external service fails several times in a row, stop
calling it for 30 seconds. Without this, an outage means every single user waits the full
timeout before failing. With it, we skip straight to the backup.

---

# Part 5 — What's in each file

Quick reference now that you know what everything does.

| File | Its job | Runs |
|---|---|---|
| `schemas.py` | Defines the shape of every piece of data | always |
| `index.py` | Builds the library: download, chunk, coordinate, store | once |
| `embed.py` | The model. Text in, 384 numbers out | both halves |
| `retrieve.py` | The search: three lists, combined by voting | per question |
| `tools.py` | The middle layer that runs searches safely | per question |
| `guards.py` | The four checks — refuse when we should | per question |
| `harness.py` | The stopwatch and the fuse | per question |
| `answer.py` | The conductor — runs all the above in order | per question |
| `stt.py` | Talks to Sarvam: audio in, text out | per question |
| `api.py` | The front door — receives requests, sends replies | per question |

## The order it happens in

```
1.  api.py      a question arrives
2.  stt.py      audio → text                      (Sarvam, ~513 ms)
                                                   ⏱ CLOCK STARTS
3.  answer.py   starts the stopwatch
4.  guards.py   three checks — refuse here if needed
5.  embed.py    question → 384 numbers                     ~7 ms
6.  tools.py    → retrieve.py    search and combine        ~30 ms
7.  guards.py   is it nonsense?
8.  answer.py   pick the best sentence                     ~15 ms
9.  guards.py   is the answer really in the source?
10. api.py      send back the answer, its source, and every timing
                                                   ⏱ ~50 ms total
```

---

# Part 6 — The five things that matter

### 1. There is no answer-writing AI

The only model turns text into numbers. Answers are **copied** from documents. So the system
cannot invent facts — the most common failure of AI systems is structurally impossible here.

### 2. Speed comes from doing the work early

The 17-minute build happens before any user arrives. At question time we only compare
numbers, which is the fastest thing a computer does.

### 3. Refusing is a feature

The system has seven distinct reasons to decline, and a refusal is a normal, successful
response — not an error. A system that answers everything confidently is worse than one that
knows its limits.

### 4. Almost every decision was reversed by measurement

- We built the popular chunking method, measured it, **deleted it**
- We planned a compression step for speed, measured it, **didn't need it**
- We built off-topic detection one way, measured it failing, **rebuilt it differently**
- We estimated storage, measured it, found we'd been **wrong by 5.5×**

Not one of those was decided by opinion.

### 5. We report the inconvenient numbers

Speech-to-text takes 513 ms and cannot fit in the budget. We say so and report it separately,
rather than folding it into one flattering total. The Hindi nonsense-detection gap is
documented rather than hidden.

---

## Try it yourself

```sh
# ask a question
curl -X POST localhost:8000/ask -F "text=what is a corporation?"

# watch it refuse
curl -X POST localhost:8000/ask -F "text=what is my bank account balance"
```

The reply includes the answer, which passage it came from, and how long every stage took.
