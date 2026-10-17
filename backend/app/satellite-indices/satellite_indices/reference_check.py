"""Reference checks: verify that our numbers are *correct*, not just repeatable.

A deterministic rule can be repeatably wrong (a wrong band, a forgotten scale
factor), so every week we compare our values with an independent calculation.

This module provides:

* ``HAND_REFERENCE``: a 2x2 scene whose NDVI statistics were worked out by hand.
* ``compare_to_reference``: compares our statistics with reference values and
  returns a list of problems (an empty list means the check passed).
* ``code_editor_script``: generates JavaScript for the Earth Engine Code Editor
  that computes the same quantities independently of this repository's code.

The Code Editor script deliberately does **not** read the registry. It uses its own
textbook definitions (band pairs, cloud classes, collection, scale), and the test
suite checks that they agree with the registry. If somebody mistypes a band in the
registry, that test fails.

Usage::

    python -m satellite_indices.reference_check --check-hand-reference
    python -m satellite_indices.reference_check --print-code-editor-script --image-id <ID>
    python -m satellite_indices.reference_check --compare ours.json reference.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .aoi import read_aoi
from .indices import Statistics, compute_index_array, compute_statistics_array

# ---------------------------------------------------------------------------
# Independent ("textbook") definitions used by the Code Editor script.
# Kept separate from registry.py on purpose; tests assert they agree.
# ---------------------------------------------------------------------------
INDEPENDENT_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
INDEPENDENT_BANDS = {
    "NDVI": ("B8", "B4"),  # (NIR - Red) / (NIR + Red)
    "NDWI": ("B3", "B8"),  # (Green - NIR) / (Green + NIR)
    "NDBI": ("B11", "B8"),  # (SWIR1 - NIR) / (SWIR1 + NIR)
}
INDEPENDENT_SCALE_M = {"NDVI": 10, "NDWI": 10, "NDBI": 20}  # coarsest band used
INDEPENDENT_SCL_MASKED = (3, 8, 9, 10, 11)  # shadow, cloud medium/high, cirrus, snow/ice

COMPARED_KEYS = ("mean", "min", "max", "std", "valid_pixel_pct")


# ---------------------------------------------------------------------------
# Hand-calculated reference
# ---------------------------------------------------------------------------
class ReferenceStats(BaseModel):
    """Reference values to compare against (``None`` means "not specified")."""

    model_config = ConfigDict(frozen=True)

    mean: float | None = None
    min: float | None = None
    max: float | None = None
    std: float | None = None
    valid_pixel_pct: float | None = Field(default=None, ge=0, le=100)


class ReferenceScene(BaseModel):
    """A tiny scene with hand-calculated expected results."""

    model_config = ConfigDict(frozen=True)

    description: str
    index: str
    raw_bands: dict[str, list[list[int]]]  # raw Sentinel-2 values (reflectance x 10,000)
    scl: list[list[int]]
    expected_index: list[list[float | None]]  # None = masked
    expected: ReferenceStats

    def raw_arrays(self) -> dict[str, np.ndarray]:
        return {name: np.array(rows) for name, rows in self.raw_bands.items()}

    def scl_array(self) -> np.ndarray:
        return np.array(self.scl)


# Worked out by hand, NDVI = (NIR - Red) / (NIR + Red), reflectance = raw / 10000:
#   pixel (0,0): NIR 0.5, Red 0.1 -> (0.5 - 0.1) / (0.5 + 0.1) =  0.4 / 0.6 =  0.666667
#   pixel (0,1): NIR 0.3, Red 0.3 -> (0.3 - 0.3) / (0.3 + 0.3) =  0.0 / 0.6 =  0.0
#   pixel (1,0): NIR 0.2, Red 0.4 -> (0.2 - 0.4) / (0.2 + 0.4) = -0.2 / 0.6 = -0.333333
#   pixel (1,1): SCL = 9 (cloud, high probability) -> masked, not used
# Valid pixels: 3 of 4 -> 75 %.
# mean = (0.666667 + 0.0 - 0.333333) / 3 = 0.111111
# population std: deviations 0.555556, -0.111111, -0.444444;
#   squares 0.308642, 0.012346, 0.197531; sum 0.518519; / 3 = 0.172840; sqrt = 0.415740
HAND_REFERENCE = ReferenceScene(
    description="2x2 scene, NDVI worked out by hand; one pixel is cloud (SCL 9)",
    index="NDVI",
    raw_bands={
        "B8": [[5000, 3000], [2000, 7000]],  # NIR
        "B4": [[1000, 3000], [4000, 1000]],  # Red
    },
    scl=[[4, 5], [4, 9]],
    expected_index=[[0.666667, 0.0], [-0.333333, None]],
    expected=ReferenceStats(
        mean=0.111111, min=-0.333333, max=0.666667, std=0.415740, valid_pixel_pct=75.0
    ),
)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def _as_mapping(value: Statistics | ReferenceStats | Mapping) -> dict:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Cannot compare a {type(value).__name__}")


def compare_to_reference(
    ours: Statistics | ReferenceStats | Mapping,
    reference: Statistics | ReferenceStats | Mapping,
    tol: float = 0.01,
) -> list[str]:
    """Compare our statistics with reference values.

    Returns a list of problems; an empty list means the check passed.

    ``tol`` is the largest allowed absolute difference for mean, min, max and std.
    ``valid_pixel_pct`` is compared in percentage points with tolerance ``tol * 100``
    (default 1 point), because pixel counts at polygon edges can differ slightly
    between tools such as Earth Engine and QGIS.
    Keys the reference does not specify are skipped.
    """
    if tol < 0:
        raise ValueError("tol must not be negative")
    ours_map, ref_map = _as_mapping(ours), _as_mapping(reference)

    problems: list[str] = []
    for key in COMPARED_KEYS:
        expected = ref_map.get(key)
        if expected is None:
            continue
        actual = ours_map.get(key)
        if actual is None:
            problems.append(f"{key}: ours is missing, reference is {expected:.4f}")
            continue
        allowed = tol * 100 if key == "valid_pixel_pct" else tol
        difference = abs(actual - expected)
        if difference > allowed:
            problems.append(
                f"{key}: ours {actual:.4f} vs reference {expected:.4f} "
                f"(difference {difference:.4f} is above the tolerance {allowed:g})"
            )
    return problems


def check_against_hand_reference(tol: float = 0.0001) -> list[str]:
    """Run our array pipeline on ``HAND_REFERENCE`` and compare. Empty list = pass."""
    scene = HAND_REFERENCE
    index = compute_index_array(scene.index, scene.raw_arrays(), scl=scene.scl_array())
    problems = compare_to_reference(compute_statistics_array(index), scene.expected, tol=tol)

    expected = np.ma.masked_invalid(
        np.array([[np.nan if v is None else v for v in row] for row in scene.expected_index])
    )
    if not np.array_equal(np.ma.getmaskarray(index), np.ma.getmaskarray(expected)):
        problems.append("mask: masked pixels differ from the hand-calculated scene")
    else:
        both = ~np.ma.getmaskarray(index)
        if not np.allclose(np.ma.getdata(index)[both], np.ma.getdata(expected)[both], atol=tol):
            problems.append("index: pixel values differ from the hand-calculated scene")
    return problems


# ---------------------------------------------------------------------------
# Earth Engine Code Editor script (independent calculation)
# ---------------------------------------------------------------------------
_IMAGE_ID_RE = re.compile(r"^[A-Za-z0-9_\-/]+$")


def code_editor_script(
    aoi_geojson: dict,
    image_id: str,
    index_key: str = "NDVI",
) -> str:
    """JavaScript for the Earth Engine Code Editor computing the same statistics.

    Paste it into https://code.earthengine.google.com, run it, and compare the
    printed values with ours using ``compare_to_reference``. It prints a dictionary
    with the same keys as ``Statistics`` (mean, min, max, std, valid_pixels,
    total_pixels, valid_pixel_pct).
    """
    key = index_key.upper()
    if key not in INDEPENDENT_BANDS:
        raise ValueError(f"Unknown index {index_key!r}. Supported: {sorted(INDEPENDENT_BANDS)}")
    if not _IMAGE_ID_RE.match(image_id):
        raise ValueError(f"Image id {image_id!r} contains unexpected characters")

    full_id = image_id if "/" in image_id else f"{INDEPENDENT_COLLECTION}/{image_id}"
    band_a, band_b = INDEPENDENT_BANDS[key]
    scale = INDEPENDENT_SCALE_M[key]
    first, *rest = INDEPENDENT_SCL_MASKED
    scl_keep = f"scl.neq({first})" + "".join(f".and(scl.neq({c}))" for c in rest)

    return f"""// Independent reference calculation for {key}
