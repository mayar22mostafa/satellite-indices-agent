"""Area-of-interest (AOI) reading and checks.

Reads a GeoJSON file or a zipped shapefile, repairs invalid geometry, converts to
WGS84 (EPSG:4326), and enforces a size limit. Every unusable input raises
``AOIError`` with a plain-language message the engineer can act on.

The result is a validated, immutable Pydantic model (``AOI``): if an ``AOI`` object
exists, its geometry is a non-empty, valid polygon inside valid lon/lat ranges.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Annotated

import numpy as np
import pyproj
import shapefile  # pyshp
import shapely
from pydantic import BaseModel, ConfigDict, Field, field_validator
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .registry import DEFAULT_MAX_AREA_KM2

WGS84 = pyproj.CRS.from_epsg(4326)
EQUAL_AREA = pyproj.CRS.from_epsg(6933)  # World Cylindrical Equal Area (metres)

# Safety limit on what we are willing to unzip from an uploaded shapefile.
MAX_UNZIPPED_BYTES = 200 * 1024 * 1024

_POLYGON_TYPES = {shapefile.POLYGON, shapefile.POLYGONZ, shapefile.POLYGONM}
_GEOJSON_GEOMETRY_TYPES = {
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
}


class AOIError(Exception):
    """Raised for every unusable area input. The message says what to fix."""


# ---------------------------------------------------------------------------
# Validated result models
# ---------------------------------------------------------------------------
Longitude = Annotated[float, Field(ge=-180, le=180)]
Latitude = Annotated[float, Field(ge=-90, le=90)]


class AOISummary(BaseModel):
    """Plain summary of an AOI (what the agent's ``describe_aoi`` tool returns)."""

    model_config = ConfigDict(frozen=True)

    area_km2: float
    centroid_lon_lat: tuple[Longitude, Latitude]
    bounds: tuple[Longitude, Latitude, Longitude, Latitude]
    repaired: bool
    warnings: list[str]


class AOI(BaseModel):
    """A validated area of interest, always in WGS84."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    geometry: BaseGeometry  # Polygon or MultiPolygon, WGS84 lon/lat
    area_km2: float = Field(gt=0)
    centroid: tuple[Longitude, Latitude]  # (lon, lat)
    bounds: tuple[Longitude, Latitude, Longitude, Latitude]  # minx, miny, maxx, maxy
    source_crs: str
    was_repaired: bool = False
    warnings: list[str] = Field(default_factory=list)

    @field_validator("geometry")
    @classmethod
    def _geometry_is_valid_polygon(cls, geom: BaseGeometry) -> BaseGeometry:
        if not isinstance(geom, Polygon | MultiPolygon):
            raise ValueError("AOI geometry must be a Polygon or MultiPolygon")
        if geom.is_empty:
            raise ValueError("AOI geometry is empty")
        if not geom.is_valid:
            raise ValueError("AOI geometry is not valid")
        return geom

    def to_geojson(self) -> dict:
        """The geometry as a GeoJSON geometry dictionary."""
        return json.loads(shapely.to_geojson(self.geometry))

    def summary(self) -> AOISummary:
        return AOISummary(
            area_km2=round(self.area_km2, 3),
            centroid_lon_lat=(round(self.centroid[0], 4), round(self.centroid[1], 4)),
            bounds=tuple(round(v, 4) for v in self.bounds),  # type: ignore[arg-type]
            repaired=self.was_repaired,
            warnings=list(self.warnings),
        )

    def describe(self) -> dict:
        return self.summary().model_dump(mode="json")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def read_aoi(path: str | Path, max_area_km2: float = DEFAULT_MAX_AREA_KM2) -> AOI:
    """Read an AOI from a ``.geojson``/``.json`` file or a zipped shapefile (``.zip``)."""
    path = Path(path)
    if not path.is_file():
        raise AOIError(f"File not found: {path}")
    suffix = path.suffix.lower()
    data = path.read_bytes()
    if suffix in {".geojson", ".json"}:
        return aoi_from_geojson_bytes(data, max_area_km2)
    if suffix == ".zip":
        return aoi_from_zipped_shapefile(data, max_area_km2)
    if suffix in {".shp", ".shx", ".dbf", ".prj"}:
        raise AOIError(
            "A shapefile is several files. Zip the .shp, .shx, .dbf (and .prj) "
            "together and upload the .zip."
        )
    raise AOIError(f"Unsupported file type {suffix!r}. Use .geojson, .json or a .zip shapefile.")


def aoi_from_geojson_bytes(data: bytes, max_area_km2: float = DEFAULT_MAX_AREA_KM2) -> AOI:
    """Build an AOI from GeoJSON bytes (Feature, FeatureCollection or bare geometry)."""
    try:
        doc = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise AOIError(f"The file is not valid GeoJSON (could not parse JSON: {err}).") from err
    if not isinstance(doc, dict):
        raise AOIError("The file is not valid GeoJSON (expected a JSON object).")

    warnings: list[str] = []
    source_crs = _geojson_crs(doc, warnings)

    raw_geometries: list[dict] = []
    _collect_geojson_geometries(doc, raw_geometries, warnings)
    if not raw_geometries:
        raise AOIError("The file contains no geometry. Draw or upload at least one polygon.")

    geoms: list[BaseGeometry] = []
    for raw in raw_geometries:
        try:
            geoms.append(shape(raw))
        except Exception as err:  # shapely raises several unrelated types here
            raise AOIError(f"A geometry in the file is malformed ({err}).") from err

    return _finalize(geoms, source_crs, warnings, max_area_km2)


def aoi_from_zipped_shapefile(data: bytes, max_area_km2: float = DEFAULT_MAX_AREA_KM2) -> AOI:
    """Build an AOI from the bytes of a zip holding a shapefile (.shp, .shx, .dbf, .prj)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as err:
        raise AOIError("The file is not a valid .zip archive.") from err

    with archive:
        if sum(i.file_size for i in archive.infolist()) > MAX_UNZIPPED_BYTES:
            raise AOIError("The zip is too large once unpacked. Upload only the area you need.")

        members: dict[str, list[str]] = {}
        for name in archive.namelist():
            base = Path(name).name
            if name.endswith("/") or name.startswith("__MACOSX/") or base.startswith("._"):
                continue
            members.setdefault(Path(name).suffix.lower(), []).append(name)

        shp_names = members.get(".shp", [])
        if not shp_names:
            raise AOIError("The zip contains no .shp file. Zip the whole shapefile together.")
        if len(shp_names) > 1:
            raise AOIError(
                f"The zip contains {len(shp_names)} shapefiles. Upload a zip with only one."
            )
        stem = str(Path(shp_names[0]).with_suffix(""))

        def find(ext: str) -> str | None:
            for name in members.get(ext, []):
                if str(Path(name).with_suffix("")).lower() == stem.lower():
                    return name
            return None

        shx_name, dbf_name, prj_name = find(".shx"), find(".dbf"), find(".prj")
        missing = [e for e, n in ((".shx", shx_name), (".dbf", dbf_name)) if n is None]
        if missing:
            raise AOIError(
                f"The shapefile is incomplete: missing {', '.join(missing)}. "
                "Zip the .shp, .shx and .dbf together."
            )

        shp_bytes = archive.read(shp_names[0])
        shx_bytes = archive.read(shx_name)
        dbf_bytes = archive.read(dbf_name)
        prj_text = archive.read(prj_name).decode("utf-8", "replace") if prj_name else None

    warnings: list[str] = []
    try:
        reader = shapefile.Reader(
            shp=io.BytesIO(shp_bytes), shx=io.BytesIO(shx_bytes), dbf=io.BytesIO(dbf_bytes)
        )
        shapes = reader.shapes()
        reader.close()
    except Exception as err:
        raise AOIError(f"The shapefile could not be read ({err}).") from err

    geoms: list[BaseGeometry] = []
    ignored = 0
    for shp in shapes:
        if shp.shapeType == shapefile.NULL:
            continue
        if shp.shapeType not in _POLYGON_TYPES:
            ignored += 1
            continue
        try:
            geoms.append(shapely.force_2d(shape(shp.__geo_interface__)))
        except Exception as err:
            raise AOIError(f"A shape in the shapefile is malformed ({err}).") from err
    if ignored:
        warnings.append(f"Ignored {ignored} non-polygon shape(s) (points or lines).")
    if not geoms:
        raise AOIError("The shapefile contains no polygons.")

    source_crs, assumed = _shapefile_crs(prj_text, geoms)
    if assumed:
        warnings.append("No .prj file: coordinates look like degrees, so WGS84 was assumed.")

    return _finalize(geoms, source_crs, warnings, max_area_km2)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _collect_geojson_geometries(obj: object, out: list[dict], warnings: list[str]) -> None:
    if not isinstance(obj, dict):
        raise AOIError("The file is not valid GeoJSON (a geometry or feature is malformed).")
    kind = obj.get("type")
    if kind == "FeatureCollection":
        for feature in obj.get("features") or []:
            _collect_geojson_geometries(feature, out, warnings)
    elif kind == "Feature":
        geometry = obj.get("geometry")
        if geometry is None:
            warnings.append("Ignored a feature with no geometry.")
        else:
            _collect_geojson_geometries(geometry, out, warnings)
    elif kind == "GeometryCollection":
        for geometry in obj.get("geometries") or []:
            _collect_geojson_geometries(geometry, out, warnings)
    elif kind in _GEOJSON_GEOMETRY_TYPES:
        out.append(obj)
    else:
        raise AOIError(f"The file is not valid GeoJSON (unknown type {kind!r}).")


def _geojson_crs(doc: dict, warnings: list[str]) -> pyproj.CRS:
    """Honour a legacy GeoJSON ``crs`` member; otherwise WGS84 (the GeoJSON standard)."""
    crs = doc.get("crs")
    if not crs:
        return WGS84
    try:
        name = crs["properties"]["name"]
        parsed = pyproj.CRS.from_user_input(name)
    except Exception as err:
        raise AOIError(f"The GeoJSON declares a coordinate system we cannot read ({crs}).") from err
    if parsed != WGS84:
        warnings.append(f"Converted from the declared coordinate system {name}.")
    return parsed


def _shapefile_crs(prj_text: str | None, geoms: list[BaseGeometry]) -> tuple[pyproj.CRS, bool]:
    """Return (crs, assumed). Reject coordinates whose system cannot be known."""
    if prj_text:
        try:
            return pyproj.CRS.from_wkt(prj_text), False
        except Exception as err:
            raise AOIError(f"The .prj file could not be understood ({err}).") from err
    minx, miny, maxx, maxy = unary_union(geoms).bounds
    if max(abs(minx), abs(maxx)) <= 180 and max(abs(miny), abs(maxy)) <= 90:
        return WGS84, True
    raise AOIError(
        "The shapefile has no .prj file and its coordinates look like metres, "
        "so the coordinate system cannot be known. Add the .prj file to the zip."
    )


def _to_polygons(geom: BaseGeometry) -> tuple[list[Polygon], int]:
    """Keep polygons only. Returns (polygons, number of ignored non-polygon parts)."""
    if geom.is_empty:
        return [], 0
    if isinstance(geom, Polygon):
        return [geom], 0
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms), 0
    if hasattr(geom, "geoms"):  # collections produced by repair or GeoJSON
        polys: list[Polygon] = []
        ignored = 0
        for part in geom.geoms:
            p, i = _to_polygons(part)
            polys.extend(p)
            ignored += i
        return polys, ignored
    return [], 1


