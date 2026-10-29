"""Analysis tools: deterministic functions that run on Google Earth Engine.

Each tool takes the shared RunContext plus small, simple inputs (IDs, dates, names)
and returns a small dict that can be turned into JSON. On a problem, a tool returns
{"error": "..."} instead of crashing, so a caller (later: the agent) can read it and react.

Scientific settings (collection, bands, scale/offset, cloud classes, area limit) come
from Somaya's registry. Area files are read and checked by Somaya's aoi.py.
"""

import functools
import json
import os
import re
from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path

import ee
from dotenv import load_dotenv

from ..registry import registry as reg
from ..registry.aoi import AOIError, read_aoi
from .context import RunContext

ROOT = Path(__file__).resolve().parents[3]   # project root (where .env and data/ live)
AOI_DIR = ROOT / "data" / "aoi"
AOI_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")   # letters, numbers, _ and - only
SAT = reg.SENTINEL2                          # the only satellite in the MVP
MIN_CLEAR_PCT = 20.0     # a day is usable only if at least this % of the area is clear
MAX_DAYS_CHECKED = 5     # in a date range: how many of the newest days to try

# Display only (colours on the map). Not science, so it lives here, not in the registry.
VIS = {
    "NDVI": {"min": -0.2, "max": 0.8,
             "palette": ["a50026", "f46d43", "fee08b", "d9ef8b", "66bd63", "006837"]},
    "NDWI": {"min": -0.5, "max": 0.5,
             "palette": ["8c510a", "f6e8c3", "c7eae5", "01665e", "08306b"]},
    "NDBI": {"min": -0.5, "max": 0.5,
             "palette": ["1a9850", "ffffbf", "d73027"]},
    "MNDWI": {"min": -0.5, "max": 0.5,
              "palette": ["8c510a", "f6e8c3", "c7eae5", "01665e", "08306b"]},
    "NDMI": {"min": -0.5, "max": 0.5,
             "palette": ["8c510a", "d8b365", "f6e8c3", "c7eae5", "5ab4ac", "01665e"]},
}


def init_earth_engine() -> None:
    """Connect to Earth Engine using the project ID from .env."""
    load_dotenv(ROOT / ".env")
    project = os.getenv("EE_PROJECT")
    if not project:
        raise RuntimeError("EE_PROJECT is missing in .env")
    ee.Initialize(project=project)


# ---------------- helpers (not tools) ----------------

def safe_tool(fn):
    """Turn Earth Engine failures into {"error": ...} instead of crashing."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ee.EEException as e:
            return {"error": f"Earth Engine error in {fn.__name__}: {e}"}
    return wrapper


def _check_dates(*days):
    """Return an error message if the dates are invalid, otherwise None."""
    try:
        parsed = [Date.fromisoformat(d) for d in days if d is not None]
    except (TypeError, ValueError):
        return f"Dates must be YYYY-MM-DD, got {days}."
    if len(parsed) == 2 and parsed[0] > parsed[1]:
        return "start_date must be on or before end_date."
    if any(d > Date.today() for d in parsed):
        return "Dates cannot be in the future."
    return None


def _to_date(millis: int) -> str:
    """Earth Engine stores time as milliseconds since 1970 -> 'YYYY-MM-DD'."""
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).date().isoformat()


def _collection(geom: ee.Geometry, start_date: str, end_date: str) -> ee.ImageCollection:
    """Images of the registry's collection touching the area (end date included)."""
    return (ee.ImageCollection(SAT.ee_collection)
            .filterBounds(geom)
            .filterDate(start_date, ee.Date(end_date).advance(1, "day")))


def _nearest_dates(geom: ee.Geometry, date: str, window_days: int = 15, n: int = 3) -> list:
    """The n available image days closest to `date` (within +/- window_days)."""
    d = ee.Date(date)
    times = (ee.ImageCollection(SAT.ee_collection).filterBounds(geom)
             .filterDate(d.advance(-window_days, "day"), d.advance(window_days + 1, "day"))
             .aggregate_array("system:time_start").getInfo())
    wanted = datetime.fromisoformat(date)
    days = sorted({_to_date(t) for t in times},
                  key=lambda x: abs((datetime.fromisoformat(x) - wanted).days))
    return days[:n]


def _clear_pct(geom: ee.Geometry, date: str) -> float:
    """% of the area that is usable on that day: not cloud, shadow or snow, and inside the image."""
    scl = _collection(geom, date, date).mosaic().select(SAT.cloud_mask_band)
    clear = ee.Image(1)
    for value in SAT.cloud_mask_classes:
        clear = clear.And(scl.neq(value))          # masked where the image has no data
    mean = (clear.unmask(0).rename("clear")        # no data -> 0 (not usable)
            .reduceRegion(ee.Reducer.mean(), geom, scale=100, maxPixels=1e9, tileScale=4)
            .get("clear").getInfo())
    return round(100 * (mean or 0), 1)


