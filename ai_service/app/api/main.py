"""HTTP API of the AI service. The Node.js backend calls these endpoints."""

import json
import uuid
import ee
from contextlib import asynccontextmanager
from datetime import date

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from pydantic_ai.exceptions import AgentRunError

from ..agent.planner import PlannerDeps, plan_turn
from ..agent.schemas import AnalysisPlan
from ..analysis import tools
from ..analysis.pipeline import run_fixed_pipeline
from ..analysis.tools import AOI_DIR, init_earth_engine
from ..analysis.explain import explain_results
from ..registry.aoi import AOIError, aoi_from_geojson_bytes


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_earth_engine()          # connect to Earth Engine once, when the server starts
    yield


app = FastAPI(title="Satellite Indices AI Service", version="0.2.0", lifespan=lifespan)

# In-memory stores (MVP): everything is lost when the service restarts.
SESSIONS: dict[str, dict] = {}   # session_id -> {"aoi": GeoJSON, "deps": PlannerDeps, "history": list}
PLANS: dict[str, dict] = {}      # plan_id -> {"session_id": str, "plan": AnalysisPlan, "result": dict | None}
EXECUTOR = ThreadPoolExecutor(max_workers=2)   # at most 2 analyses run at the same time
LOCK = threading.Lock()                        # stops a double click from starting two runs
logger = logging.getLogger("ai_service")
MAX_DOWNLOAD_BYTES = 48 * 1024 * 1024          # Earth Engine's limit for one direct download
DOWNLOAD_SCALES_M = (10, 20, 30, 60)            # pixel sizes tried in order; the finest that fits wins
LONG_RANGE_DAYS = 365                           # longer ranges get a "one image, not a trend" note

# ---------------- request bodies ----------------


class PlanRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The engineer's chat message")
    session_id: str | None = Field(None, description="Omit on the first message of a chat")
    aoi: dict | None = Field(None, description="GeoJSON area: required on the first message; "
                             "optional later, to change the chat's area")
    start_date: date | None = Field(None, description="First day of the range (YYYY-MM-DD). Use with end_date.")
    end_date: date | None = Field(None, description="Last day of the range (YYYY-MM-DD). Use with start_date.")
    image_date: date | None = Field(None, description="One exact day (YYYY-MM-DD), instead of a range.")


# ---------------- helpers ----------------

def _check_aoi(aoi: dict) -> tuple[bytes, float]:
    """Validate the area (Somaya's reader). Bad area -> 400. Returns the raw file and its km²."""
    raw = json.dumps(aoi).encode()
    try:
        area = aoi_from_geojson_bytes(raw)
    except AOIError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return raw, area.area_km2


def _save_aoi(raw: bytes) -> str:
    """Save the area under a new id in data/aoi/ so the tools can load it."""
    aoi_id = f"upload_{uuid.uuid4().hex[:8]}"
    AOI_DIR.mkdir(parents=True, exist_ok=True)
    (AOI_DIR / f"{aoi_id}.geojson").write_bytes(raw)
    return aoi_id


def _read_dates(req: PlanRequest) -> tuple | None:
    """The engineer's dates from the request, checked: (start, end, image_date). None if no dates sent."""
    has_range = req.start_date is not None or req.end_date is not None
    if req.image_date is None and not has_range:
        return None
    if req.image_date is not None and has_range:
        raise HTTPException(status_code=400,
                            detail="Send either image_date, or start_date and end_date, not both.")
    today = date.today()
    if req.image_date is not None:
        if req.image_date > today:
            raise HTTPException(status_code=400, detail=f"image_date cannot be in the future (today is {today}).")
        return None, None, req.image_date
    if req.start_date is None or req.end_date is None:
        raise HTTPException(status_code=400, detail="Send both start_date and end_date.")
    if req.start_date > req.end_date:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date.")
    if req.end_date > today:
        raise HTTPException(status_code=400, detail=f"end_date cannot be in the future (today is {today}).")
    return req.start_date, req.end_date, None


def _app_notes(deps: PlannerDeps, changed: list[str]) -> list[str]:
    """Assumptions written by code (not the model): what the app changed in this message."""
    notes = []
    if "area" in changed:
        notes.append(f"Using the new area selected in the app ({deps.area_km2:,.0f} km²).")
    if "dates" in changed:
        when = (deps.image_date.isoformat() if deps.image_date
                else f"{deps.start_date.isoformat()} to {deps.end_date.isoformat()}")
        notes.append(f"Using the new dates selected in the app: {when}.")
    return notes


def _long_range_note(plan: AnalysisPlan) -> list[str]:
    """Long ranges: say before approval that one image is used, not an average or a trend."""
    if plan.image_date is None and (plan.end_date - plan.start_date).days > LONG_RANGE_DAYS:
        return ["Uses only the newest suitable image in this date range (one day), "
                "not an average or a trend over the whole period."]
    return []