// Generated by satellite_indices.reference_check (does not use the registry).
// Paste into https://code.earthengine.google.com and run.

var aoi = ee.Geometry({json.dumps(aoi_geojson)});
var image = ee.Image({json.dumps(full_id)});
var bands = [{json.dumps(band_a)}, {json.dumps(band_b)}];
var scale = {scale};  // metres: coarsest resolution among the bands used

// 1. Reflectance = stored value / 10000.
var refl = image.select(bands).multiply(0.0001);

// 2. Normalised difference, with zero denominators excluded.
var a = refl.select(bands[0]);
var b = refl.select(bands[1]);
var nd = refl.normalizedDifference(bands).updateMask(a.add(b).neq(0));

// 3. Cloud mask from the scene classification layer (SCL).
var scl = image.select('SCL');
var usable = {scl_keep};
nd = nd.updateMask(usable);

// 4. Statistics over the area, population standard deviation.
var reducer = ee.Reducer.mean()
  .combine({{reducer2: ee.Reducer.minMax(), sharedInputs: true}})
  .combine({{reducer2: ee.Reducer.stdDev(), sharedInputs: true}})
  .combine({{reducer2: ee.Reducer.count(), sharedInputs: true}});
var stats = nd.reduceRegion({{
  reducer: reducer, geometry: aoi, scale: scale, maxPixels: 1e9
}});

