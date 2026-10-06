# Hint-ladder leakage check

A small tool that checks whether an AI tutor's hints make the student think,
or quietly hand over the answer a few hints early.

**How to read this (about 5 minutes, no code needed):**

1. Read [the idea in one example](#the-idea-in-one-example) just below. One minute.
2. Open **[FINDINGS.md](FINDINGS.md)** for the results, the chart, and a table of
   every question tested. Three minutes.
3. Come back here for [what this doesn't prove](#what-this-doesnt-prove).

Everything under [For the technical reader](#for-the-technical-reader) is
optional: how to run it, why it's built the way it is, and where the code
lives.

---

## The idea in one example

A tutor gives a stuck student a series of hints, called a **hint ladder**.
Each hint helps a bit more than the last, and none of them is supposed to give
the answer away.

Here's a ladder this tool wrote for a grade 6 maths question (lightly
shortened; the original is in FINDINGS.md):

> *Liam planted a tree that was 45 inches tall. A few years later it was 112
> inches tall. How many inches did it grow?* Answer: **67**

| hint | text |
|---|---|
| 1 | How can you show the starting height, the growth, and the final height as an addition equation? |
| 2 | Let x be the amount the tree grew. The starting height (45) plus the growth (x) equals the final height (112). |
| 3 | This gives the equation 45 + x = 112. To find x, do the opposite of adding. |
| 4 | Subtract 45 from both sides. Calculate 112 − 45. |

Now **cover the question** and read only the hints. Hint 1 tells you nothing
about the answer. Hint 2 gives you 45, 112, and how they fit together, and
that's enough to get 67 without ever seeing the question. The ladder was meant
to hold until hint 4 and **gave the answer away at hint 2**. A student who
reads hint 2 has nothing left to think about.

That's the whole method. The tool does that "cover the question" test
automatically:

1. An AI writes a question, its answer, and four hints.
2. A second AI plays the student. It's shown **the hints but never the
   question**: first no hints, then hint 1, then hints 1 and 2, and so on. Each
   time it's asked what the answer must be. It gets 5 tries at each step,
   because AI answers vary from one try to the next.
3. If it can name the answer from the hints alone, the hints gave it away.
   The point where that first happens is where the ladder **leaks**.

```
    a ladder doing its job            a ladder that leaks at hint 2
    named the answer                  named the answer
     |                                 |        __________
     |                                 |       |
     |                                 |       |
     |________________                 |_______|
     +----------------> hints          +----------------> hints
       0  1  2  3  4                     0  1  2  3  4
```

Why it matters: this failure is silent. Nothing breaks and no error shows up.
The student types the right answer and moves on, but the hint did the
thinking. If an unaided test comes later, that's where it shows, as a student
who "practised" and still can't do it.

---

## Words used in this repo

| word | meaning |
|---|---|
| **hint ladder** | the four hints for one question, from vaguest to most helpful |
| **leaks at hint 2** | from hint 2 onwards, the answer can be worked out from the hints alone |
| **standard** | one skill from the Common Core, the public list of what US students should learn in each grade. `6.EE.B.7` reads as grade 6, Expressions & Equations, group B, item 7. Codes starting `RL`, `RI`, `L` are English. FINDINGS.md lists what each one covers. |
| **ELA** | English Language Arts: reading, writing, vocabulary |
| **the student** | an AI model standing in for a student. Not a real child. |
| **the judge** | a second AI that marks the student's answer when it isn't an exact match. It never sees the hints, so a hint can't sway its marking. |
| **standards drift** | a question that ends up testing a different skill from the one it's labelled with |
| **mock mode** | a practice run with no AI calls and no cost, using made-up answers, to check the tool itself works |

---

## What it found

On 20 questions it wrote itself (grades 6 to 8, maths and English), each in
English, Spanish and French:

- **10 of the 12 maths ladders gave the answer away at hint 2 or 3**, a hint
  or two before they were supposed to. English-reading ladders leaked much
  less: 2 of 8.
- **Translating the hints made almost no difference.** I expected Spanish and
  French hints to leak more. They didn't: only one question leaked earlier in
  translation.
- **5% of questions drifted** from the skill they were labelled with.

Details, the chart and the full table are in [FINDINGS.md](FINDINGS.md).

---

## What this doesn't prove

- **The content is made up by this tool.** It measures ladders the tool wrote,
  not anyone's product.
- **It's small.** 20 questions. Each appears in 3 languages, but the
  translations share a question and answer, so they tend to pass or fail
  together. Treat it as 20 results, not 60.
- **It's evidence, not proof.** A sudden jump at a hint strongly suggests that
  hint carried the answer. Read the ladder itself before acting on it.
- **The student is an AI, not a child.** It's a stand-in.
- **The marking is done by an AI too**, and it can get things wrong.

## Ground rules

- **Nothing is taken from anywhere.** Every question and hint is written by the
  tool when it runs. The only input is the public list of Common Core codes.
- **No student data.** There's no code that reads or stores anything about a
  student, and nothing in the method needs it.
- **No passwords or keys in the repo.** The AI key lives in a private `.env`
  file that's never uploaded. `.env.example` shows the format.

---

## For the technical reader

### Run it

```bash
pip install -r requirements.txt

# Check everything works: no API key, no cost, about a second.
pytest

# Real run. Put your Gemini key in .env first (see .env.example).
python -m src.run

# A small real run over four standards, to watch the cost.
python -m src.run --skills 4
```

A run writes `FINDINGS.md` and the two chart images to the repo root. Results
are cached in `results/`, so re-running costs nothing. The full run here cost
about $1.

`python -m src.run --mock` runs the whole pipeline on a simulator that plants
leaks at known hints. Note that it **overwrites FINDINGS.md with simulated
numbers**; the page says so at the top. `git checkout FINDINGS.md
leakage_curves*.png` puts the real ones back.

### Why the question is hidden

The obvious version of this shows the student the question plus a few hints
and watches its score climb as hints arrive. I built that first, and it
doesn't work. With no hints at all, the student model already scored:

| questions        | score with no hints |
| ---------------- | ------------------: |
| Maths, 4 hardest | **100%** |
| ELA, all 8 | **91%** |

It never needed the hints, so the line starts at the top and stays flat. A
weaker model doesn't fix it, since every current model handles grade 6-8 work
and they keep improving. Hiding the question puts the floor back at zero
whatever the model.

It also catches what a text search misses. In the tree example, no hint
contains "67", but the answer is still in hint 2.

The old version still runs: `python -m src.run --with-question`.

### Does the detector actually work?

In mock mode the simulator plants leaks at known hints, and the real detector
has to find them. 20 standards, 3 languages, 25 planted leaks out of 60
ladders:

| tries per step | version | found | false alarms | missed |
| ---: | --- | ---: | ---: | ---: |
| 5 | hints-only | 25/25 | 0 | 0 |
| 40 | with-question | 25/25 | 0 | 0 |
| 20 | with-question | 25/25 | 1 | 0 |
| 10 | with-question | 25/25 | 5 | 0 |
| 5 | with-question | 22/25 | 6 | 3 |

Hints-only is exact at 5 tries. The old version needs 40 to match it, which is
8x the AI calls.

My first detector was wrong: 19 false alarms, because it flagged any jump over
35 points. With 5 tries a score can only be 0, 20, 40, 60, 80 or 100%, so two
neighbouring points can differ by 40 by luck. It now needs all three:

1. the jump is bigger than chance would produce at that many tries
2. the score afterwards is actually high (10% to 45% means the hint helped,
   which is its job)
3. the score stays high for the rest of the ladder, because once the answer
   is out it doesn't go back in

Rule 3 caught a real case: one ELA ladder scored 33% at hint 2, then 0% at
hints 3 and 4. Noise, not a leak. `tests/test_pipeline.py` guards it.

### Choices worth explaining

**Translate rather than rewrite per language.** Same question, same answer,
only the hints change, so any difference comes from the hint wording.

**The student runs with thinking turned off**, to sit closer to a struggling
learner. This rules some models out: `gemini-3.1-pro-preview` refuses
`thinking_budget=0`.

**The judge never sees the hints.** If it did, it might mark something correct
because a hint made the answer look obvious, which is the thing being
measured.

**Most grading skips the judge.** An exact match settles easy cases for free,
and "UNKNOWN" answers short-circuit. Cost tracks the interesting cases, not
the size of the run.

**Mock and real runs never share a cache entry.** Otherwise a mock run poisons
the cache and a later real run replays fake answers while reporting no spend.
That bug happened; there's a test for it now.

**Unpriced models report tokens, not dollars.** Only models with a rate in
`config.py` get a dollar figure.

**Python, not TypeScript.** Eval tooling usually sits beside the app rather
than inside it, and Python is the normal choice there.

### Where the code lives

Each file opens with a plain-English note on what it does and why.

```
src/simulate.py   runs the AI student across the ladder   <- start here
src/detect.py     decides whether a curve counts as a leak <- then here
src/generate.py   writes the question, answer and hints, and translates them
src/grade.py      marks answers; the judge never sees the hints
src/tag.py        the standards drift check
src/report.py     the chart and FINDINGS.md
src/client.py     AI calls, retries, cache, cost tracking
src/config.py     every setting, one screen
fixtures/         the 20 Common Core standards
tests/            detector tests plus a full run on the simulator
results/          cache and raw results (not uploaded)
```

`simulate.py` and `detect.py` together are the argument; the rest is plumbing.
Prices in `config.py` were checked in July 2026 and will drift.
