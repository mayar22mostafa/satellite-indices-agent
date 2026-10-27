"""What the planner agent may answer, and the full plan the engineer approves."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..registry import registry as reg

# The allowed index names come from Somaya's registry (one source of truth).
IndexName = Literal[tuple(sorted(reg.INDICES))]  # type: ignore


class PlanCore(BaseModel):
    """The parts of a plan that the agent chooses (shared by PlanChoice and AnalysisPlan)."""

    indices: list[IndexName] = Field(
        ..., min_length=1, description="Indices to compute, e.g. ['NDVI']")
    max_cloud: float = Field(
        20, ge=0, le=100, description="Max cloud % of the image tile (default 20)")
    cloud_mask: bool = Field(True, description="Remove cloud pixels (keep true unless asked)")
    assumptions: list[str] = Field(
        default_factory=list,
        description="Every choice you made that the engineer did not state, in short plain sentences")


class PlanChoice(PlanCore):
    """The agent's answer. New dates ONLY if the engineer's message explicitly asks for them."""

    new_start_date: date | None = Field(
        None, description="Only if the message explicitly asks for a new date range: its first day. Otherwise null")
    new_end_date: date | None = Field(
        None, description="Only if the message explicitly asks for a new date range: its last day. Otherwise null")
    new_image_date: date | None = Field(
        None, description="Only if the message explicitly asks for one exact day. Otherwise null")


class AnalysisPlan(PlanCore):
    """The full plan the engineer approves: the agent's choice + the chat's dates (set by code)."""

    start_date: date
    end_date: date
    image_date: date | None = None

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