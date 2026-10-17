import io
import json
import zipfile
from pathlib import Path

import pyproj
import pytest
import shapefile
from pydantic import ValidationError
from shapely.geometry import Point, Polygon
from shapely.geometry.polygon import orient

from satellite_indices.aoi import (
    AOI,
    AOIError,
    aoi_from_geojson_bytes,
    aoi_from_zipped_shapefile,
    read_aoi,
)

# A 0.02 x 0.02 degree square, about 4.2 km2.
SQUARE = [[30.98, 30.76], [31.0, 30.76], [31.0, 30.78], [30.98, 30.78], [30.98, 30.76]]
# A self-intersecting "bow-tie", about 0.5 km2.
BOW_TIE = [[30.0, 30.0], [30.01, 30.01], [30.01, 30.0], [30.0, 30.01], [30.0, 30.0]]


def gj(obj) -> bytes:
    return json.dumps(obj).encode()


def polygon(coords):
    return {"type": "Polygon", "coordinates": [coords]}


def make_zip(parts: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return out.getvalue()


def shapefile_parts(rings, shape_type=shapefile.POLYGON, prj_text=None) -> dict[str, bytes]:
    buffers = {k: io.BytesIO() for k in ("shp", "shx", "dbf")}
    writer = shapefile.Writer(**buffers, shapeType=shape_type)
    writer.field("name", "C")
    if shape_type == shapefile.POLYGON:
        for ring in rings:
            writer.poly([list(orient(Polygon(ring), sign=-1.0).exterior.coords)])
            writer.record("a")
    else:
        for x, y in rings:
            writer.point(x, y)
            writer.record("a")
    writer.close()
    parts = {f"area.{k}": v.getvalue() for k, v in buffers.items()}
    if prj_text is not None:
        parts["area.prj"] = prj_text.encode()
    return parts


# --- GeoJSON ------------------------------------------------------------------
def test_geojson_polygon_is_read():
    aoi = aoi_from_geojson_bytes(gj(polygon(SQUARE)))
    assert aoi.area_km2 == pytest.approx(4.245, abs=0.01)
    assert aoi.centroid == pytest.approx((30.99, 30.77))
    assert aoi.bounds == pytest.approx((30.98, 30.76, 31.0, 30.78))
    assert aoi.was_repaired is False
    assert aoi.warnings == []
    assert aoi.describe() == {
        "area_km2": 4.245,
        "centroid_lon_lat": [30.99, 30.77],
        "bounds": [30.98, 30.76, 31.0, 30.78],
        "repaired": False,
        "warnings": [],
    }


def test_feature_and_feature_collection_are_read():
    feature = {"type": "Feature", "properties": {}, "geometry": polygon(SQUARE)}
    collection = {"type": "FeatureCollection", "features": [feature]}
    assert aoi_from_geojson_bytes(gj(feature)).area_km2 == pytest.approx(4.245, abs=0.01)
    assert aoi_from_geojson_bytes(gj(collection)).area_km2 == pytest.approx(4.245, abs=0.01)


def test_bow_tie_is_repaired_with_a_warning():
    aoi = aoi_from_geojson_bytes(gj(polygon(BOW_TIE)))
    assert aoi.was_repaired is True
    assert any("repaired" in w for w in aoi.warnings)
    assert aoi.geometry.is_valid
    assert aoi.area_km2 == pytest.approx(0.535, abs=0.01)


def test_points_are_ignored_with_a_warning_when_a_polygon_exists():
    collection = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": polygon(SQUARE)},
            {"type": "Feature", "properties": {}, "geometry": Point(31, 30).__geo_interface__},
        ],
    }
    aoi = aoi_from_geojson_bytes(gj(collection))
    assert any("non-polygon" in w for w in aoi.warnings)


def test_only_points_is_an_error():
    with pytest.raises(AOIError, match="no polygons"):
        aoi_from_geojson_bytes(gj({"type": "Point", "coordinates": [31, 30]}))


