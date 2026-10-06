"""Writes the questions, answers and hint ladders.

All generated at runtime. Nothing is copied from any product and no external
site is fetched.
"""

from __future__ import annotations

import asyncio

import yaml

from .client import ModelClient
from .config import FIXTURES, LANGUAGE_NAMES, Config
from .schemas import Item, Skill

AUTHOR_SYSTEM = """You write practice items for a middle-school mastery-learning tutor.

You produce three things for one Common Core standard:

1. A question a student in the given grade can answer. For ELA standards,
   include a short original passage (4-8 sentences) inside the question itself,
   because the student will see nothing but your question.
2. The ground-truth answer, stated as briefly as it can be stated. A number, a
   short phrase, or one sentence. No working, no explanation.
3. A ladder of exactly {levels} hints that scaffold a struggling student toward
   the answer without handing it over.

Rules for the hint ladder, which matter more than anything else here:

- Hint 1 is a broad orienting question. It should help a stuck student start,
  and almost nothing more.
- Each later hint is more supportive than the one before it.
- Hint {levels} is maximally supportive: it may name the method, set up the
  work, and walk right up to the final step. It must still stop short of
  stating the answer.
- NO hint at any level may contain the ground-truth answer, restate it in other
  words, or make it derivable in a single trivial step before the last level.

The point of the ladder is that the student does the thinking. A hint that
supplies the answer has failed, however helpful it sounds."""

AUTHOR_USER = """Standard: {code}
Subject: {subject}
Grade: {grade}
Description: {description}

Write the question, the ground-truth answer, and the {levels}-hint ladder."""

TRANSLATE_SYSTEM = """You translate tutoring content between languages.

Translate the question and every hint into {language}. Preserve each hint's
level of support exactly: a hint that only orients the student in the source
language must only orient the student in the target language, and a hint that
withholds the answer must still withhold it.

Do not add information. Do not remove information. Do not make any hint more
or less helpful than its source. Never state the answer, in any language."""

TRANSLATE_USER = """Question:
{question}

Hints:
{hints}

Translate all of it into {language}."""


def load_skills(cfg: Config) -> list[Skill]:
    raw = yaml.safe_load((FIXTURES / "skills.yaml").read_text(encoding="utf-8"))
    skills = [Skill(**row) for row in raw]
    if cfg.skills_limit:
        skills = skills[: cfg.skills_limit]
    return skills


async def author_item(client: ModelClient, cfg: Config, skill: Skill) -> Item:
    """Write the English item. Every other language is derived from this one."""
    data = await client.json_call(
        kind="author",
        model=cfg.author_model,
        system=AUTHOR_SYSTEM.format(levels=cfg.max_hint_level),
        user=AUTHOR_USER.format(
            code=skill.code,
            subject=skill.subject,
            grade=skill.grade,
            description=skill.description,
            levels=cfg.max_hint_level,
        ),
        # Thinking tokens draw from this budget on 2.5 models, so it is set well
        # above what the JSON itself needs.
        max_tokens=8192,
        ctx={"skill": skill.code, "language": "en", "max_level": cfg.max_hint_level},
    )
    hints = _fit_ladder(data["hints"], cfg.max_hint_level)
    return Item(
        skill_code=skill.code,
        language="en",
        question=data["question"],
        answer=data["answer"],
        hints=hints,
        # The ladder is written so that nothing before the last rung should give
        # the answer away. A leak detected earlier than this is the defect.
        intended_leak_level=cfg.max_hint_level,
    )


async def translate_item(
    client: ModelClient, cfg: Config, base: Item, language: str
) -> Item:
    """Same question, same answer, translated ladder.

    Translating instead of writing a new question per language keeps the item
    fixed, so any difference between languages comes from the hints.
    """
    numbered = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(base.hints))
    data = await client.json_call(
        kind="translate",
        model=cfg.author_model,
        system=TRANSLATE_SYSTEM.format(language=LANGUAGE_NAMES[language]),
        user=TRANSLATE_USER.format(
            question=base.question,
            hints=numbered,
            language=LANGUAGE_NAMES[language],
        ),
        # Thinking tokens draw from this budget on 2.5 models, so it is set well
        # above what the JSON itself needs.
        max_tokens=8192,
        ctx={
            "skill": base.skill_code,
            "language": language,
            "max_level": cfg.max_hint_level,
        },
    )
    return Item(
        skill_code=base.skill_code,
        language=language,
        question=data["question"],
        answer=base.answer,  # graded against the original ground truth
        hints=_fit_ladder(data["hints"], cfg.max_hint_level),
        intended_leak_level=base.intended_leak_level,
    )


async def build_items(client: ModelClient, cfg: Config) -> list[Item]:
    skills = load_skills(cfg)
    bases = await asyncio.gather(*(author_item(client, cfg, s) for s in skills))

    items: list[Item] = list(bases)
    others = [lang for lang in cfg.languages if lang != "en"]
    if others:
        translated = await asyncio.gather(
            *(
                translate_item(client, cfg, base, lang)
                for base in bases
                for lang in others
            )
        )
        items.extend(translated)
    return items


def _fit_ladder(hints: list[str], levels: int) -> list[str]:
    """Models occasionally return one rung too many or too few."""
    hints = [h.strip() for h in hints if h and h.strip()]
    if not hints:
        raise ValueError("author returned no usable hints")
    if len(hints) > levels:
        return hints[:levels]
    while len(hints) < levels:
        hints.append(hints[-1])
    return hints
