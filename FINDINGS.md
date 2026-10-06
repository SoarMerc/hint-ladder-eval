# Findings

## What this measures

A tutor that teaches through hints is supposed to make the student do the thinking. Each hint helps a bit more than the last, and none of them gives the answer away. This checks whether that holds.

It writes a question, an answer, and a ladder of 4 hints. Then it shows a model **only the hints, never the question**, and asks what the answer to the hidden question must be.

- If the ladder is doing its job, the model can't answer. Without the question there's nothing to solve, because the hints describe a method rather than handing over a result.
- If the ladder leaks, at some hint the model can answer **from the hints alone**, and every hint after that was decoration.

Hiding the question is what makes this work. The obvious approach - show the student the question and watch its score climb as hints arrive - doesn't work any more, because a small current model answers grade 6-8 questions with no hints at all. Its score starts at the top and never moves. Hiding the question puts the floor back at zero no matter how good the model is.

This also catches what a plain text search would miss. On one generated item, none of the hints contained the answer anywhere in their text, and the model still worked it out from the first three.

The failure is worth catching because it's silent. Nothing errors. The student gets it right, the mastery score goes up, and no learning happened.

## Headline

**35 of 60 ladders gave the answer away earlier than intended.**

Those 60 ladders are 20 standards measured in 3 languages, not 60 independent items. The languages share a question and an answer by design, so they are correlated: treat the underlying sample size as 20.

![Leakage curves](leakage_curves.png)

## Results by outcome

| outcome | count | what it means |
|---|---:|---|
| leaked | 35 | the score jumped before the last hint, so the ladder gave the answer away early |
| ok | 20 | the score climbed gradually, or only jumped at the last hint |
| trivial | 0 | answered with no hints at all, so the question itself is the problem |
| no signal | 5 | the ladder barely moved accuracy, so leakage is not measurable on this item |

## Same ladder, different language

Same question, same answer, hints translated. These are the ladders that hold up in English and lose it in another language.

| skill | language | leaks at hint | English leaks at hint | earlier by |
|---|---|---:|---:|---:|
| RL.6.2 | Spanish | 3 | 4 | 1 |

## Flagged items

| skill | language | outcome | no hints | full ladder | note |
|---|---|---|---:|---:|---|
| 6.EE.B.7 | en | leaked | 0% | 100% | accuracy jumped 100% at hint 2 and stayed up, 2 level(s) earlier than intended |
| 6.EE.B.7 | es | leaked | 0% | 100% | accuracy jumped 100% at hint 2 and stayed up, 2 level(s) earlier than intended |
| 6.EE.B.7 | fr | leaked | 0% | 100% | accuracy jumped 100% at hint 2 and stayed up, 2 level(s) earlier than intended |
| 6.NS.C.6 | en | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 6.NS.C.6 | es | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 6.NS.C.6 | fr | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 6.RP.A.3 | en | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 6.RP.A.3 | es | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 6.RP.A.3 | fr | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 7.EE.B.4 | en | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 7.EE.B.4 | es | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 7.EE.B.4 | fr | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 7.NS.A.1 | en | leaked | 0% | 100% | accuracy jumped 100% at hint 2 and stayed up, 2 level(s) earlier than intended |
| 7.NS.A.1 | es | leaked | 0% | 100% | accuracy jumped 100% at hint 2 and stayed up, 2 level(s) earlier than intended |
| 7.NS.A.1 | fr | leaked | 0% | 100% | accuracy jumped 100% at hint 2 and stayed up, 2 level(s) earlier than intended |
| 7.RP.A.3 | en | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 7.RP.A.3 | es | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 7.RP.A.3 | fr | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 8.EE.A.1 | en | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 8.EE.A.1 | es | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 8.EE.A.1 | fr | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 8.EE.B.5 | en | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 8.EE.B.5 | es | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 8.EE.B.5 | fr | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 8.EE.C.7 | en | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 8.EE.C.7 | es | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 8.EE.C.7 | fr | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 8.G.B.7 | en | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 8.G.B.7 | es | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| 8.G.B.7 | fr | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| L.8.5 | en | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |
| RI.7.5 | en | leaked | 0% | 100% | accuracy jumped 80% at hint 3 and stayed up, 1 level(s) earlier than intended |
| RI.7.5 | es | leaked | 0% | 100% | accuracy jumped 80% at hint 3 and stayed up, 1 level(s) earlier than intended |
| RI.7.5 | fr | leaked | 0% | 100% | accuracy jumped 80% at hint 3 and stayed up, 1 level(s) earlier than intended |
| RL.6.2 | es | leaked | 0% | 100% | accuracy jumped 100% at hint 3 and stayed up, 1 level(s) earlier than intended |

## Standards drift

Each question was shown to a second model that wasn't told which standard it was written for, and had to pick one from the list.

**5% of items were tagged to a different standard than the one they were filed under** (20 items checked).

## What this doesn't prove

- **The content is synthetic.** Every question and hint was generated by this harness. Nothing was taken from any product.
- **Small sample.** 5 attempts per point on each curve. Enough to see a cliff, not enough to put an error bar on it.
- **It's evidence, not proof.** A jump at hint *k* strongly suggests hint *k* carried the answer. Read the flagged ladders before acting.
- **The student is a model, not a child.** It runs with reasoning turned off to sit closer to a struggling learner, but it's a stand-in.
- **The judge never sees the hints**, but it's still a model marking free text, and it gets things wrong sometimes.
- **No student data is involved anywhere.** There's no code path that reads a student record, and none is needed.
