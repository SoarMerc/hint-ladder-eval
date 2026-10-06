# Hint-ladder leakage harness

Checks whether an AI tutor's hints actually make the student think, or whether
they quietly hand over the answer a few hints early.

---

## The idea

A tutor gives a stuck student a series of hints, each a bit more helpful than
the last, and none of them supposed to give the answer away.

To check that, the harness writes a question, an answer, and a ladder of four
hints. Then it shows a model **only the hints, never the question**, and asks
what the answer to the hidden question must be.

```
    a ladder doing its job         a ladder that leaks
    score                          score
     |                              |        _________
     |                              |       |
     |                              |       |
     |_______________               |_______|
     +--------------> hints         +--------------> hints
       0  1  2  3  4                  0  1  2  3  4

    the hints describe a           by hint 2 you can work out
    method, so with no             the answer from the hints
    question there is              alone, and hints 3 and 4
    nothing to solve               were decoration
```

Hiding the question is the part that makes this work, and it's the one
non-obvious choice in the whole thing. More on that below.

The failure is worth catching because it's silent. Nothing errors, no log line
looks wrong. The student answers correctly, the mastery score goes up, and no
learning happened.

---

## Run it

```bash
pip install -r requirements.txt

# No API key needed. Deterministic simulator, runs in about a second.
python -m src.run --mock

# Real run. Put your key in .env first (see .env.example).
python -m src.run

# A quick real run over four standards while you watch the cost.
python -m src.run --skills 4
```

Both modes write two things to the repo root:

- `FINDINGS.md` - one page: the number, the chart, which ladders failed, what
  the run cost, and what it doesn't prove.
- `leakage_curves.png` - the chart (a dark version gets written too).

![Leakage curves](leakage_curves.png)

---

## Why the obvious version doesn't work

The obvious way to build this is to show the student the question plus a few
hints, then watch its score go up as you give it more hints.

I built that first. Then I measured it, and it doesn't work.

Here is the problem. Before giving it any hints at all, I asked the student
model to answer the questions cold:

| questions        | score with no hints |
| ---------------- | ------------------: |
| Maths, 4 hardest | **100%** |
| ELA, all 8 | **91%** |

The model already knows the answers. It never needed the hints. So its score
starts at the top and stays there, the line is flat, and you learn nothing
about the ladder.

You can't fix this by picking a weaker model. Every current model is good at
grade 6-8 work, and they keep getting better.

So instead: **hide the question.**

Now the model has nothing to solve. It sees only the hints. If it can still
tell you the answer, that is because the hints told it. That is exactly what we
wanted to measure, and it keeps working no matter how smart models get.

This also catches what a plain text search would miss. On the first item I
generated, none of the four hints contained the answer anywhere in their text.
The model still worked the answer out from hints 1 to 3.

The old version still runs if you want to see the flat lines yourself:
`python -m src.run --with-question`.

---

## Does the detector actually work?

Worth checking, since the whole thing reports a failure rate. In `--mock` mode
the simulator plants leaks at levels it chooses, and the real detector has to go
find them. 20 standards, 3 languages, 25 planted leaks out of 60 ladders:

| repeats | version | found | false alarms | missed |
| ---: | --- | ---: | ---: | ---: |
| 5 | hints-only | 25/25 | 0 | 0 |
| 40 | with-question | 25/25 | 0 | 0 |
| 20 | with-question | 25/25 | 1 | 0 |
| 10 | with-question | 25/25 | 5 | 0 |
| 5 | with-question | 22/25 | 6 | 3 |

Hints-only gets it exactly right at 5 repeats. The old version needs 40 to match
that, which is 8x the calls.

My first attempt at the detector was wrong. It reported 19 false alarms, because
it flagged any score jump bigger than 35 points. With 5 repeats a score can only
be 0, 20, 40, 60, 80 or 100, so two neighbouring points can differ by 40 purely
by luck.

It now needs three things before it calls something a leak:

1. the jump is bigger than what chance would produce at that number of repeats
2. the score afterwards is actually high (10% to 45% means the hint helped,
   which is its job)
3. the score stays high for the rest of the ladder, because once the answer is
   out it doesn't go back in

Rule 3 caught a real case: one ELA ladder scored 33% at hint 2, then 0% at hints
3 and 4. Noise, not a leak. There's a test in `tests/test_pipeline.py` so this
doesn't quietly break again.

---

## Two extras

**The same ladder in three languages.** Same question, same answer, hints
translated. I translate instead of writing a fresh question per language so the
only thing that changes is the hint wording.

I expected hints to get leakier in translation. They mostly didn't: 12, 12 and
11 leaks out of 20 for English, Spanish and French, and only one standard
changed level. Leaving it in because a negative result is still a result.

**Standards drift.** Each question goes to a second model that isn't told which
standard it was written for, and has to pick one from the list. How often it
picks a different one tells you how often generated content drifts from its
label.

---

## A few choices worth explaining

**Hiding the question from the student.** Covered above. Everything else follows
from it.

**The student runs with thinking turned off.** This rules out some models
entirely. `gemini-3.1-pro-preview` refuses `thinking_budget=0` ("only works in
thinking mode"), so it can't be the student no matter what else it's good at.

**The judge never sees the hints.** It gets the question, the right answer, and
the student's response, and nothing else. If it saw the hints it might mark
something correct because a hint made the answer look obvious, which is the
exact thing being measured.

**Most grading skips the judge.** An exact match after normalising settles the
easy cases for free, and `UNKNOWN` responses short-circuit without a call. So
grading cost tracks the interesting cases rather than the size of the run.

**Mock and live runs never share a cache entry.** The cache key includes the
mode. Without that, a mock run poisons the cache and a later real run replays
fake answers while reporting no spend. That bug was here; there's a test for it
now.

**Models with no price report tokens, not dollars.** Only models with a rate in
`config.py` get a dollar figure. The rest say `not priced` instead of guessing.

**Python, not TypeScript.** Eval tooling usually sits beside the app rather than
inside it, and Python is the normal choice there.

---

## Ground rules

- All content is generated at runtime. Nothing is scraped or copied from any
  product or website. The skill list is public Common Core codes.
- No student data. There's no code path that reads or stores a student record,
  and none is needed.
- No keys in the repo. They come from `.env`, which is gitignored.
  `.env.example` is the template.

---

## Repo map

```
src/generate.py   writes the question, answer and hint ladder, and translates it
src/simulate.py   runs the student across the ladder (start here)
src/grade.py      scores responses; the judge doesn't see the hints
src/detect.py     turns a curve into a verdict
src/tag.py        standards drift check
src/report.py     the chart and FINDINGS.md
src/client.py     Gemini calls, retries, cache, cost tracking
src/config.py     every setting, one screen
fixtures/         the 20 Common Core standards
tests/            detector tests plus a full run on the simulator
results/          cache and raw run.json (gitignored)
```

Read `simulate.py` first, then `detect.py`. Between them that's the argument;
the rest is plumbing.

---

## What this doesn't prove

- The content is synthetic, so this measures ladders the harness writes, not
  anyone's product.
- 20 standards across 3 languages. That's 60 curves, but the languages share a
  question and answer, so the real sample size is 20.
- A jump at hint 3 is strong evidence that hints 1-3 carry the answer. It isn't
  proof. Read the flagged ladders before acting on them.
- The judge is a model marking free text. It gets things wrong sometimes.
- Prices in `config.py` were checked in July 2026 and will drift.
