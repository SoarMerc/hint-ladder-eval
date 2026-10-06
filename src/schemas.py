"""Data shapes passed between stages.

Validating at each boundary means a malformed model response blows up next to
the call that produced it, rather than three stages later as a strange number
in the report.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Skill(BaseModel):
    code: str
    subject: str
    grade: int
    description: str


class Item(BaseModel):
    """One question plus its hint ladder, in one language."""

    skill_code: str
    language: str
    question: str
    answer: str
    hints: list[str]
    intended_leak_level: int

    @field_validator("hints")
    @classmethod
    def _ladder_must_be_populated(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("hint ladder is empty")
        if any(not h.strip() for h in v):
            raise ValueError("hint ladder contains an empty rung")
        return v


class Attempt(BaseModel):
    """One student run at one point on the ladder."""

    skill_code: str
    language: str
    condition: str  # hints_only | with_question
    hints_shown: int
    repeat: int
    response: str
    correct: bool
    graded_by: str  # "exact" or "judge"


class Curve(BaseModel):
    """Accuracy as a function of how many hints the student was shown."""

    skill_code: str
    language: str
    condition: str = "hints_only"
    intended_leak_level: int
    accuracy: list[float]  # index k = accuracy with k hints shown, k in 0..N

    @field_validator("accuracy")
    @classmethod
    def _within_unit_interval(cls, v: list[float]) -> list[float]:
        if any(a < 0.0 or a > 1.0 for a in v):
            raise ValueError("accuracy outside [0, 1]")
        return v


class Detection(BaseModel):
    """What the detector concluded about one curve."""

    skill_code: str
    language: str
    condition: str = "hints_only"
    intended_leak_level: int
    leak_level: int | None  # level of the largest accuracy jump, if any
    jump_size: float
    baseline: float  # accuracy with no hints
    ceiling: float  # accuracy with the full ladder
    status: str  # ok | leaked | trivial | no_signal
    note: str = ""

    @property
    def flagged(self) -> bool:
        return self.status in {"leaked", "trivial"}


class TagCheck(BaseModel):
    """Blind re-tag of a generated item against its claimed standard."""

    skill_code: str
    predicted_code: str
    match: bool


class CostLine(BaseModel):
    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0
    # False when no verified price exists for this model. Token counts are
    # still real; the dollar figure is simply not claimed.
    priced: bool = True


class RunReport(BaseModel):
    mock: bool
    curves: list[Curve]
    detections: list[Detection]
    tag_checks: list[TagCheck] = Field(default_factory=list)
    costs: list[CostLine] = Field(default_factory=list)

    @property
    def total_usd(self) -> float:
        return sum(c.usd for c in self.costs)
