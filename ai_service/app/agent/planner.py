"""Planner agent: turns an engineer's request into a plan to approve (or a question).

It may LOOK at the area and the available images (read-only tools),
but it never computes indices. Computing happens only after approval.
"""

import argparse
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext
from pydantic_ai.usage import UsageLimits
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.groq import GroqModelSettings

from ..analysis import tools
from ..analysis.context import RunContext as AnalysisContext
from .schemas import AnalysisPlan, ClarifyingQuestion

load_dotenv(tools.ROOT / ".env")          # GROQ_API_KEY and LLM_MODEL must be loaded before the Agent

PROMPT_FILE = Path(__file__).parent / "prompts" / "planner_v1.md"
MODEL = os.getenv("LLM_MODEL", "groq:llama-3.3-70b-versatile")
LIMITS = UsageLimits(request_limit=8)     # max LLM calls per message (stops endless loops)


@dataclass
class PlannerDeps:
    """What the agent's tools need. The LLM never sees or chooses these."""
    aoi_id: str
    analysis: AnalysisContext = field(default_factory=AnalysisContext)


planner = Agent(
    MODEL,
    deps_type=PlannerDeps,
    output_type=PromptedOutput([AnalysisPlan, ClarifyingQuestion]),
    instructions=PROMPT_FILE.read_text(),
    retries=2,
    model_settings=GroqModelSettings(groq_reasoning_effort="low"),
)


@planner.instructions
def todays_date(ctx: RunContext[PlannerDeps]) -> str:
    return f"Today's date is {date.today().isoformat()}."


def _load_area(deps: PlannerDeps) -> dict | None:
    """Load the area into the analysis context once; return an error dict if it fails."""
    if deps.aoi_id in deps.analysis.aois:
        return None
    info = tools.describe_aoi(deps.analysis, deps.aoi_id)
    return info if "error" in info else None


@planner.output_validator
def check_images_exist(ctx: RunContext[PlannerDeps], output):
    """Code check: never hand the engineer a plan that would find no image."""
    if not isinstance(output, AnalysisPlan):
        return output
    deps = ctx.deps
    error = _load_area(deps)
    if error:
        raise ModelRetry(f"The area cannot be used: {error['error']}. Ask the engineer about it.")

    if output.image_date:
        day = output.image_date.isoformat()
        found = tools.select_image(deps.analysis, deps.aoi_id, date=day)
        if "error" in found:
            nearest = found.get("nearest_dates", [])
            raise ModelRetry(f"There is no Sentinel-2 image on {day}. Nearest available days: "
                             f"{nearest}. Return a ClarifyingQuestion offering these days.")
    else:
        found = tools.find_images(deps.analysis, deps.aoi_id, output.start_date.isoformat(),
                                  output.end_date.isoformat(), output.max_cloud)
        if "error" in found:
            raise ModelRetry(found["error"])
        if found["count"] == 0:
            raise ModelRetry("No clear images match this window and cloud limit. Widen the "
                             "window (up to 90 days) and say so in assumptions.")
    return output


FORMAT_ERRORS = ("output_parse_failed", "tool_use_failed", "json_validate_failed")   # model answered in a broken format


def plan_turn(message: str, deps: PlannerDeps, history: list | None = None, attempts: int = 3):
    """One chat turn. Returns (AnalysisPlan or ClarifyingQuestion, updated history).

    Retries when the model sends a badly formatted answer (a known, random gpt-oss quirk).
    """
    for attempt in range(1, attempts + 1):
        try:
            result = planner.run_sync(message, deps=deps, message_history=history,
                                      usage_limits=LIMITS)
            return result.output, result.all_messages()
        except ModelHTTPError as e:
            is_format_error = any(code in str(e.body) for code in FORMAT_ERRORS)
            if not is_format_error or attempt == attempts:
                raise


def main():
    parser = argparse.ArgumentParser(description="Chat with the planner in the terminal.")
    parser.add_argument("--aoi", default="cairo_box", help="area id in data/aoi/")
    args = parser.parse_args()

    tools.init_earth_engine()
    deps = PlannerDeps(aoi_id=args.aoi)
    history = None
    print(f"Planner ready ({MODEL}), area '{args.aoi}'. Type 'quit' to stop.")

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