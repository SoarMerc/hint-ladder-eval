"""Run configuration and cost table.

Everything tunable lives here so a reader can see the whole parameter surface
in one screen.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
RESULTS = ROOT / "results"
CACHE = RESULTS / "cache"

# USD per million tokens: (input, output). Checked against
# ai.google.dev/gemini-api/docs/pricing in July 2026, and these move.
#
# Billing is per token, there's no per-request charge. Thinking tokens bill at
# the output rate, which is most of the bill here since the author model can't
# turn thinking off.
#
# Only put a model here if you've checked its price. Anything missing still
# gets its tokens counted, it just reports "not priced" instead of a guess.
#
# (gemini-3.1-pro-preview goes to 4.00/18.00 above 200k input tokens. Nothing
# here gets close.)
PRICES: dict[str, tuple[float, float]] = {
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.6-flash": (1.50, 7.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
}

LANGUAGE_NAMES = {"en": "English", "es": "Spanish", "fr": "French"}


class Config(BaseModel):
    """Knobs for one run of the harness."""

    # Writes the questions and hint ladders, so use the strongest model.
    author_model: str = "gemini-3.1-pro-preview"

    # Runs with thinking off, so it has to be a model that allows that.
    # gemini-3.1-pro-preview rejects thinking_budget=0 and can't be used here.
    student_model: str = "gemini-3.1-flash-lite"

    # Just decides whether two answers mean the same thing. Doesn't need much.
    judge_model: str = "gemini-3.1-flash-lite"

    # Has to be independent of the author and at least as good, otherwise a
    # mismatch tells you about the tagger rather than the question.
    tagger_model: str = "gemini-3.1-pro-preview"

    # --- experiment shape ---------------------------------------------------
    languages: list[str] = Field(default_factory=lambda: ["en", "es", "fr"])
    max_hint_level: int = 4
    repeats: int = 5  # student attempts per (skill, language, hint level) cell
    skills_limit: int | None = None  # cap the fixture for a quick run

    # --- detection thresholds ----------------------------------------------
    # Smallest score jump that counts as a cliff.
    jump_threshold: float = 0.35
    # How many standard errors a jump has to clear before we believe it. With
    # 5 repeats a score can only be 0/20/40/60/80/100, so neighbouring points
    # can differ by 40 on luck alone.
    noise_z: float = 2.0
    # A real leak holds the score up for the rest of the ladder; a noise blip
    # falls back down.
    sustain_tolerance: float = 0.15
    # A leak means the student can now answer, not just answer a bit better.
    leak_floor: float = 0.70
    # Accuracy at zero hints above this means the question is guessable, which
    # is a different defect but still a defect.
    trivial_baseline: float = 0.60
    # If the full ladder lifts accuracy by less than this, the cell produced no
    # usable signal and we say so instead of inventing a leakage level.
    min_span: float = 0.20

    # --- execution ----------------------------------------------------------
    concurrency: int = 8
    max_retries: int = 5
    retry_delay: int = 5  # seconds, linear backoff
    seed: int = 7
    mock: bool = False
    use_cache: bool = True

    def price(self, model: str) -> tuple[float, float]:
        return PRICES.get(model, (0.0, 0.0))