def _finalize(
    geoms: list[BaseGeometry],
    source_crs: pyproj.CRS,
    warnings: list[str],
    max_area_km2: float,
) -> AOI:
    if max_area_km2 <= 0:
        raise ValueError("max_area_km2 must be positive")

    # 1. Keep polygons only; points and lines are ignored with a warning.
    polygons: list[Polygon] = []
    ignored = 0
    for g in geoms:
        p, i = _to_polygons(g)
        polygons.extend(p)
        ignored += i
    if ignored:
        warnings.append(f"Ignored {ignored} non-polygon geometry part(s) (points or lines).")
    if not polygons:
        raise AOIError("The file contains no polygons. An area must be a polygon.")

    # 2. Convert to WGS84.
    geometry: BaseGeometry = unary_union(polygons)
    if source_crs != WGS84:
        try:
            to_wgs84 = pyproj.Transformer.from_crs(source_crs, WGS84, always_xy=True)
            geometry = _reproject(geometry, to_wgs84)
        except Exception as err:
            raise AOIError(f"Could not convert the coordinates to WGS84 ({err}).") from err

    # 3. Reject impossible coordinates (a common sign of swapped x/y or a wrong CRS).
    if not _finite_bounds(geometry):
        raise AOIError("The coordinates contain invalid numbers (NaN or infinity).")
    minx, miny, maxx, maxy = geometry.bounds
    if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
        raise AOIError(
            "Coordinates are outside valid longitude/latitude ranges "
            f"(bounds: {minx:.4f}, {miny:.4f}, {maxx:.4f}, {maxy:.4f}). "
            "Longitude must be within -180..180 and latitude within -90..90. "
            "This often means x and y are swapped or the coordinate system is wrong."
        )

    # 4. Repair invalid polygons (for example self-intersecting bow-ties).
    repaired = False
    if not geometry.is_valid:
        fixed = shapely.make_valid(geometry)
        fixed_polys, _ = _to_polygons(fixed)
        if not fixed_polys:
            raise AOIError("The polygon is invalid and could not be repaired.")
        geometry = unary_union(fixed_polys)
        repaired = True
        warnings.append("The polygon was invalid (for example self-intersecting) and was repaired.")
    final_polys, _ = _to_polygons(geometry)
    geometry = unary_union(final_polys) if final_polys else geometry
    if geometry.is_empty:
        raise AOIError("The area is empty after cleaning. Check the polygon.")

    # 5. Area in an equal-area projection, then the size limit.
    to_equal_area = pyproj.Transformer.from_crs(WGS84, EQUAL_AREA, always_xy=True)
    area_km2 = _reproject(geometry, to_equal_area).area / 1e6
    if area_km2 <= 0:
        raise AOIError("The area has zero size. Check that the polygon has three distinct points.")
    if area_km2 > max_area_km2:
        raise AOIError(
            f"The area is {area_km2:,.1f} km2, above the limit of {max_area_km2:,.1f} km2. "
            "Upload a smaller area."
        )

    centroid = geometry.centroid
    return AOI(
        geometry=geometry,
        area_km2=area_km2,
        centroid=(centroid.x, centroid.y),
        bounds=tuple(geometry.bounds),
        source_crs=source_crs.to_string(),
        was_repaired=repaired,
        warnings=warnings,
    )


def _reproject(geometry: BaseGeometry, transformer: pyproj.Transformer) -> BaseGeometry:
    """Apply a pyproj transformer to every coordinate of a geometry."""

    def convert(coords: np.ndarray) -> np.ndarray:
        x, y = transformer.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    return shapely.transform(geometry, convert)


def _finite_bounds(geometry: BaseGeometry) -> bool:
    return all(v == v and abs(v) != float("inf") for v in geometry.bounds)
