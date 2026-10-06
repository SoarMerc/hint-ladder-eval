"""Decides whether a curve counts as a leak.

No network calls here, just the rules. Kept small, since this is the part
people will want to argue with.

A curve that sits flat and then jumps to ~100% and stays there means one hint
handed over the answer. A curve that climbs gradually means each hint did a bit
of the work and the student still had something to do.
"""

from __future__ import annotations

import math

from .config import Config
from .schemas import Curve, Detection


def largest_jump(accuracy: list[float]) -> tuple[int, float]:
    """Return (level, size) of the biggest single-step rise in accuracy.

    Level is 1-indexed: level k is the step from k-1 hints to k hints, so it
    names the hint that caused the rise.
    """
    steps = [accuracy[k] - accuracy[k - 1] for k in range(1, len(accuracy))]
    if not steps:
        return 0, 0.0
    size = max(steps)
    return steps.index(size) + 1, size


def noise_floor(p_before: float, p_after: float, repeats: int, z: float) -> float:
    """Smallest jump that isn't explainable by luck.

    Each point is a proportion over `repeats` trials, so the gap between two
    adjacent points has a standard error. At 5 repeats that error is big.
    """
    if repeats <= 0:
        return 1.0
    var = (p_before * (1 - p_before) + p_after * (1 - p_after)) / repeats
    return z * math.sqrt(var)


def cliff_at(acc: list[float], level: int, cfg: Config) -> tuple[bool, float]:
    """Does hint `level` look like it handed the answer over?

    All three have to hold, and each rules out a different way of being wrong:

    1. the rise beats the sampling noise, otherwise we're reading a coin flip
    2. the score afterwards is actually high - 10% to 45% means the hint helped,
       which is its job
    3. the score stays up for the rest of the ladder, since a spike that falls
       away was noise
    """
    step = acc[level] - acc[level - 1]
    required = max(
        cfg.jump_threshold,
        noise_floor(acc[level - 1], acc[level], cfg.repeats, cfg.noise_z),
    )
    big_enough = step >= required
    high_enough = acc[level] >= cfg.leak_floor
    sustained = min(acc[level:]) >= acc[level] - cfg.sustain_tolerance
    return (big_enough and high_enough and sustained), step


def detect_one(curve: Curve, cfg: Config) -> Detection:
    acc = curve.accuracy
    baseline, ceiling = acc[0], acc[-1]
    level, size = largest_jump(acc)

    # The leak is where the answer FIRST becomes available, not where the
    # largest step happens to be.
    cliffs = [
        (k, step)
        for k in range(1, len(acc))
        for ok, step in [cliff_at(acc, k, cfg)]
        if ok
    ]
    if cliffs:
        level, size = cliffs[0]

    def build(status: str, leak: int | None, note: str) -> Detection:
        return Detection(
            skill_code=curve.skill_code,
            language=curve.language,
            condition=curve.condition,
            intended_leak_level=curve.intended_leak_level,
            leak_level=leak,
            jump_size=round(size, 3),
            baseline=round(baseline, 3),
            ceiling=round(ceiling, 3),
            status=status,
            note=note,
        )

    # Checked first: if the student can already answer without any hints, the
    # curve cannot tell us anything about the ladder, and the item itself is
    # the problem.
    if baseline >= cfg.trivial_baseline:
        return build(
            "trivial",
            None,
            f"answerable {baseline:.0%} of the time with no hints at all",
        )

    if ceiling - baseline < cfg.min_span:
        return build(
            "no_signal",
            None,
            "the full ladder barely moved accuracy, so leakage is not measurable here",
        )

    if cliffs and level < curve.intended_leak_level:
        return build(
            "leaked",
            level,
            f"accuracy jumped {size:.0%} at hint {level} and stayed up, "
            f"{curve.intended_leak_level - level} level(s) earlier than intended",
        )

    if cliffs:
        return build(
            "ok", level, f"the answer becomes available at hint {level}, as intended"
        )

    return build("ok", None, "accuracy rose gradually across the ladder")


def detect_all(curves: list[Curve], cfg: Config) -> list[Detection]:
    return [detect_one(c, cfg) for c in curves]


def cross_language_gaps(detections: list[Detection]) -> list[dict[str, object]]:
    """Skills whose leak level moves when the ladder changes language."""
    by_skill: dict[tuple[str, str], dict[str, Detection]] = {}
    for d in detections:
        by_skill.setdefault((d.skill_code, d.condition), {})[d.language] = d

    rows: list[dict[str, object]] = []
    for (skill, _condition), langs in sorted(by_skill.items()):
        base = langs.get("en")
        if base is None:
            continue
        for language, det in sorted(langs.items()):
            if language == "en":
                continue
            base_level = base.leak_level or base.intended_leak_level
            other_level = det.leak_level or det.intended_leak_level
            if other_level < base_level:
                rows.append(
                    {
                        "skill_code": skill,
                        "language": language,
                        "en_leak_level": base_level,
                        "leak_level": other_level,
                        "levels_earlier": base_level - other_level,
                    }
                )
    return rows


def summarise(detections: list[Detection]) -> dict[str, int]:
    counts = {"ok": 0, "leaked": 0, "trivial": 0, "no_signal": 0}
    for d in detections:
        counts[d.status] = counts.get(d.status, 0) + 1
    return counts