def _first_error(result: dict) -> str | None:
    """The first error message in a pipeline result (top level or inside a step), or None."""
    return result.get("error") or next(
        (step["error"] for step in result.values() if isinstance(step, dict) and "error" in step),
        None,
    )


def _geometry(geojson: dict) -> dict:
    """One GeoJSON geometry for the response (several polygons become one MultiPolygon)."""
    kind = geojson.get("type")
    if kind == "Feature":
        return geojson["geometry"]
    if kind == "FeatureCollection":
        geoms = [f["geometry"] for f in geojson.get("features", []) if f.get("geometry")]
        if len(geoms) == 1:
            return geoms[0]
        parts = []
        for g in geoms:
            parts.extend([g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"])
        return {"type": "MultiPolygon", "coordinates": parts}
    return geojson


def _feature(aoi: dict, properties: dict) -> dict:
    return {"type": "Feature", "geometry": _geometry(aoi), "properties": properties}


# ---------------- endpoints ----------------

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    return {"status": "ok"}



@app.post("/plans")
def create_plan(req: PlanRequest):
    """One chat message -> a plan to approve, or a clarifying question.

    First message: aoi and dates are required. Later messages: both are optional;
    when sent, they replace the chat's current area or dates from this message on.
    """
    dates = _read_dates(req)                                    # checked before anything is changed
    checked = _check_aoi(req.aoi) if req.aoi is not None else None   # bad area -> 400, nothing changed
    first = req.session_id is None
    if first:                                                   # first message: new chat
        if checked is None:
            raise HTTPException(status_code=400,
                                detail="The first message of a chat must include 'aoi'.")
        if dates is None:
            raise HTTPException(status_code=400, detail="The first message of a chat must include "
                                "dates: start_date and end_date, or image_date.")
        session_id = f"s_{uuid.uuid4().hex[:8]}"
        SESSIONS[session_id] = {"aoi": None, "deps": PlannerDeps(aoi_id=""), "history": None}
    else:
        session_id = req.session_id
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Unknown session_id (the chat expired "
                                "or the service restarted). Start a new chat.")
    session = SESSIONS[session_id]
    deps = session["deps"]

    changed = []
    if checked is not None:                                     # a new area replaces the old one
        raw, area_km2 = checked
        deps.aoi_id, deps.area_km2 = _save_aoi(raw), area_km2
        session["aoi"] = req.aoi
        changed.append("area")
    if dates is not None:                                       # new dates replace the old ones
        deps.start_date, deps.end_date, deps.image_date = dates
        changed.append("dates")
    deps.changed_in_app = [] if first else changed             # the first message is the start, not a change
    notes = _app_notes(deps, deps.changed_in_app)

    try:
        output, session["history"] = plan_turn(req.message, deps, session["history"])
    except AgentRunError as e:
        raise HTTPException(status_code=502, detail="The AI model could not answer. "
                            f"Please try again. ({type(e).__name__})")

    if isinstance(output, AnalysisPlan):
        output.assumptions = notes + _long_range_note(output) + output.assumptions
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        PLANS[plan_id] = {"session_id": session_id, "aoi_id": deps.aoi_id, "aoi": session["aoi"],
                          "plan": output, "status": None, "progress": None, "result": None,
                          "error": None, "explanation": None}
        return {"session_id": session_id, "type": "plan", "plan_id": plan_id,
                "plan": output.model_dump(mode="json")}
    return {"session_id": session_id, "type": "question", **output.model_dump()}


def _run_plan(plan_id: str) -> None:
    """Background job: run every index of an approved plan and record the outcome."""
    entry = PLANS[plan_id]
    try:
        plan: AnalysisPlan = entry["plan"]
        total = len(plan.indices)
        results, errors = {}, {}
        for i, index in enumerate(plan.indices):
            entry["progress"] = {"done": i, "total": total, "current": index}
            result = run_fixed_pipeline(
                entry["aoi_id"], index, plan.start_date.isoformat(), plan.end_date.isoformat(),
                max_cloud=plan.max_cloud, cloud_mask=plan.cloud_mask,
                image_date=plan.image_date.isoformat() if plan.image_date else None,
            )
            error = _first_error(result)
            if error:
                errors[index] = error
            else:
                results[index] = result
        entry["progress"] = {"done": total, "total": total, "current": None}

        if results:
            entry["result"] = _feature(entry["aoi"], {
                "session_id": entry["session_id"], "plan_id": plan_id,
                "plan": plan.model_dump(mode="json"), "results": results, "errors": errors,
            })
            entry["status"] = "done"          # set LAST, after the result is ready
        else:
            entry["error"] = errors
            entry["status"] = "failed"
    except Exception as e:                    # never leave a job stuck on "running"
        logger.exception("Plan %s crashed", plan_id)
        entry["error"] = {"service": f"Unexpected error: {type(e).__name__}"}
        entry["status"] = "failed"


def _status_body(plan_id: str, entry: dict) -> dict:
    """What approve and GET /result return: the status, plus progress, result or error."""
    body = {"plan_id": plan_id, "session_id": entry["session_id"], "status": entry["status"]}
    if entry["status"] == "running":
        body["progress"] = entry["progress"]
    elif entry["status"] == "done":
        body["result"] = entry["result"]
    elif entry["status"] == "failed":
        body["error"] = entry["error"]
    return body


@app.post("/plans/{plan_id}/approve", status_code=202)
def approve_plan(plan_id: str):
    """Start the approved plan in the background and answer at once."""
    entry = PLANS.get(plan_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown plan_id (expired or the service "
                            "restarted). Ask the agent for a new plan.")
    with LOCK:
        if entry["status"] is None:                       # first approve: start the job
            indices = entry["plan"].indices
            entry["progress"] = {"done": 0, "total": len(indices), "current": indices[0]}
            entry["status"] = "running"
            EXECUTOR.submit(_run_plan, plan_id)
    return _status_body(plan_id, entry)                   # later approves: just the status


@app.get("/plans/{plan_id}/result")
def get_result(plan_id: str):
    """Poll this every 2-3 s: running (with progress) -> done (with result) or failed (with error)."""
    entry = PLANS.get(plan_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown plan_id (expired or the service "
                            "restarted). Ask the agent for a new plan.")
    if entry["status"] is None:
        raise HTTPException(status_code=409, detail="Approve the plan before asking for its result.")
    return _status_body(plan_id, entry)


@app.get("/plans/{plan_id}/explanation")
def get_explanation(plan_id: str):
    """Plain-language explanation of each index of a finished plan. Computed once, then reused."""
    entry = PLANS.get(plan_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown plan_id (expired or the service "
                            "restarted). Ask the agent for a new plan.")
    if entry["status"] != "done":
        raise HTTPException(status_code=409, detail="The analysis must be finished before "
                            "it can be explained.")

    if entry["explanation"] is None:
        plan_json = entry["plan"].model_dump(mode="json")
        results = entry["result"]["properties"]["results"]
        entry["explanation"] = {index: explain_results(index, steps, plan_json)
                                for index, steps in results.items()}
    return {"plan_id": plan_id, "session_id": entry["session_id"],
            "explanations": entry["explanation"]}


@app.get("/plans/{plan_id}/download/{index}", status_code=307,
           responses={307: {"description": "Redirect to a fresh GeoTIFF download link (header: location)"}})
def download_geotiff(plan_id: str, index: str):
    """GeoTIFF of one index of a finished plan. Redirects to a fresh Earth Engine link."""
    entry = PLANS.get(plan_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown plan_id (expired or the service "
                            "restarted). Ask the agent for a new plan.")
    if entry["status"] != "done":
        raise HTTPException(status_code=409, detail="The analysis must be finished before downloading.")

    index = index.upper()
    results = entry["result"]["properties"]["results"]
    if index not in results:
        raise HTTPException(status_code=404, detail=f"This plan has no successful result for {index}.")

    deps = SESSIONS[entry["session_id"]]["deps"]
    ctx, aoi_id, plan = deps.analysis, entry["aoi_id"], entry["plan"]   # the plan's own area
    day = results[index]["select_image"]["date"]          # exactly the image the user saw

    if aoi_id not in ctx.aois:
        tools.describe_aoi(ctx, aoi_id)
    image = tools.select_image(ctx, aoi_id, date=day)
    if "error" in image:
        raise HTTPException(status_code=422, detail=image["error"])
    computed = tools.compute_index(ctx, image["image_ref"], aoi_id, index, plan.cloud_mask)
    if "error" in computed:
        raise HTTPException(status_code=422, detail=computed["error"])

    region = ctx.aois[aoi_id]
    image = ctx.results[computed["result_id"]]["image"].toFloat()   # 4 bytes per pixel instead of 8
    box_m2 = region.bounds(1).area(1).getInfo()                      # the file covers the rectangle around the area
    scale = next((s for s in DOWNLOAD_SCALES_M
                  if box_m2 / s ** 2 * 4 <= MAX_DOWNLOAD_BYTES * 0.75), None)
    if scale is None:
        raise HTTPException(status_code=422, detail="The area is too large for a direct download, "
                            f"even at {DOWNLOAD_SCALES_M[-1]} m.")

    try:
        url = image.getDownloadURL({
            "name": f"{index}_{day}_{scale}m",
            "region": region,
            "scale": scale,
            "crs": "EPSG:4326",
            "format": "GEO_TIFF",
        })
    except ee.EEException as e:
        raise HTTPException(status_code=422, detail=f"GeoTIFF could not be created: {e}")
    return RedirectResponse(url, status_code=307)