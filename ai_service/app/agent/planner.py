"""Planner agent: turns an engineer's message into a plan to approve (or a question).

The engineer picks the dates in the app, and code puts them into the plan.
The agent only chooses WHAT to analyze. It never computes anything: that happens
only after approval.
"""

import argparse
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.groq import GroqModelSettings
from pydantic_ai.usage import UsageLimits

from ..analysis import tools
from ..analysis.context import RunContext as AnalysisContext
from .schemas import AnalysisPlan, ClarifyingQuestion, PlanChoice

load_dotenv(tools.ROOT / ".env")          # GROQ_API_KEY and LLM_MODEL must be loaded before the Agent

PROMPT_FILE = Path(__file__).parent / "prompts" / "planner_v2.md"
MODEL = os.getenv("LLM_MODEL", "groq:openai/gpt-oss-120b")
LIMITS = UsageLimits(request_limit=8)     # max LLM calls per message (stops endless loops)
FORMAT_ERRORS = ("output_parse_failed", "tool_use_failed", "json_validate_failed")


@dataclass
class PlannerDeps:
    """What the agent's checks need. The LLM never sees or chooses these."""
    aoi_id: str
    start_date: date | None = None        # the engineer's range ...
    end_date: date | None = None
    image_date: date | None = None        # ... or one exact day
    analysis: AnalysisContext = field(default_factory=AnalysisContext)


planner = Agent(
    MODEL,
    deps_type=PlannerDeps,
    output_type=PromptedOutput([PlanChoice, ClarifyingQuestion]),
    instructions=PROMPT_FILE.read_text(),
    retries=2,
    model_settings=GroqModelSettings(groq_reasoning_effort="low"),
)


@planner.instructions
def todays_date(ctx: RunContext[PlannerDeps]) -> str:
    return f"Today's date is {date.today().isoformat()}."


@planner.instructions
def selected_dates(ctx: RunContext[PlannerDeps]) -> str:
    d = ctx.deps
    if d.image_date:
        current = f"one exact day, {d.image_date.isoformat()}"
    else:
        current = f"the range {d.start_date.isoformat()} to {d.end_date.isoformat()}"
    return (f"The current dates of this chat are {current}. Use them unless the engineer's "
            "message explicitly asks for different dates (rule 3).")


def _load_area(deps: PlannerDeps) -> dict | None:
    """Load the area into the analysis context once; return an error dict if it fails."""
    if deps.aoi_id in deps.analysis.aois:
        return None
    info = tools.describe_aoi(deps.analysis, deps.aoi_id)
    return info if "error" in info else None


def _plan_dates(choice: PlanChoice, deps: PlannerDeps) -> tuple:
    """(start, end, image_date) this choice will use: new dates from the message, else the current ones."""
    if choice.new_image_date:
        return None, None, choice.new_image_date
    if choice.new_start_date or choice.new_end_date:
        return choice.new_start_date, choice.new_end_date, None
    return deps.start_date, deps.end_date, deps.image_date


@planner.output_validator
def check_choice(ctx: RunContext[PlannerDeps], output):
    """Code checks: valid dates, and images exist for them. Otherwise the agent must fix it or ask."""
    if not isinstance(output, PlanChoice):
        return output
    deps = ctx.deps
    start, end, day = _plan_dates(output, deps)
    today = date.today()

    if day is None and (start is None or end is None):
        raise ModelRetry("Give both new_start_date and new_end_date, or only new_image_date.")
    if (day or end) > today:
        raise ModelRetry(f"Dates cannot be in the future (today is {today}). "
                         "Return a ClarifyingQuestion asking for past dates.")
    if day is None and start > end:
        raise ModelRetry("new_start_date must be on or before new_end_date.")

    error = _load_area(deps)
    if error:
        raise ModelRetry(f"The area cannot be used: {error['error']}. Ask the engineer about it.")

    if day:
        found = tools.select_image(deps.analysis, deps.aoi_id, date=day.isoformat())
        if "error" in found:
            nearest = found.get("nearest_dates", [])
            raise ModelRetry(f"There is no Sentinel-2 image on {day}. Nearest available days: {nearest}. "
                             "Do not pick a day yourself. Return a ClarifyingQuestion offering these days.")
    else:
        found = tools.find_images(deps.analysis, deps.aoi_id, start.isoformat(), end.isoformat(),
                                  output.max_cloud)
        if "error" in found:
            raise ModelRetry(found["error"])
        if found["count"] == 0:
            raise ModelRetry(f"No images between {start} and {end} with cloud <= {output.max_cloud}%. "
                             "Do not change the dates yourself. Return a ClarifyingQuestion suggesting "
                             "a wider date range or a higher cloud limit.")
    return output


NEW_DATE_FIELDS = {"new_start_date", "new_end_date", "new_image_date"}


def _to_plan(choice: PlanChoice, deps: PlannerDeps) -> AnalysisPlan:
    """The agent's choice + the chat's dates = the plan. Code builds it; the new_* fields are dropped."""
    start = deps.image_date or deps.start_date
    end = deps.image_date or deps.end_date
    return AnalysisPlan(**choice.model_dump(exclude=NEW_DATE_FIELDS),
                        start_date=start, end_date=end, image_date=deps.image_date)


def plan_turn(message: str, deps: PlannerDeps, history: list | None = None, attempts: int = 3):
    """One chat turn. Returns (AnalysisPlan or ClarifyingQuestion, updated history).

    Retries when the model sends a badly formatted answer (a known, random gpt-oss quirk).
    """
    for attempt in range(1, attempts + 1):
        try:
            result = planner.run_sync(message, deps=deps, message_history=history,
                                      usage_limits=LIMITS)
            output = result.output
            if isinstance(output, PlanChoice):
                deps.start_date, deps.end_date, deps.image_date = _plan_dates(output, deps)
                output = _to_plan(output, deps)
            return output, result.all_messages()
        except ModelHTTPError as e:
            is_format_error = any(code in str(e.body) for code in FORMAT_ERRORS)
            if not is_format_error or attempt == attempts:
                raise


def main():
    parser = argparse.ArgumentParser(description="Chat with the planner in the terminal.")
    parser.add_argument("--aoi", default="cairo_box", help="area id in data/aoi/")
    parser.add_argument("--start", help="range start YYYY-MM-DD (default: 30 days before --end)")
    parser.add_argument("--end", help="range end YYYY-MM-DD (default: today)")
    parser.add_argument("--date", help="one exact day YYYY-MM-DD (instead of a range)")
    args = parser.parse_args()

    deps = PlannerDeps(aoi_id=args.aoi)
    if args.date:
        deps.image_date = date.fromisoformat(args.date)
    else:
        deps.end_date = date.fromisoformat(args.end) if args.end else date.today()
        deps.start_date = (date.fromisoformat(args.start) if args.start
                           else deps.end_date - timedelta(days=30))

    tools.init_earth_engine()
    history = None
    dates = deps.image_date or f"{deps.start_date} to {deps.end_date}"
    print(f"Planner ready ({MODEL}), area '{args.aoi}', dates {dates}. Type 'quit' to stop.")

    while True:
        message = input("\nYou: ").strip()
        if message.lower() in {"", "q", "quit", "exit"}:
            break
        try:
            output, history = plan_turn(message, deps, history)
        except Exception as e:                      # terminal test only: show and continue
            print(f"Error: {type(e).__name__}: {e}")
            continue
        print(f"\n[{type(output).__name__}]")
        print(output.model_dump_json(indent=2))


if __name__ == "__main__":
    main()