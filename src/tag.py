"""Standards drift check.

Show a second model just the question, without telling it which standard the
question was written for, and ask it to pick one from the list. If it picks a
different one, the question has drifted from its label.
"""

from __future__ import annotations

import asyncio

from .client import ModelClient
from .config import Config
from .schemas import Item, Skill, TagCheck

TAG_SYSTEM = """You classify practice questions against the Common Core standards.

You are given a question and a list of candidate standard codes with their
descriptions. Choose the single code whose standard the question most directly
assesses.

Reply with one code from the list, exactly as written. You have not been told
which standard the question was written for, and there is no partial credit for
being close."""

TAG_USER = """Candidate standards:
{candidates}

Question:
{question}

Which single standard code does this question assess?"""


async def _tag_one(
    client: ModelClient, cfg: Config, item: Item, skills: list[Skill]
) -> TagCheck:
    candidates = "\n".join(f"- {s.code}: {s.description}" for s in skills)
    distractor = next(
        (s.code for s in skills if s.code != item.skill_code), item.skill_code
    )
    data = await client.json_call(
        kind="tag",
        model=cfg.tagger_model,
        system=TAG_SYSTEM,
        user=TAG_USER.format(candidates=candidates, question=item.question),
        # The tagger model is forced to think, and thinking tokens draw from
        # this budget, so 256 leaves nothing for the JSON body.
        max_tokens=2048,
        temperature=0.0,
        ctx={"skill": item.skill_code, "distractor": distractor},
    )
    predicted = str(data["code"]).strip()
    return TagCheck(
        skill_code=item.skill_code,
        predicted_code=predicted,
        match=predicted == item.skill_code,
    )


async def check_drift(
    client: ModelClient, cfg: Config, items: list[Item], skills: list[Skill]
) -> list[TagCheck]:
    """Only English items are re-tagged; translation is a separate question."""
    english = [i for i in items if i.language == "en"]
    return list(
        await asyncio.gather(*(_tag_one(client, cfg, i, skills) for i in english))
    )


def drift_rate(checks: list[TagCheck]) -> float:
    if not checks:
        return 0.0
    return 1.0 - sum(c.match for c in checks) / len(checks)