// 5. Pixels in the area, to report the valid-pixel percentage.
var total = ee.Image.constant(1).reduceRegion({{
  reducer: ee.Reducer.count(), geometry: aoi, scale: scale, maxPixels: 1e9
}}).get('constant');

var valid = ee.Number(stats.get('nd_count'));
var result = ee.Dictionary({{
  mean: stats.get('nd_mean'),
  min: stats.get('nd_min'),
  max: stats.get('nd_max'),
  std: stats.get('nd_stdDev'),
  valid_pixels: valid,
  total_pixels: total,
  valid_pixel_pct: valid.divide(ee.Number(total)).multiply(100)
}});
print('{key} reference values', result);
"""


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
def _default_aoi_path() -> Path:
    return Path(__file__).parent / "data" / "test_area.geojson"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reference checks for satellite-indices.")
    parser.add_argument("--check-hand-reference", action="store_true")
    parser.add_argument("--print-code-editor-script", action="store_true")
    parser.add_argument("--image-id", help="Sentinel-2 image id (with or without collection)")
    parser.add_argument("--index", default="NDVI", help="NDVI, NDWI or NDBI (default NDVI)")
    parser.add_argument("--aoi", type=Path, default=None, help="area file (default: test area)")
    parser.add_argument(
        "--compare", nargs=2, metavar=("OURS_JSON", "REFERENCE_JSON"), help="compare two JSON files"
    )
    parser.add_argument("--tol", type=float, default=0.01)
    args = parser.parse_args(argv)

    if not (args.check_hand_reference or args.print_code_editor_script or args.compare):
        parser.print_help()
        return 2

    status = 0
    if args.check_hand_reference:
        problems = check_against_hand_reference()
        print("Hand reference: PASS" if not problems else "Hand reference: FAIL")
        for problem in problems:
            print(" -", problem)
        status |= bool(problems)

    if args.compare:
        ours, reference = (json.loads(Path(p).read_text()) for p in args.compare)
        problems = compare_to_reference(ours, reference, tol=args.tol)
        print("Comparison: PASS" if not problems else "Comparison: FAIL")
        for problem in problems:
            print(" -", problem)
        status |= bool(problems)

    if args.print_code_editor_script:
        if not args.image_id:
            parser.error("--print-code-editor-script needs --image-id")
        aoi = read_aoi(args.aoi or _default_aoi_path())
        print(code_editor_script(aoi.to_geojson(), args.image_id, args.index))

    return status


if __name__ == "__main__":
    sys.exit(main())