@pytest.mark.parametrize(
    "payload, message",
    [
        (b"not json at all", "not valid GeoJSON"),
        (gj([1, 2, 3]), "not valid GeoJSON"),
        (gj({"type": "FeatureCollection", "features": []}), "no geometry"),
        (gj({"type": "Banana"}), "unknown type"),
        (gj({"type": "Polygon", "coordinates": "oops"}), "malformed"),
    ],
)
def test_bad_geojson_gives_a_clear_error(payload, message):
    with pytest.raises(AOIError, match=message):
        aoi_from_geojson_bytes(payload)


def test_out_of_range_coordinates_are_rejected():
    far = [[300, 0], [301, 0], [301, 1], [300, 1], [300, 0]]
    with pytest.raises(AOIError, match="outside valid longitude/latitude"):
        aoi_from_geojson_bytes(gj(polygon(far)))


def test_swapped_x_y_is_rejected():
    swapped = [[lat, lon] for lon, lat in SQUARE]
    swapped = [[a, b + 100] for a, b in swapped]  # latitude far outside +-90
    with pytest.raises(AOIError, match="outside valid longitude/latitude"):
        aoi_from_geojson_bytes(gj(polygon(swapped)))


def test_area_above_the_limit_is_rejected():
    big = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    with pytest.raises(AOIError, match="above the limit"):
        aoi_from_geojson_bytes(gj(polygon(big)))


def test_custom_limit_is_honoured():
    with pytest.raises(AOIError, match="above the limit of 1.0 km2"):
        aoi_from_geojson_bytes(gj(polygon(SQUARE)), max_area_km2=1.0)
    assert aoi_from_geojson_bytes(gj(polygon(SQUARE)), max_area_km2=10.0).area_km2 > 4


def test_legacy_geojson_crs_is_converted():
    to_utm = pyproj.Transformer.from_crs(4326, 32636, always_xy=True)
    projected = [list(to_utm.transform(x, y)) for x, y in SQUARE]
    doc = polygon(projected)
    doc["crs"] = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32636"}}
    aoi = aoi_from_geojson_bytes(gj(doc))
    assert aoi.bounds == pytest.approx((30.98, 30.76, 31.0, 30.78), abs=1e-4)
    assert aoi.area_km2 == pytest.approx(4.245, abs=0.02)
    assert any("Converted" in w for w in aoi.warnings)


# --- Shapefile ----------------------------------------------------------------
def test_zipped_shapefile_without_prj_assumes_wgs84_with_a_warning():
    aoi = aoi_from_zipped_shapefile(make_zip(shapefile_parts([SQUARE])))
    assert aoi.area_km2 == pytest.approx(4.245, abs=0.01)
    assert any("WGS84 was assumed" in w for w in aoi.warnings)


def test_zipped_shapefile_with_prj_is_converted_to_wgs84():
    utm = pyproj.CRS.from_epsg(32636)
    to_utm = pyproj.Transformer.from_crs(4326, utm, always_xy=True)
    projected = [list(to_utm.transform(x, y)) for x, y in SQUARE]
    parts = shapefile_parts([projected], prj_text=utm.to_wkt())
    aoi = aoi_from_zipped_shapefile(make_zip(parts))
    assert aoi.bounds == pytest.approx((30.98, 30.76, 31.0, 30.78), abs=1e-4)
    assert aoi.area_km2 == pytest.approx(4.245, abs=0.02)
    assert aoi.warnings == []


def test_shapefile_in_metres_without_prj_is_rejected():
    metres = [[500000, 3400000], [502000, 3400000], [502000, 3402000], [500000, 3402000]]
    metres.append(metres[0])
    with pytest.raises(AOIError, match="no .prj"):
        aoi_from_zipped_shapefile(make_zip(shapefile_parts([metres])))


