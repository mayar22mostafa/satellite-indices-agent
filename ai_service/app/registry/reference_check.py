"""Reference values: how we prove our numbers are correct, not just repeatable.

Two kinds of reference:

1. HAND-CALCULATED reference (works offline). A tiny scene whose NDVI was worked out on
   paper. ``HAND_SCENE`` and ``HAND_REFERENCE`` below are checked in the tests.

2. INDEPENDENT reference on a real test area (weekly). The numbers come from a different
   tool (Earth Engine Code Editor or QGIS) and are typed into ``data/reference_values.json``
   (schema: ``models.ReferenceSet``; see ``data/reference_values.example.json``).

Workflow for a real reference (see docs/sprint1-runbook.md):

    python -m satellite_indices.reference_check --print-code-editor-script --image-id ID
    # run the printed script at code.earthengine.google.com, type the numbers into
    # data/reference_values.json, then check a saved run against it:
    python -m satellite_indices.reference_check --compare output/ndvi_ID.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import AuditedRun, ReferenceSet, ReferenceValue, Statistics
from .registry import coarsest_resolution_m, get_index, get_satellite

# ---------------------------------------------------------------- 1. by hand
# Tiny scenes whose index values were worked out on paper, one per index. Raw Sentinel-2
# values (reflectance x 10000). A scene is a dict of band -> rows, plus the SCL rows.
#
# NDVI (2x2, all bands 10 m). Red = B4, NIR = B8.
#   pixel (0,0): NIR 5000, Red 1000 -> (0.5-0.1)/(0.5+0.1) = 0.4/0.6 = 0.666667
#   pixel (0,1): NIR 3000, Red 3000 -> 0/0.6               = 0.0
#   pixel (1,0): NIR 2000, Red 4000 -> (0.2-0.4)/(0.6)     = -0.333333
#   pixel (1,1): cloud (SCL=9) -> masked, not counted
# valid = 3 of 4 pixels = 75 %;  mean = (0.666667+0+(-0.333333))/3 = 0.111111
HAND_SCENE = {
    "raw": {"B8": [[5000, 3000], [2000, 7000]], "B4": [[1000, 3000], [4000, 1000]]},
    "scl": [[4, 5], [4, 9]],
}
HAND_REFERENCE = ReferenceValue(
    index="NDVI",
    image_id="HAND-CALCULATED",
    source="by hand (see comment above)",
    mean=1 / 9,
    min=-1 / 3,
    max=2 / 3,
    valid_pixel_pct=75.0,
)

# NDWI (2x2, all bands 10 m). Green = B3, NIR = B8.
#   pixel (0,0): Green 4000, NIR 1000 -> (0.4-0.1)/(0.5)  = 0.6
#   pixel (0,1): Green 2000, NIR 2000 -> 0
#   pixel (1,0): Green 1000, NIR 3000 -> (0.1-0.3)/(0.4)  = -0.5
#   pixel (1,1): SCL=8 (cloud, medium probability) -> masked
# valid = 75 %;  mean = (0.6+0-0.5)/3 = 0.033333
HAND_SCENE_NDWI = {
    "raw": {"B3": [[4000, 2000], [1000, 9000]], "B8": [[1000, 2000], [3000, 9000]]},
    "scl": [[4, 5], [4, 8]],
}
HAND_REFERENCE_NDWI = ReferenceValue(
    index="NDWI",
    image_id="HAND-CALCULATED",
    source="by hand (see comment above)",
    mean=1 / 30,
    min=-0.5,
    max=0.6,
    valid_pixel_pct=75.0,
)

# NDBI (2x2 at 20 m). SWIR1 = B11 is a 20 m band; NIR = B8 is a 10 m band, so B8 comes as
# 4x4 and each 20 m pixel uses the MEAN of its four 10 m pixels (blocks A B / C D):
#   block A: B11 6000, B8 mean (2000+6000+2000+6000)/4 = 4000 -> (0.6-0.4)/1.0  = 0.2
#            (taking only the top-left B8 pixel, 2000, would wrongly give 0.5)
#   block B: B11 3000, B8 all 5000                           -> (0.3-0.5)/0.8  = -0.25
#   block C: B11 3000, B8 all 3000                           -> 0
#   block D: SCL=9 (cloud) -> masked
# valid = 75 %;  mean = (0.2-0.25+0)/3 = -0.016667
HAND_SCENE_NDBI = {
    "raw": {
        "B11": [[6000, 3000], [3000, 7000]],
        "B8": [
            [2000, 6000, 5000, 5000],
            [2000, 6000, 5000, 5000],
            [3000, 3000, 7000, 7000],
            [3000, 3000, 7000, 7000],
        ],
    },
    "scl": [[4, 5], [6, 9]],
}
HAND_REFERENCE_NDBI = ReferenceValue(
    index="NDBI",
    image_id="HAND-CALCULATED",
    source="by hand (see comment above)",
    mean=-0.05 / 3,
    min=-0.25,
    max=0.2,
    valid_pixel_pct=75.0,
)

# index -> (scene, reference): one hand-calculated check per formula
HAND_CASES = {
    "NDVI": (HAND_SCENE, HAND_REFERENCE),
    "NDWI": (HAND_SCENE_NDWI, HAND_REFERENCE_NDWI),
    "NDBI": (HAND_SCENE_NDBI, HAND_REFERENCE_NDBI),
}

# --------------------------------------------------- 2. independent reference
DEFAULT_REFERENCE_FILE = Path(__file__).parent / "data" / "reference_values.json"


def compare_to_reference(
    ours: Statistics, reference: ReferenceValue, tol: float = 0.01
) -> list[str]:
    """Return a list of problems (empty list = pass).

    ``tol`` is an absolute tolerance on index values (0.01 = 1 % of the -1..1 range)
    because Earth Engine and QGIS resample slightly differently at polygon edges.
    valid_pixel_pct is allowed 2 percentage points. A missing value is a problem, never a pass.
    """
    problems = []
    for key in ("mean", "min", "max"):
        got, want = getattr(ours, key), getattr(reference, key)
        if got is None:
            problems.append(f"{key}: ours is empty (no valid pixels) vs reference {want:.4f}")
        elif abs(got - want) > tol:
            problems.append(f"{key}: ours {got:.4f} vs reference {want:.4f} (tolerance {tol})")
    if (
        reference.valid_pixel_pct is not None
        and abs(ours.valid_pixel_pct - reference.valid_pixel_pct) > 2.0
    ):
        problems.append(
            f"valid_pixel_pct: ours {ours.valid_pixel_pct} vs reference {reference.valid_pixel_pct}"
        )
    return problems


def compare_run_to_file(
    run_path: Path, reference_path: Path = DEFAULT_REFERENCE_FILE, tol: float = 0.01
) -> list[str]:
    """Check a saved run (output of run_ndvi) against the reference file."""
    run = AuditedRun.load(run_path)
    if run.synthetic:
        raise ValueError("This run used synthetic demo data; it cannot be compared to a reference.")
    if not Path(reference_path).exists():
        raise FileNotFoundError(
            f"{reference_path} does not exist yet. Create it from the Code Editor numbers "
            "(see data/reference_values.example.json for the format)."
        )
    ref = ReferenceSet.load(reference_path).find(run.result.index, run.result.image_id)
    return compare_to_reference(run.result.statistics, ref, tol)


# The independent script hard-codes these on purpose: if the registry changes, a human
# must re-check the script instead of both silently changing together.
_SCRIPT_SCALE_FACTOR = 1 / 10000
_SCRIPT_CLOUD_CLASSES = (3, 8, 9, 10, 11)


def code_editor_script(index_key: str, image_id: str, geojson_path: Path) -> str:
    """JavaScript for the Earth Engine Code Editor: an independent computation
    written WITHOUT our Python code, to produce the reference number."""
    index = get_index(index_key)
    sat = get_satellite(index.satellite)
    if sat.scale_factor != _SCRIPT_SCALE_FACTOR or sat.cloud_mask_classes != _SCRIPT_CLOUD_CLASSES:
        raise ValueError(
            "The registry's scale factor or cloud classes changed. Review the independent "
            "script in reference_check.py by hand, then update its hard-coded values."
        )
    scale = coarsest_resolution_m(index)
    grid_band = max(index.bands_used(), key=lambda name: sat.bands[name].resolution_m)
    coords = json.loads(Path(geojson_path).read_text())["geometry"]["coordinates"]

    def band_js(var: str, name: str) -> str:
        line = f"var {var} = img.select('{name}')"
        if sat.bands[name].resolution_m < scale:  # finer band: AVERAGE up to the common grid
            line += (
                ".reduceResolution({reducer: ee.Reducer.mean(), bestEffort: true, maxPixels: 1024})"
                ".reproject(proj)"
            )
        return line + ".divide(10000);"

    return f"""// Independent reference for {index.key} - paste in code.earthengine.google.com
