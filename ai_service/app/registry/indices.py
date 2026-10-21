"""Index maths on plain arrays (numpy).

This is the reference implementation of the scientific rules. The Earth Engine
tools (ee_tools.py) apply the *same* rules on Google's servers; the tests and
the reference check compare the two. Rules, always applied:

  1. scale + offset from the registry (stored value -> reflectance)
  2. cloud/shadow mask (Sentinel-2 SCL classes from the registry)
  3. normalized difference with a safe zero denominator (-> masked, never inf)
  4. statistics over valid pixels only, with valid-pixel %
  5. a formula that mixes 10 m and 20 m bands (NDBI) is computed at 20 m: each 20 m pixel is
     the MEAN of the four 10 m pixels inside it (not one of them)
"""

from __future__ import annotations

import numpy as np

from .models import Statistics
from .registry import (
    SCL_MASKED_CLASSES,
    Index,
    coarsest_resolution_m,
    get_index,
    get_satellite,
    to_reflectance,
)


def normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(a - b) / (a + b). Where a + b == 0 the result is NaN (masked)."""
    a = np.asarray(a, dtype="float64")
    b = np.asarray(b, dtype="float64")
    denom = a + b
    out = np.full(denom.shape, np.nan)
    np.divide(a - b, denom, out=out, where=(denom != 0) & np.isfinite(denom))
    return out


def block_mean(array: np.ndarray, factor: int) -> np.ndarray:
    """Average ``factor`` x ``factor`` blocks (10 m -> 20 m is factor 2). NaN stays NaN."""
    array = np.asarray(array, dtype="float64")
    if factor == 1:
        return array
    rows, cols = array.shape
    if rows % factor or cols % factor:
        raise ValueError(f"A {rows}x{cols} array cannot be averaged in blocks of {factor}.")
    blocks = array.reshape(rows // factor, factor, cols // factor, factor)
    return blocks.mean(axis=(1, 3))


def _repeat_to(array: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    """Make a coarse array (e.g. 20 m SCL) match a finer result by repeating its pixels."""
    if array.shape == shape:
        return array
    fy, fx = shape[0] / array.shape[0], shape[1] / array.shape[1]
    if fy != fx or fy != int(fy) or fy < 1:
        raise ValueError(f"Cannot match an array of shape {array.shape} to {shape}.")
    return np.repeat(np.repeat(array, int(fy), axis=0), int(fx), axis=1)


def cloud_mask_from_scl(scl: np.ndarray) -> np.ndarray:
    """True where the pixel is usable (not cloud, shadow, cirrus or snow)."""
    return ~np.isin(scl, SCL_MASKED_CLASSES)


def compute_index_array(
    index_key: str, raw_bands: dict[str, np.ndarray], scl: np.ndarray | None = None
) -> np.ndarray:
    """Compute an index from RAW stored band values (e.g. 0..10000 for S2).

    Bands may come at their own native size: a 10 m band of an index that also uses a 20 m band
    (NDBI) is averaged down to the 20 m grid first. ``scl`` may be on the result grid or a
    coarser one (it is repeated up to the result). NaN marks masked or undefined pixels.
    """
    index: Index = get_index(index_key)
    sat = get_satellite(index.satellite)
    for band in index.bands_used():
        if band not in raw_bands:
            raise ValueError(f"{index.key} needs band {band}, which was not provided.")
    target_m = coarsest_resolution_m(index)
    reflectance = {}
    for name in index.bands_used():
        factor = target_m // sat.bands[name].resolution_m
        values = to_reflectance(np.asarray(raw_bands[name], dtype="float64"), sat)
        reflectance[name] = block_mean(values, factor)
    if reflectance[index.a].shape != reflectance[index.b].shape:
        raise ValueError(
            f"{index.key}: bands do not line up after matching resolutions "
            f"({reflectance[index.a].shape} vs {reflectance[index.b].shape})."
        )
    result = normalized_difference(reflectance[index.a], reflectance[index.b])
    if scl is not None:
        usable = cloud_mask_from_scl(_repeat_to(np.asarray(scl), result.shape))
        result = np.where(usable, result, np.nan)
    return result


def compute_statistics_array(values: np.ndarray, aoi_mask: np.ndarray | None = None) -> Statistics:
    """Mean, min, max, std (population) and valid-pixel % over the area.

    `aoi_mask` marks pixels inside the polygon (True = inside). Total pixels
    are the pixels inside the area; valid pixels are those that are not NaN.
    """
    values = np.asarray(values, dtype="float64")
    inside = np.ones(values.shape, dtype=bool) if aoi_mask is None else np.asarray(aoi_mask, bool)
    total = int(inside.sum())
    valid = inside & np.isfinite(values)
    n = int(valid.sum())
    pct = 100.0 * n / total if total else 0.0
    if n == 0:
        return Statistics(
            mean=None,
            min=None,
            max=None,
            std=None,
            valid_pixel_pct=round(pct, 2),
            valid_pixels=0,
            total_pixels=total,
        )
    v = values[valid]
    return Statistics(
        mean=float(v.mean()),
        min=float(v.min()),
        max=float(v.max()),
        std=float(v.std()),  # population std, same as EE stdDev()
        valid_pixel_pct=round(pct, 2),
        valid_pixels=n,
        total_pixels=total,
    )