def _aoi_file(aoi_id: str) -> Path | None:
    """data/aoi/<aoi_id>.geojson, .json or .zip (zipped shapefile), if it exists."""
    for suffix in (".geojson", ".json", ".zip"):
        path = AOI_DIR / f"{aoi_id}{suffix}"
        if path.exists():
            return path
    return None


# ---------------- lookup tools ----------------

@safe_tool
def describe_aoi(ctx: RunContext, aoi_id: str) -> dict:
    """Read and check the area with Somaya's read_aoi, then prepare it for Earth Engine."""
    if not AOI_ID_PATTERN.match(aoi_id):
        return {"error": "aoi_id may contain only letters, numbers, '_' and '-'."}
    path = _aoi_file(aoi_id)
    if path is None:
        known = sorted({p.stem for p in AOI_DIR.glob("*") if p.suffix in (".geojson", ".json", ".zip")})
        return {"error": f"Unknown aoi_id '{aoi_id}'. Known: {known}"}

    try:
        aoi = read_aoi(path)              # polygons only, repaired, WGS84, size-checked
    except AOIError as e:
        return {"error": str(e)}

    geojson = json.loads(json.dumps(aoi.to_geojson()))   # plain lists, as Earth Engine expects
    ctx.aois[aoi_id] = ee.Geometry(geojson)
    return {"aoi_id": aoi_id, **aoi.describe()}


@safe_tool
def find_images(ctx: RunContext, aoi_id: str, start_date: str, end_date: str,
                max_cloud: float = 20) -> dict:
    """List images over the area, newest first, under the cloud limit."""
    if aoi_id not in ctx.aois:
        return {"error": f"Unknown area '{aoi_id}'. Call describe_aoi first."}
    if (problem := _check_dates(start_date, end_date)):
        return {"error": problem}

    col = (_collection(ctx.aois[aoi_id], start_date, end_date)
           .filter(ee.Filter.lte(SAT.cloud_property, max_cloud))
           .sort("system:time_start", False)
           .limit(30))
    info = ee.Dictionary({                       # one trip to the server for all three lists
        "ids": col.aggregate_array("system:index"),
        "times": col.aggregate_array("system:time_start"),
        "clouds": col.aggregate_array(SAT.cloud_property),
    }).getInfo()

    images = [{"image_id": i, "date": _to_date(t), "tile_cloud_pct": round(c, 1)}
              for i, t, c in zip(info["ids"], info["times"], info["clouds"])]
    return {"count": len(images), "images": images}


# ---------------- analysis tools ----------------

@safe_tool
def select_image(ctx: RunContext, aoi_id: str, start_date: str | None = None,
                 end_date: str | None = None, max_cloud: float = 20,
                 date: str | None = None) -> dict:
    """Choose the image day to use and mosaic all its tiles over the area.

    date given        -> use exactly that day (the engineer's choice).
    date not given    -> use the newest day between start_date and end_date under max_cloud.
    """
    if aoi_id not in ctx.aois:
        return {"error": f"Unknown area '{aoi_id}'. Call describe_aoi first."}
    geom = ctx.aois[aoi_id]
    if (problem := _check_dates(date) if date else _check_dates(start_date, end_date)):
        return {"error": problem}

    if date is None:
        if not (start_date and end_date):
            return {"error": "Give either a date, or both start_date and end_date."}
        good = (_collection(geom, start_date, end_date)
                .filter(ee.Filter.lte(SAT.cloud_property, max_cloud))
                .sort("system:time_start", False))
        if good.size().getInfo() == 0:
            return {"error": f"No images between {start_date} and {end_date} with cloud <= {max_cloud}%. "
                             "Try a wider date range or a higher cloud limit."}
        date = _to_date(good.first().get("system:time_start").getInfo())

    day = _collection(geom, date, date)                 # all tiles over the area on that day
    info = ee.Dictionary({"tiles": day.size(),
                          "cloud": day.aggregate_mean(SAT.cloud_property)}).getInfo()
    if info["tiles"] == 0:
        return {"error": f"No Sentinel-2 image over '{aoi_id}' on {date}.",
                "nearest_dates": _nearest_dates(geom, date)}
    if start_date is None or end_date is None:          # exact day: not checked yet
        clear = _clear_pct(geom, date)
        if clear < MIN_CLEAR_PCT:
            return {"error": f"The image of {date} is not usable over '{aoi_id}': only {clear}% of the "
                             "area is clear (the rest is cloud, shadow or outside the image).",
                    "nearest_dates": _nearest_dates(geom, date)}

    image_ref = f"s2_{date}"
    ctx.images[image_ref] = {"image": day.mosaic(), "date": date}
    return {"image_ref": image_ref, "date": date, "tiles": info["tiles"],
            "tile_cloud_pct": round(info["cloud"], 1), "area_clear_pct": clear}


