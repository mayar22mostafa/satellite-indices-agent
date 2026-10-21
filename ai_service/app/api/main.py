"""HTTP API of the AI service. The Node.js backend calls these endpoints."""

import json
import uuid
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ..analysis.pipeline import run_fixed_pipeline
from ..analysis.tools import AOI_DIR, init_earth_engine
from ..registry.aoi import AOIError, aoi_from_geojson_bytes
from ..registry import registry as reg


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_earth_engine()          # connect to Earth Engine once, when the server starts
    yield


app = FastAPI(title="Satellite Indices AI Service", version="0.1.0", lifespan=lifespan)


class AnalyzeRequest(BaseModel):
    aoi: dict = Field(..., description="GeoJSON: FeatureCollection, Feature, or Polygon/MultiPolygon")
    index: str = Field(..., description="NDVI, NDWI or NDBI")
    start_date: date | None = Field(None, description="Default: 60 days before end_date")
    end_date: date | None = Field(None, description="Default: today")
    image_date: date | None = Field(None, description="Exact image day (skips the cloud filter)")
    max_cloud: float = Field(20, ge=0, le=100)
    cloud_mask: bool = True


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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    # 0. Check the index first: no Earth Engine work for an index we don't support
    index = req.index.upper()
    supported = sorted(reg.INDICES)
    if index not in supported:
        raise HTTPException(status_code=422,
                            detail=f"Unknown index '{req.index}'. Supported: {supported}")
    
    # 1. Check the area before touching Earth Engine -> a clear 400 error for bad input
    raw = json.dumps(req.aoi).encode()
    try:
        aoi_from_geojson_bytes(raw)
    except AOIError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Dates
    end = req.end_date or date.today()
    start = req.start_date or end - timedelta(days=60)

    # 3. Save the area under a temporary id, run the pipeline, then delete the file
    aoi_id = f"upload_{uuid.uuid4().hex[:8]}"
    AOI_DIR.mkdir(parents=True, exist_ok=True)
    path = AOI_DIR / f"{aoi_id}.geojson"
    path.write_bytes(raw)
    try:
        result = run_fixed_pipeline(
            aoi_id, index, start.isoformat(), end.isoformat(),
            max_cloud=req.max_cloud, cloud_mask=req.cloud_mask,
            image_date=req.image_date.isoformat() if req.image_date else None,
        )
    finally:
        path.unlink(missing_ok=True)

    error = result.get("error") or next(
        (step["error"] for step in result.values() if isinstance(step, dict) and "error" in step),
        None,
    )
    if error:
        raise HTTPException(status_code=422, detail=error)
    
    return {"type": "Feature", "geometry": _geometry(req.aoi),
            "properties": {"index": index, **result}}