var geom = ee.Geometry.Polygon({json.dumps(coords)});
var img = ee.Image('{sat.ee_collection}/{image_id}');
var proj = img.select('{grid_band}').projection();  // the index's pixel grid ({scale} m)
var scl = img.select('SCL');
var good = scl.neq(3).and(scl.neq(8)).and(scl.neq(9)).and(scl.neq(10)).and(scl.neq(11));
{band_js("a", index.a)}
{band_js("b", index.b)}
var idx = a.subtract(b).divide(a.add(b)).updateMask(good).rename('{index.key}');
var r = ee.Reducer.mean().combine(ee.Reducer.min(), '', true)
          .combine(ee.Reducer.max(), '', true).combine(ee.Reducer.count(), '', true);
print(idx.reduceRegion({{reducer: r, geometry: geom, scale: {scale}, maxPixels: 1e9}}));
// total pixels on the SAME grid (a plain ee.Image.constant(1) uses a degree grid and over-counts)
print(ee.Image.constant(1).reproject(proj).clip(geom).reduceRegion(
  {{reducer: ee.Reducer.count(), geometry: geom, scale: {scale}, maxPixels: 1e9}}));
// valid_pixel_pct = {index.key}_count / total count * 100
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--print-code-editor-script", action="store_true")
    ap.add_argument("--compare", type=Path, metavar="RUN.json", help="saved run to check")
    ap.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE_FILE)
    ap.add_argument("--tol", type=float, default=0.01)
    ap.add_argument("--index", default="NDVI")
    ap.add_argument(
        "--image-id",
        default="<IMAGE_ID>",
        help="Sentinel-2 image id, e.g. 20260920T083611_20260920T084512_T36RUU",
    )
    ap.add_argument(
        "--aoi", default=str(Path(__file__).parent / "data" / "test_area_delta.geojson")
    )
    args = ap.parse_args(argv)
    if args.print_code_editor_script:
        print(code_editor_script(args.index, args.image_id, Path(args.aoi)))
        return 0
    if args.compare:
        try:
            problems = compare_run_to_file(args.compare, args.reference, args.tol)
        except (ValueError, FileNotFoundError) as err:
            print(f"Cannot compare: {err}", file=sys.stderr)
            return 2
        if problems:
            print("FAIL: our result does not match the independent reference")
            for p in problems:
                print(f"  - {p}")
            return 1
        print(f"PASS: matches the reference within tolerance {args.tol}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
