"""explain_results: turns the numbers of one index result into plain English.

Hybrid design:
  - facts + details  -> built by fixed rules (always correct, no LLM)
  - summary          -> written by the LLM from those facts only (falls back to rules)

Put this file in ai_service/app/analysis/explain.py
"""

import os
from dotenv import load_dotenv
from .tools import ROOT
from ..registry import registry as reg

load_dotenv(ROOT / ".env")
MODEL = os.getenv("LLM_MODEL", "groq:llama-3.3-70b-versatile")

# ---------------- rules: classify the MEAN value of each index ----------------
# (upper_bound, class_key) checked in order; the last one has no upper bound.
LEVELS = {
    "NDVI": [(0.0, "water"), (0.1, "barren_built"), (0.2, "sparse_veg"),
             (0.5, "moderate_veg"), (None, "dense_veg")],
    "NDWI": [(-0.1, "mostly_land"), (0.1, "some_moisture"), (None, "water_dominated")],
    "NDBI": [(-0.1, "low_built"), (0.1, "mixed"), (None, "built_up")],
    "MNDWI": [(0.0, "mostly_land"), (0.2, "some_moisture"), (None, "water_dominated")],
    "NDMI": [(-0.2, "dry_bare"), (0.0, "low_moisture"), (0.2, "moderate_moisture"),
             (None, "high_moisture")],
}

LEVEL_TEXT = {
    "water": "dominated by water",
    "barren_built": "mostly built-up or bare ground",
    "sparse_veg": "sparse vegetation or urban area",
    "moderate_veg": "moderate vegetation",
    "dense_veg": "dense vegetation",
    "mostly_land": "mostly land with little water",
    "some_moisture": "noticeable moisture or water",
    "water_dominated": "dominated by water",
    "low_built": "little built-up area",
    "mixed": "mixed built-up and open land",
    "built_up": "dominated by built-up area",
    "dry_bare": "mostly bare soil or very dry surfaces",
    "low_moisture": "dry or sparse vegetation",
    "moderate_moisture": "vegetation with moderate water content",
    "high_moisture": "moist, well-watered vegetation",
}

# What the MIN and MAX usually mean for each index (shown only when the value is extreme).
EXTREMES = {
    "NDVI": {"min": (-0.1, "negative values: water (e.g. a river) or shadow"),
             "max": (0.6, "dense, healthy vegetation (farmland, parks)")},
    "NDWI": {"max": (0.3, "clear open water")},
    "NDBI": {"max": (0.2, "dense built-up areas")},
    "MNDWI": {"max": (0.2, "open water")},
    "NDMI": {"max": (0.4, "well-watered, dense vegetation")},
}


def _classify(index: str, mean: float) -> str:
    levels = LEVELS.get(index, LEVELS["NDVI"])
    for upper, key in levels:
        if upper is None or mean < upper:
            return key
    return levels[-1][1]


def build_facts(index: str, steps: dict, plan: dict) -> dict:
    """Only facts that can be proven from the pipeline output. No LLM here."""
    st, sel = steps["compute_statistics"], steps["select_image"]
    cloud, valid = sel["tile_cloud_pct"], st["valid_pixel_pct"]
    quality = ("good" if cloud < 10 and valid > 90
               else "fair" if cloud <= 20 and valid > 70 else "poor")
    return {
        "index": index, "index_name": reg.get_index(index).name,
        "mean": st["mean"], "min": st["min"], "max": st["max"], "std": st["std"],
        "level": _classify(index, st["mean"]),
        "variability": "high" if st["std"] > 0.2 else "low" if st["std"] < 0.1 else "moderate",
        "quality": quality, "cloud_pct": cloud, "valid_pct": valid,
        "image_date": sel["date"], "area_km2": steps["describe_aoi"].get("area_km2"),
        "exact_day_requested": bool(plan.get("image_date")),
        "window": [plan.get("start_date"), plan.get("end_date")],
        "assumptions": plan.get("assumptions", []),
    }


def build_details(f: dict) -> list[str]:
    idx = f["index"]
    out = [f"Mean {idx} = {f['mean']}: {LEVEL_TEXT[f['level']]}."]
    if f["variability"] == "high":
        out.append(f"High variability across the area (std = {f['std']}).")
    elif f["variability"] == "low":
        out.append(f"Low variability across the area (std = {f['std']}).")
    ext = EXTREMES.get(idx, {})
    if "min" in ext and f["min"] < ext["min"][0]:
        out.append(f"Lowest value {f['min']}: {ext['min'][1]}.")
    if "max" in ext and f["max"] > ext["max"][0]:
        out.append(f"Highest value {f['max']}: {ext['max'][1]}.")
    return out


def build_quality(f: dict) -> str:
    label = {"good": "Excellent", "fair": "Acceptable", "poor": "Poor"}[f["quality"]]
    text = f"{label} quality: {f['cloud_pct']}% cloud and {f['valid_pct']}% valid pixels."
    return text + (" Use the result with caution." if f["quality"] == "poor" else "")


def build_notes(f: dict) -> list[str]:
    if f["exact_day_requested"]:
        notes = [f"The result is based on the image of {f['image_date']}, as requested."]
    else:
        notes = [f"The result is based on ONE image dated {f['image_date']} (the newest suitable "
                 f"image between {f['window'][0]} and {f['window'][1]}), not an average of the "
                 "whole period."]
    return notes + list(f["assumptions"])


# ---------------- LLM: summary only ----------------

_agent = None


def _llm_summary(f: dict, details: list[str]) -> str:
    global _agent
    from pydantic_ai import Agent
    from pydantic_ai.models.groq import GroqModelSettings

    if _agent is None:
        _agent = Agent(
            MODEL, output_type=str, retries=1,
            instructions=("You are a remote-sensing assistant. Using ONLY the facts given, write a "
                          "2-3 sentence plain-English summary for a non-expert. Do not invent "
                          "numbers, places or causes."),
            model_settings=GroqModelSettings(groq_reasoning_effort="low"),
        )
    prompt = f"Facts: {f}\nKey points:\n- " + "\n- ".join(details)
    return _agent.run_sync(prompt).output.strip()


# ---------------- the tool ----------------

def explain_results(index: str, steps: dict, plan: dict, use_llm: bool = True) -> dict:
    """Same style as the other tools: returns a small dict, or {"error": ...}."""
    try:
        facts = build_facts(index, steps, plan)
        details = build_details(facts)

        summary = (f"Area of {facts['area_km2']} km² on {facts['image_date']}: "
                   f"{LEVEL_TEXT[facts['level']]}.")
        source = "rules"
        if use_llm:
            try:
                summary, source = _llm_summary(facts, details), "llm"
            except Exception:           # LLM down or rate limit -> keep the rule-based summary
                pass

        return {"summary": summary, "details": details,
                "data_quality": build_quality(facts), "notes": build_notes(facts),
                "source": source, "facts": facts}
    except Exception as e:              # the explanation must never break the analysis
        return {"error": f"explain_results failed: {type(e).__name__}: {e}"}