def test_shapefile_with_only_points_is_rejected():
    parts = shapefile_parts([(31, 30), (31.1, 30.1)], shape_type=shapefile.POINT)
    with pytest.raises(AOIError, match="no polygons"):
        aoi_from_zipped_shapefile(make_zip(parts))


def test_incomplete_shapefile_is_rejected():
    parts = shapefile_parts([SQUARE])
    del parts["area.dbf"]
    with pytest.raises(AOIError, match="missing .dbf"):
        aoi_from_zipped_shapefile(make_zip(parts))


def test_zip_without_a_shp_is_rejected():
    with pytest.raises(AOIError, match="no .shp"):
        aoi_from_zipped_shapefile(make_zip({"readme.txt": b"hello"}))


def test_not_a_zip_is_rejected():
    with pytest.raises(AOIError, match="not a valid .zip"):
        aoi_from_zipped_shapefile(b"plain bytes")


def test_two_shapefiles_in_one_zip_are_rejected():
    parts = shapefile_parts([SQUARE])
    parts.update({k.replace("area", "other"): v for k, v in parts.items()})
    with pytest.raises(AOIError, match="2 shapefiles"):
        aoi_from_zipped_shapefile(make_zip(parts))


def test_macos_resource_files_are_ignored():
    parts = shapefile_parts([SQUARE])
    parts["__MACOSX/._area.shp"] = b"junk"
    parts["._area.dbf"] = b"junk"
    assert aoi_from_zipped_shapefile(make_zip(parts)).area_km2 > 4


# --- Files --------------------------------------------------------------------
def test_read_aoi_from_geojson_and_zip_files(tmp_path: Path):
    geojson = tmp_path / "field.geojson"
    geojson.write_bytes(gj(polygon(SQUARE)))
    archive = tmp_path / "field.zip"
    archive.write_bytes(make_zip(shapefile_parts([SQUARE])))
    assert read_aoi(geojson).area_km2 == pytest.approx(4.245, abs=0.01)
    assert read_aoi(archive).area_km2 == pytest.approx(4.245, abs=0.01)


def test_read_aoi_errors(tmp_path: Path):
    with pytest.raises(AOIError, match="File not found"):
        read_aoi(tmp_path / "missing.geojson")
    other = tmp_path / "notes.txt"
    other.write_text("x")
    with pytest.raises(AOIError, match="Unsupported file type"):
        read_aoi(other)
    lone = tmp_path / "area.shp"
    lone.write_bytes(b"x")
    with pytest.raises(AOIError, match="Zip the .shp"):
        read_aoi(lone)


def test_bundled_test_area_is_readable():
    bundled = Path(__file__).parent.parent / "satellite_indices" / "data" / "test_area.geojson"
    assert read_aoi(bundled).area_km2 == pytest.approx(4.245, abs=0.01)


# --- The AOI model itself refuses invalid data --------------------------------
def test_aoi_model_rejects_non_polygons_and_bad_values():
    common = dict(area_km2=1.0, centroid=(31, 30), bounds=(30, 30, 31, 31), source_crs="EPSG:4326")
    with pytest.raises(ValidationError):
        AOI(geometry=Point(31, 30), **common)
    with pytest.raises(ValidationError):
        AOI(geometry=Polygon(), **common)
    ok = Polygon(SQUARE)
    with pytest.raises(ValidationError):
        AOI(geometry=ok, **{**common, "area_km2": 0})
    with pytest.raises(ValidationError):
        AOI(geometry=ok, **{**common, "centroid": (300, 30)})
    # An invalid (bow-tie) polygon cannot be stored in an AOI.
    with pytest.raises(ValidationError):
        AOI(geometry=Polygon(BOW_TIE), **common)


def test_aoi_is_immutable_and_exports_geojson():
    aoi = aoi_from_geojson_bytes(gj(polygon(SQUARE)))
    with pytest.raises(ValidationError):
        aoi.area_km2 = 1.0
    exported = aoi.to_geojson()
    assert exported["type"] == "Polygon"
