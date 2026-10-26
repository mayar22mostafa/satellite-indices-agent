"""HTTP API of the AI service. The Node.js backend calls these endpoints."""

import json
import uuid
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from pydantic_ai.exceptions import AgentRunError

from ..agent.planner import PlannerDeps, plan_turn
from ..agent.schemas import AnalysisPlan
from ..analysis.pipeline import run_fixed_pipeline
from ..analysis.tools import AOI_DIR, init_earth_engine
from ..registry.aoi import AOIError, aoi_from_geojson_bytes


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_earth_engine()          # connect to Earth Engine once, when the server starts
    yield


app = FastAPI(title="Satellite Indices AI Service", version="0.2.0", lifespan=lifespan)

# In-memory stores (MVP): everything is lost when the service restarts.
SESSIONS: dict[str, dict] = {}   # session_id -> {"aoi": GeoJSON, "deps": PlannerDeps, "history": list}
PLANS: dict[str, dict] = {}      # plan_id -> {"session_id": str, "plan": AnalysisPlan, "result": dict | None}


# ---------------- request bodies ----------------


class PlanRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The engineer's chat message")
    session_id: str | None = Field(None, description="Omit on the first message of a chat")
    aoi: dict | None = Field(None, description="GeoJSON area; required on the first message")


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
    if req.session_id is None:                                  # first message: new chat
        if req.aoi is None:
            raise HTTPException(status_code=400,
                                detail="The first message of a chat must include 'aoi'.")
        aoi_id = _save_aoi(_check_aoi(req.aoi))
        session_id = f"s_{uuid.uuid4().hex[:8]}"
        SESSIONS[session_id] = {"aoi": req.aoi, "deps": PlannerDeps(aoi_id=aoi_id), "history": None}
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
        PLANS[plan_id] = {"session_id": session_id, "plan": output, "result": None}
        return {"session_id": session_id, "type": "plan", "plan_id": plan_id,
                "plan": output.model_dump(mode="json")}
    return {"session_id": session_id, "type": "question", **output.model_dump()}


@app.post("/plans/{plan_id}/approve")
def approve_plan(plan_id: str):
    """The engineer approved: run exactly the saved plan, one pipeline run per index."""
    entry = PLANS.get(plan_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown plan_id (expired or the service "
                            "restarted). Ask the agent for a new plan.")
    if entry["result"] is not None:
        return entry["result"]                     # approved before: same answer, no recompute

    session = SESSIONS[entry["session_id"]]
    plan: AnalysisPlan = entry["plan"]
    results, errors = {}, {}
    for index in plan.indices:
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

    if not results:
        raise HTTPException(status_code=422, detail=errors)

    response = _feature(session["aoi"], {
        "session_id": entry["session_id"], "plan_id": plan_id,
        "plan": plan.model_dump(mode="json"), "results": results, "errors": errors,
    })
    entry["result"] = response
    return response