@safe_tool
def compute_index(ctx: RunContext, image_ref: str, aoi_id: str, index_name: str,
                  cloud_mask: bool = True) -> dict:
    """Apply the registry's rules on Earth Engine, the same rules as Somaya's indices.py:

    1. scale + offset (stored value -> reflectance)
    2. cloud/shadow mask from the registry's SCL classes
    3. normalized difference, masked where the denominator is 0
    """
    try:
        index = reg.get_index(index_name)
    except ValueError as e:
        return {"error": str(e)}
    if image_ref not in ctx.images:
        return {"error": f"Unknown image '{image_ref}'. Call select_image first."}
    if aoi_id not in ctx.aois:
        return {"error": f"Unknown area '{aoi_id}'. Call describe_aoi first."}

    sat = reg.get_satellite(index.satellite)
    image = ctx.images[image_ref]["image"]

    if cloud_mask:
        if sat.cloud_mask_method != "scl":
            return {"error": f"Cloud mask method '{sat.cloud_mask_method}' is not implemented yet."}
        scl = image.select("SCL")
        clear = ee.Image(1)
        for value in reg.SCL_MASKED_CLASSES:
            clear = clear.And(scl.neq(value))       # 1 = keep pixel, 0 = remove
        image = image.updateMask(clear)

    a = image.select(index.a).multiply(sat.scale_factor).add(sat.offset)
    b = image.select(index.b).multiply(sat.scale_factor).add(sat.offset)
    denominator = a.add(b)
    index_image = (a.subtract(b).divide(denominator)
                   .updateMask(denominator.neq(0))  # a + b = 0 -> masked, never a broken value
                   .rename(index.key)
                   .clip(ctx.aois[aoi_id]))

    scale_m = reg.coarsest_resolution_m(index)
    suffix = "" if cloud_mask else "_nomask"
    result_id = f"{index.key}_{image_ref}_{aoi_id}{suffix}"
    ctx.results[result_id] = {"image": index_image, "aoi_id": aoi_id,
                              "index": index.key, "scale_m": scale_m}
    return {"result_id": result_id, "index": index.key,
            "resolution_m": scale_m, "cloud_mask": cloud_mask}


@safe_tool
def compute_statistics(ctx: RunContext, result_id: str) -> dict:
    """Mean, min, max, std and the % of the area with valid (clear) pixels."""
    if result_id not in ctx.results:
        return {"error": f"Unknown result '{result_id}'. Call compute_index first."}

    r = ctx.results[result_id]
    geom, scale, band = ctx.aois[r["aoi_id"]], r["scale_m"], r["index"]

    reducer = (ee.Reducer.mean()
               .combine(ee.Reducer.minMax(), sharedInputs=True)
               .combine(ee.Reducer.stdDev(), sharedInputs=True)
               .combine(ee.Reducer.count(), sharedInputs=True))
    stats = r["image"].reduceRegion(reducer=reducer, geometry=geom, scale=scale,
                                    maxPixels=1e10, tileScale=4)
    total = ee.Image(1).reduceRegion(reducer=ee.Reducer.count(), geometry=geom, scale=scale,
                                     maxPixels=1e10, tileScale=4)
    info = ee.Dictionary({"stats": stats, "total": total}).getInfo()

    s = info["stats"]
    # Earth Engine names outputs "<band>_<statistic>", e.g. "NDVI_mean"
    valid = s.get(f"{band}_count") or 0
    all_pixels = list(info["total"].values())[0] or 0
    if valid == 0:
        return {"error": "No clear pixels over the area (all masked as cloud/no data)."}

    def get(name):
        value = s.get(f"{band}_{name}")
        return None if value is None else round(value, 4)

    return {"result_id": result_id, "index": band,
            "mean": get("mean"), "min": get("min"), "max": get("max"), "std": get("stdDev"),
            "valid_pixel_pct": round(min(100.0, 100 * valid / all_pixels), 1),}


@safe_tool
def create_map_layer(ctx: RunContext, result_id: str) -> dict:
    """Display only: a map-tile URL and a PNG preview URL. Never used for numbers."""
    if result_id not in ctx.results:
        return {"error": f"Unknown result '{result_id}'. Call compute_index first."}

    r = ctx.results[result_id]
    vis = VIS[r["index"]]
    tiles = r["image"].getMapId(vis)
    preview = r["image"].getThumbURL({**vis, "region": ctx.aois[r["aoi_id"]],
                                      "dimensions": 1024, "format": "png"})
    return {"result_id": result_id, "tile_url": tiles["tile_fetcher"].url_format,
            "preview_url": preview}