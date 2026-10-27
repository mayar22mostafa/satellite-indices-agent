"""HTTP API of the AI service. The Node.js backend calls these endpoints."""

import json
import uuid
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

# ---------------- request bodies ----------------


class PlanRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The engineer's chat message")
    session_id: str | None = Field(None, description="Omit on the first message of a chat")
    aoi: dict | None = Field(None, description="GeoJSON area; required on the first message")
    start_date: date | None = Field(None, description="First day of the range (YYYY-MM-DD). Use with end_date.")
    end_date: date | None = Field(None, description="Last day of the range (YYYY-MM-DD). Use with start_date.")
    image_date: date | None = Field(None, description="One exact day (YYYY-MM-DD), instead of a range.")


# ---------------- helpers ----------------

def _check_aoi(aoi: dict) -> bytes:
    """Validate the area (Somaya's reader). Bad area -> 400."""
    raw = json.dumps(aoi).encode()
    try:
        aoi_from_geojson_bytes(raw)
    except AOIError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return raw


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
    """One chat message -> a plan to approve, or a clarifying question."""
    dates = _read_dates(req)                                    # checked before anything is created
    if req.session_id is None:                                  # first message: new chat
        if req.aoi is None:
            raise HTTPException(status_code=400,
                                detail="The first message of a chat must include 'aoi'.")
        if dates is None:
            raise HTTPException(status_code=400, detail="The first message of a chat must include "
                                "dates: start_date and end_date, or image_date.")
        aoi_id = _save_aoi(_check_aoi(req.aoi))
        session_id = f"s_{uuid.uuid4().hex[:8]}"
        SESSIONS[session_id] = {"aoi": req.aoi, "deps": PlannerDeps(aoi_id=aoi_id), "history": None}
    else:
        session_id = req.session_id
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Unknown session_id (the chat expired "
                                "or the service restarted). Start a new chat.")
    session = SESSIONS[session_id]
    if dates is not None:                                       # new dates replace the old ones
        deps = session["deps"]
        deps.start_date, deps.end_date, deps.image_date = dates
    else:
        session_id = req.session_id
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Unknown session_id (the chat expired "
                                "or the service restarted). Start a new chat.")
    session = SESSIONS[session_id]

    try:
        output, session["history"] = plan_turn(req.message, session["deps"], session["history"])
    except AgentRunError as e:
        raise HTTPException(status_code=502, detail="The AI model could not answer. "
                            f"Please try again. ({type(e).__name__})")

    if isinstance(output, AnalysisPlan):
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        PLANS[plan_id] = {"session_id": session_id, "plan": output, "status": None,
                          "progress": None, "result": None, "error": None, "explanation": None}
        return {"session_id": session_id, "type": "plan", "plan_id": plan_id,
                "plan": output.model_dump(mode="json")}
    return {"session_id": session_id, "type": "question", **output.model_dump()}


def _run_plan(plan_id: str) -> None:
    """Background job: run every index of an approved plan and record the outcome."""
    entry = PLANS[plan_id]
    try:
        session = SESSIONS[entry["session_id"]]
        plan: AnalysisPlan = entry["plan"]
        total = len(plan.indices)
        results, errors = {}, {}
        for i, index in enumerate(plan.indices):
            entry["progress"] = {"done": i, "total": total, "current": index}
            result = run_fixed_pipeline(
                session["deps"].aoi_id, index, plan.start_date.isoformat(), plan.end_date.isoformat(),
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
            entry["result"] = _feature(session["aoi"], {
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