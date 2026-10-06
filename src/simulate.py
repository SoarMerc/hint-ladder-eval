"""Runs the student model across the hint ladder.

Two modes:

    hints_only     show the hints, hide the question. If the model can still
                   name the answer, the hints gave it away. This is the default.
    with_question  the original approach: question plus k hints, watch the
                   score climb.

with_question doesn't work on current models. gemini-3.1-flash-lite answers
grade 6-8 items with no hints at all (100% on maths, 91% on ELA), so the score
starts at the top and the curve is flat. Hiding the question fixes that, since
you can't solve a question you haven't seen.

Both are kept so the flat curves stay reproducible.
"""

from __future__ import annotations

import asyncio

from .client import ModelClient
from .config import Config
from .grade import grade_response
from .schemas import Attempt, Curve, Item, Skill

HINTS_ONLY = "hints_only"
WITH_QUESTION = "with_question"

SYSTEM_WITH_QUESTION = """You are a student in grade {grade} working on a practice question.

You may be given some hints. Use whatever you have been given and commit to a
single best final answer.

- Reply with the answer only. No working, no explanation, no restating the
  question.
- If you are unsure, still give your best guess rather than refusing.
- Answer in the same language as the question."""

SYSTEM_HINTS_ONLY = """You are shown the hints a tutor gave a student about a question you have NOT been shown.

Work out what the answer to that hidden question must be, using the hints alone.

- Reply with the answer only. No working, no explanation.
- If the hints do not contain enough information to determine the answer, reply
  with exactly: UNKNOWN
- Do not guess. UNKNOWN is the correct response when the hints only describe a
  method without supplying the specifics it needs.
- Answer in the same language as the hints."""

USER_NO_HINTS = """Question:
{question}

Your answer:"""

USER_WITH_HINTS = """Question:
{question}

Hints you have been given so far:
{hints}

Your answer:"""

USER_HINTS_ONLY_EMPTY = """You have been given no hints at all, and you have not seen the question.

Your answer:"""

USER_HINTS_ONLY = """Hints a tutor gave about a question you have not seen:
{hints}

What is the answer to the hidden question?

Your answer:"""


def _prompt(
    item: Item, condition: str, hints_shown: int, grade_level: int
) -> tuple[str, str]:
    shown = item.hints[:hints_shown]
    numbered = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(shown))

    if condition == HINTS_ONLY:
        system = SYSTEM_HINTS_ONLY
        user = (
            USER_HINTS_ONLY.format(hints=numbered) if shown else USER_HINTS_ONLY_EMPTY
        )
    else:
        system = SYSTEM_WITH_QUESTION.format(grade=grade_level)
        user = (
            USER_WITH_HINTS.format(question=item.question, hints=numbered)
            if shown
            else USER_NO_HINTS.format(question=item.question)
        )
    return system, user


async def _one_attempt(
    client: ModelClient,
    cfg: Config,
    item: Item,
    grade_level: int,
    hints_shown: int,
    repeat: int,
    condition: str = HINTS_ONLY,
) -> Attempt:
    system, user = _prompt(item, condition, hints_shown, grade_level)

    data = await client.json_call(
        kind="student",
        model=cfg.student_model,
        system=system,
        user=user,
        max_tokens=512,
        # Thinking off - see config.py
        think=False,
        temperature=1.0,  # we want the repeats to actually vary
        cache_salt=f"{condition}:{item.language}:{hints_shown}:{repeat}",
        ctx={
            "skill": item.skill_code,
            "language": item.language,
            "condition": condition,
            "hints_shown": item.hints[:hints_shown],
            "repeat": repeat,
            "max_level": cfg.max_hint_level,
        },
    )
    response = data["answer"]
    correct, how = await grade_response(client, cfg, item, response)
    return Attempt(
        skill_code=item.skill_code,
        language=item.language,
        condition=condition,
        hints_shown=hints_shown,
        repeat=repeat,
        response=response,
        correct=correct,
        graded_by=how,
    )


async def sweep(
    client: ModelClient,
    cfg: Config,
    items: list[Item],
    skills: list[Skill],
    conditions: list[str] | None = None,
) -> list[Attempt]:
    conditions = conditions or [HINTS_ONLY]
    grade_of = {s.code: s.grade for s in skills}
    jobs = [
        _one_attempt(
            client,
            cfg,
            item,
            grade_of.get(item.skill_code, 7),
            hints_shown,
            repeat,
            condition,
        )
        for condition in conditions
        for item in items
        for hints_shown in range(cfg.max_hint_level + 1)
        for repeat in range(cfg.repeats)
    ]
    return list(await asyncio.gather(*jobs))


def build_curves(
    cfg: Config,
    items: list[Item],
    attempts: list[Attempt],
    conditions: list[str] | None = None,
) -> list[Curve]:
    """Collapse attempts into one accuracy-versus-hints-shown curve per cell."""
    conditions = conditions or [HINTS_ONLY]
    buckets: dict[tuple[str, str, str], list[list[bool]]] = {
        (item.skill_code, item.language, condition): [
            [] for _ in range(cfg.max_hint_level + 1)
        ]
        for item in items
        for condition in conditions
    }
    for a in attempts:
        key = (a.skill_code, a.language, a.condition)
        if key in buckets:
            buckets[key][a.hints_shown].append(a.correct)

    curves: list[Curve] = []
    for condition in conditions:
        for item in items:
            cells = buckets[(item.skill_code, item.language, condition)]
            curves.append(
                Curve(
                    skill_code=item.skill_code,
                    language=item.language,
                    condition=condition,
                    intended_leak_level=item.intended_leak_level,
                    accuracy=[
                        (sum(cell) / len(cell)) if cell else 0.0 for cell in cells
                    ],
                )
            )
    return curves
