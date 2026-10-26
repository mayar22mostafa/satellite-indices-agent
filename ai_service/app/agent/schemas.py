"""What the planner agent is allowed to answer: a plan to approve, or a question."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..registry import registry as reg

# The allowed index names come from Somaya's registry (one source of truth).
IndexName = Literal[tuple(sorted(reg.INDICES))]


class AnalysisPlan(BaseModel):
    """A plan the engineer must approve before anything is computed."""

    indices: list[IndexName] = Field(# type: ignore
        ..., min_length=1, description="Indices to compute, e.g. ['NDVI']")
    start_date: date = Field(..., description="First day of the search window (YYYY-MM-DD)")
    end_date: date = Field(..., description="Last day of the search window (YYYY-MM-DD)")
    image_date: date | None = Field(
        None, description="Only if the engineer asked for one exact day; otherwise null")
    max_cloud: float = Field(
        20, ge=0, le=100, description="Max cloud % of the image tile (default 20)")
    cloud_mask: bool = Field(True, description="Remove cloud pixels (keep true unless asked)")
    assumptions: list[str] = Field(
        default_factory=list,
        description="Every choice you made that the engineer did not state, in plain words")

    @model_validator(mode="after")
    def check_dates(self):
        today = date.today()
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if self.end_date > today:
            raise ValueError(f"end_date cannot be in the future (today is {today})")
        if self.image_date and self.image_date > today:
            raise ValueError(f"image_date cannot be in the future (today is {today})")
        return self


class ClarifyingQuestion(BaseModel):
    """Asked when the request is too unclear to plan safely."""

    question: str = Field(..., description="One short question for the engineer")
    reason: str = Field(..., description="Why you cannot plan without the answer")