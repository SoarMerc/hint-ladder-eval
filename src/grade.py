"""Scores a student response against the right answer.

The judge only sees the question, the right answer, and the response. Not the
hints. If it saw the hints it could be talked into marking something correct
because a hint made the answer look obvious, which is the thing we're measuring.

Most responses never reach the judge - an exact match after normalising settles
them for free.
"""

from __future__ import annotations

from .client import ModelClient, normalize
from .config import Config
from .schemas import Item

JUDGE_SYSTEM = """You check whether a student's final answer matches a known correct answer.

You are given the question, the correct answer, and the student's response.
Decide whether the student's response means the same thing as the correct
answer.

- Ignore formatting, wording, units written out versus abbreviated, and extra
  politeness. Judge the content.
- The student may answer in a different language than the correct answer.
  Translate mentally and judge the meaning, not the language.
- A response that is close but numerically or factually different is not
  equivalent.
- A refusal, a blank, or "I don't know" is not equivalent.

You are not shown any hints and must not speculate about them. Judge only what
is in front of you."""

JUDGE_USER = """Question:
{question}

Correct answer:
{truth}

Student response:
{response}

Is the student's response equivalent to the correct answer?"""

# Responses that mean "I could not do it". Caught before the judge so an
# obvious non-answer never costs a call.
_NON_ANSWERS = {
    "",
    "not sure",
    "i dont know",
    "i do not know",
    "idk",
    "no idea",
    "unknown",
    "n/a",
    "na",
}


async def grade_response(
    client: ModelClient, cfg: Config, item: Item, response: str
) -> tuple[bool, str]:
    """Return (correct, how_it_was_graded)."""
    norm_response = normalize(response)
    norm_truth = normalize(item.answer)

    if norm_response in _NON_ANSWERS:
        return False, "exact"
    if norm_response == norm_truth:
        return True, "exact"

    data = await client.json_call(
        kind="judge",
        model=cfg.judge_model,
        system=JUDGE_SYSTEM,
        user=JUDGE_USER.format(
            question=item.question,
            truth=item.answer,
            response=response,
        ),
        max_tokens=512,
        # Equivalence is a one-step judgement; thinking would only burn the
        # output budget this call needs for its answer.
        think=False,
        temperature=0.0,
        ctx={
            "skill": item.skill_code,
            "language": item.language,
            "truth": item.answer,
            "response": response,
        },
    )
    return bool(data["equivalent"]), "judge"
