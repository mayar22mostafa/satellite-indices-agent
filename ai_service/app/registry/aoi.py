"""Area-of-interest (AOI) reading and checks.

Pipeline (step 1 of the preprocessing in the proposal):
  read file -> keep polygons -> repair geometry -> convert to WGS84 -> size check

Supported inputs: GeoJSON (.geojson/.json) and zipped shapefile (.zip).
Every failure raises AOIError with a message a field engineer can act on.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import shapefile  # pyshp
import shapely
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator
from pyproj import CRS, Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.validation import explain_validity, make_valid

#from .settings import get_settings

WGS84 = CRS.from_epsg(4326)
EQUAL_AREA = CRS.from_epsg(6933)  # World Cylindrical Equal Area, metres
MAX_AOI_AREA_KM2 = 100_000

class AOIError(ValueError):
    """Raised when an area file cannot be used. The message explains why."""


class AOISummary(BaseModel):
    """What the agent's describe_aoi tool returns: size and location, nothing else."""

    model_config = ConfigDict(frozen=True)

    area_km2: float = Field(gt=0)
    centroid_lon_lat: tuple[float, float]
    bounds: tuple[float, float, float, float]
    repaired: bool
    warnings: list[str]


class AOI(BaseModel):
    """A validated area of interest. Always WGS84 (lon, lat), always a valid polygon."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    geometry: Polygon | MultiPolygon
    area_km2: float = Field(gt=0)
    centroid: tuple[float, float]  # (lon, lat)
    bounds: tuple[float, float, float, float]  # minx, miny, maxx, maxy
    source_crs: str
    was_repaired: bool = False
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _is_a_real_wgs84_polygon(self) -> AOI:
        if self.geometry.is_empty or not self.geometry.is_valid:
            raise ValueError("geometry must be a valid, non-empty polygon")
        minx, miny, maxx, maxy = self.bounds
        if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
            raise ValueError("bounds must be valid WGS84 longitude/latitude, ordered min to max")
        lon, lat = self.centroid
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("centroid must be valid WGS84 longitude/latitude")
        return self

    @field_serializer("geometry")
    def _geometry_as_geojson(self, geometry: Polygon | MultiPolygon) -> dict[str, Any]:
        return mapping(geometry)

    def to_geojson(self) -> dict[str, Any]:
        return mapping(self.geometry)

    def summary(self) -> AOISummary:
        return AOISummary(
            area_km2=round(self.area_km2, 3),
            centroid_lon_lat=(round(self.centroid[0], 5), round(self.centroid[1], 5)),
            bounds=tuple(round(b, 5) for b in self.bounds),  # type: ignore[arg-type]
            repaired=self.was_repaired,
            warnings=list(self.warnings),
        )

    def describe(self) -> dict[str, Any]:
        """Plain-dict form of ``summary()`` for tools and prompts."""
        return self.summary().model_dump()


# ----------------------------------------------------------------- public API
def read_aoi(path: str | Path, max_area_km2: float | None = None) -> AOI:
    """Read a GeoJSON or zipped shapefile and return a validated AOI."""
    path = Path(path)
    if not path.exists():
        raise AOIError(f"File not found: {path.name}")
    suffix = path.suffix.lower()
    data = path.read_bytes()
    if suffix in (".geojson", ".json"):
        return aoi_from_geojson_bytes(data, max_area_km2)
    if suffix == ".zip":
        return aoi_from_zipped_shapefile(data, max_area_km2)
    raise AOIError(
        f"Unsupported file type {suffix!r}. Upload a .geojson file or a "
        "zipped shapefile (.zip containing .shp, .shx, .dbf, .prj)."
    )


def aoi_from_geojson_bytes(data: bytes, max_area_km2: float | None = None) -> AOI:
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise AOIError(f"The file is not valid GeoJSON ({e}).") from e
    geoms = _geometries_from_geojson(obj)
    # GeoJSON (RFC 7946) is WGS84. Honour a legacy "crs" member if present.
    src = _legacy_geojson_crs(obj) or WGS84
    return _build_aoi(geoms, src, max_area_km2)


def aoi_from_zipped_shapefile(data: bytes, max_area_km2: float | None = None) -> AOI:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise AOIError("The file is not a valid .zip archive.") from e
    names = {n.lower(): n for n in zf.namelist() if not n.endswith("/")}
    shp = [n for n in names if n.endswith(".shp")]
    if not shp:
        raise AOIError("The zip has no .shp file.")
    if len(shp) > 1:
        raise AOIError("The zip has more than one shapefile; upload one layer only.")
    stem = shp[0][:-4]
    missing = [ext for ext in (".shx", ".dbf") if stem + ext not in names]
    if missing:
        raise AOIError(f"The shapefile is missing required parts: {', '.join(missing)}.")
    try:
        reader = shapefile.Reader(
            shp=io.BytesIO(zf.read(names[stem + ".shp"])),
            shx=io.BytesIO(zf.read(names[stem + ".shx"])),
            dbf=io.BytesIO(zf.read(names[stem + ".dbf"])),
        )
        geoms = [shape(s.__geo_interface__) for s in reader.shapes() if s.shapeType != 0]
    except Exception as e:  # pyshp raises several unrelated types
        raise AOIError(f"The shapefile could not be read ({e}).") from e

    src: CRS | None = None
    if stem + ".prj" in names:
        try:
            src = CRS.from_wkt(zf.read(names[stem + ".prj"]).decode("utf-8", "ignore"))
        except Exception as e:
            raise AOIError(f"The .prj file is not a valid projection ({e}).") from e
    warnings: list[str] = []
    if src is None:
        if _looks_like_degrees(geoms):
            src = WGS84
            warnings.append("No .prj file: coordinates look like degrees, assumed WGS84.")
        else:
            raise AOIError(
                "The shapefile has no .prj file and its coordinates are not "
                "in degrees, so the coordinate system is unknown."
            )
    return _build_aoi(geoms, src, max_area_km2, warnings)


# ------------------------------------------------------------------ internals
def _geometries_from_geojson(obj: Any) -> list:
    if not isinstance(obj, dict) or "type" not in obj:
        raise AOIError("The file is not valid GeoJSON (no 'type').")
    t = obj["type"]
    try:
        if t == "FeatureCollection":
            feats = [f.get("geometry") for f in obj.get("features", [])]
        elif t == "Feature":
            feats = [obj.get("geometry")]
        else:
            feats = [obj]
        geoms = [shape(g) for g in feats if g]
    except Exception as e:
        raise AOIError(f"The GeoJSON geometry is malformed ({e}).") from e
    if not geoms:
        raise AOIError("The GeoJSON contains no geometry.")
    return geoms


def _legacy_geojson_crs(obj: Any) -> CRS | None:
    crs = obj.get("crs") if isinstance(obj, dict) else None
    name = (crs or {}).get("properties", {}).get("name") if isinstance(crs, dict) else None
    if not name:
        return None
    try:
        return CRS.from_user_input(name)
    except Exception as e:
        raise AOIError(f"Unrecognised CRS in GeoJSON: {name!r}.") from e


def _looks_like_degrees(geoms: list) -> bool:
    return all(
        -180 <= g.bounds[0] <= 180
        and -180 <= g.bounds[2] <= 180
        and -90 <= g.bounds[1] <= 90
        and -90 <= g.bounds[3] <= 90
        for g in geoms
        if not g.is_empty
    )


def _polygons_only(geom) -> list[Polygon]:
    """Extract polygons from any geometry (repair can yield collections)."""
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if hasattr(geom, "geoms"):
        out: list[Polygon] = []
        for g in geom.geoms:
            out.extend(_polygons_only(g))
        return out
    return []  # points and lines are ignored


def _build_aoi(
    geoms: list, src_crs: CRS, max_area_km2: float | None, warnings: list[str] | None = None
) -> AOI:
    warnings = list(warnings or [])
    polys: list[Polygon] = []
    for g in geoms:
        polys.extend(_polygons_only(g))
    if not polys:
        raise AOIError("The file has no polygons. The area must be a polygon, not points or lines.")
    if len(polys) < len(geoms):
        warnings.append("Non-polygon features were ignored.")

    # Reproject to WGS84 first, then repair (repair in lon/lat is what EE receives).
    if src_crs != WGS84:
        polys = [_reproject(p, src_crs, WGS84) for p in polys]
    for p in polys:
        minx, miny, maxx, maxy = p.bounds
        if not (
            -180 <= minx <= 180 and -180 <= maxx <= 180 and -90 <= miny <= 90 and -90 <= maxy <= 90
        ):
            raise AOIError(
                "Coordinates are outside valid longitude/latitude ranges. "
                "Check the file's coordinate system, or that x/y are not swapped."
            )

    repaired = False
    fixed: list[Polygon] = []
    for p in polys:
        if not p.is_valid:
            repaired = True
            warnings.append(f"Invalid geometry repaired ({explain_validity(p)}).")
            p = make_valid(p)
        fixed.extend(_polygons_only(p))
    union = unary_union(fixed)
    parts = _polygons_only(union)
    if not parts:
        raise AOIError("The geometry is empty after repair (zero-area polygon).")
    geometry: Polygon | MultiPolygon = parts[0] if len(parts) == 1 else MultiPolygon(parts)

    area_km2 = _area_km2(geometry)
    if area_km2 <= 0:
        raise AOIError("The area is zero.")
    limit = (
        max_area_km2
       if max_area_km2 is not None
       else MAX_AOI_AREA_KM2
         )
  
    if area_km2 > limit:
        raise AOIError(
            f"The area is {area_km2:,.0f} km2, above the limit of "
            f"{limit:,.0f} km2. Draw a smaller area."
        )
    c = geometry.centroid
    return AOI(
        geometry=geometry,
        area_km2=area_km2,
        centroid=(c.x, c.y),
        bounds=geometry.bounds,
        source_crs=src_crs.to_string(),
        was_repaired=repaired,
        warnings=warnings,
    )


def _reproject(geometry, src: CRS, dst: CRS):
    """Reproject any shapely geometry between two CRSs (x/y = lon/lat order)."""
    tr = Transformer.from_crs(src, dst, always_xy=True)

    def convert(coords: np.ndarray) -> np.ndarray:
        x, y = tr.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    return shapely.transform(geometry, convert)


def _area_km2(geometry) -> float:
    return _reproject(geometry, WGS84, EQUAL_AREA).area / 1e6
