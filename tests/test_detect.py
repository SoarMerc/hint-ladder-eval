"""Tests for the part that decides what counts as a defect."""

from __future__ import annotations

from src.config import Config
from src.detect import cross_language_gaps, detect_one, largest_jump, summarise
from src.schemas import Curve, Detection

CFG = Config(mock=True)


def curve(acc, language="en", skill="7.EE.B.4", intended=4) -> Curve:
    return Curve(
        skill_code=skill,
        language=language,
        intended_leak_level=intended,
        accuracy=acc,
    )


def test_largest_jump_names_the_hint_that_caused_the_rise():
    level, size = largest_jump([0.1, 0.2, 0.9, 0.9, 0.9])
    assert level == 2
    assert size == pytest_approx(0.7)


def test_gradual_ladder_is_ok():
    d = detect_one(curve([0.10, 0.25, 0.40, 0.55, 0.70]), CFG)
    assert d.status == "ok"
    assert d.leak_level is None
    assert not d.flagged


def test_early_cliff_is_flagged_as_leaked():
    d = detect_one(curve([0.10, 0.15, 0.85, 0.85, 0.90]), CFG)
    assert d.status == "leaked"
    assert d.leak_level == 2
    assert d.flagged


def test_cliff_at_the_final_hint_is_intended_not_a_leak():
    d = detect_one(curve([0.10, 0.15, 0.20, 0.25, 0.90]), CFG)
    assert d.status == "ok"
    assert d.leak_level == 4
    assert not d.flagged


def test_guessable_question_is_flagged_even_though_no_hint_leaked():
    d = detect_one(curve([0.80, 0.85, 0.85, 0.90, 0.95]), CFG)
    assert d.status == "trivial"
    assert d.leak_level is None
    assert d.flagged


def test_flat_curve_reports_no_signal_rather_than_inventing_a_level():
    d = detect_one(curve([0.20, 0.22, 0.21, 0.24, 0.25]), CFG)
    assert d.status == "no_signal"
    assert d.leak_level is None
    assert not d.flagged


def test_cross_language_gap_is_reported_only_when_it_gets_worse():
    dets = [
        Detection(
            skill_code="7.EE.B.4",
            language="en",
            intended_leak_level=4,
            leak_level=4,
            jump_size=0.5,
            baseline=0.1,
            ceiling=0.8,
            status="ok",
        ),
        Detection(
            skill_code="7.EE.B.4",
            language="es",
            intended_leak_level=4,
            leak_level=2,
            jump_size=0.6,
            baseline=0.1,
            ceiling=0.8,
            status="leaked",
        ),
        Detection(
            skill_code="7.EE.B.4",
            language="fr",
            intended_leak_level=4,
            leak_level=4,
            jump_size=0.5,
            baseline=0.1,
            ceiling=0.8,
            status="ok",
        ),
    ]
    rows = cross_language_gaps(dets)
    assert len(rows) == 1
    assert rows[0]["language"] == "es"
    assert rows[0]["levels_earlier"] == 2


def test_summarise_counts_every_status():
    dets = [detect_one(curve([0.1, 0.15, 0.85, 0.85, 0.9]), CFG)]
    assert summarise(dets)["leaked"] == 1


def pytest_approx(value: float, tol: float = 1e-9):
    class _Approx:
        def __eq__(self, other):  # noqa: D105
            return abs(other - value) < tol

        def __repr__(self):  # noqa: D105
            return f"~{value}"

    return _Approx()
