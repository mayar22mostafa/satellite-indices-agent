"""Reference implementation of the index maths on NumPy arrays.

This is the offline, easy-to-test version of the rules every analysis follows,
in this order:

1. Scale and offset: raw Sentinel-2 values are reflectance x 10,000 (from the registry).
2. Cloud mask: pixels whose SCL class is in ``SCL_MASKED_CLASSES`` are masked out.
3. Safe normalised difference: ``(a - b) / (a + b)``; where the denominator is zero
   the pixel is masked, never ``inf`` and never an unhandled ``NaN``.
4. Statistics on valid pixels only, always reported with the valid-pixel percentage.

Masked pixels are represented with ``numpy.ma`` masked arrays, so "no value" is
explicit and cannot be confused with a real number.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .registry import SCL_MASKED_CLASSES, get_index, get_satellite, to_reflectance


class Statistics(BaseModel):
    """Statistics of an index over the valid pixels of an area."""

    model_config = ConfigDict(frozen=True)

    mean: float | None = None
    min: float | None = None
    max: float | None = None
    std: float | None = Field(default=None, ge=0, description="Population standard deviation")
    valid_pixels: int = Field(ge=0)
    total_pixels: int = Field(ge=0)
    valid_pixel_pct: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _consistent(self) -> Statistics:
        if self.valid_pixels > self.total_pixels:
            raise ValueError("valid_pixels cannot exceed total_pixels")
        if self.valid_pixels == 0 and any(
            v is not None for v in (self.mean, self.min, self.max, self.std)
        ):
            raise ValueError("with no valid pixels, mean/min/max/std must be None")
        return self

    def as_dict(self) -> dict:
        """JSON-friendly dictionary (values rounded for display)."""

        def r(value: float | None, digits: int = 4) -> float | None:
            return None if value is None else round(value, digits)

        return {
            "mean": r(self.mean),
            "min": r(self.min),
            "max": r(self.max),
            "std": r(self.std),
            "valid_pixels": self.valid_pixels,
            "total_pixels": self.total_pixels,
            "valid_pixel_pct": round(self.valid_pixel_pct, 2),
        }


def normalized_difference(a, b) -> np.ma.MaskedArray:
    """``(a - b) / (a + b)`` with every unusable pixel masked.

    A pixel is masked when either input is masked or not finite, or when
    ``a + b == 0`` (division by zero).
    """
    a_data = np.asarray(np.ma.getdata(a), dtype=float)
    b_data = np.asarray(np.ma.getdata(b), dtype=float)
    if a_data.shape != b_data.shape:
        raise ValueError(f"Band shapes differ: {a_data.shape} vs {b_data.shape}")

    mask = (
        np.ma.getmaskarray(a) | np.ma.getmaskarray(b) | ~np.isfinite(a_data) | ~np.isfinite(b_data)
    )
    total = a_data + b_data
    mask = mask | (total == 0)

    safe_total = np.where(mask, 1.0, total)
    values = np.where(mask, 0.0, (a_data - b_data) / safe_total)
    return np.ma.array(values, mask=mask)


def cloud_mask_from_scl(scl) -> np.ndarray:
    """Boolean array that is ``True`` where the pixel is usable (not cloud, shadow, snow)."""
    return ~np.isin(np.asarray(scl), SCL_MASKED_CLASSES)


def compute_index_array(
    key: str,
    raw_bands: Mapping[str, np.ndarray],
    scl: np.ndarray | None = None,
) -> np.ma.MaskedArray:
    """Full pipeline on raw band arrays (reflectance x 10,000), returning a masked index.

    ``raw_bands`` must hold the bands the index needs, already on the same pixel grid
    (for NDBI, resample the 20 m band to the grid you compute on). When ``scl`` is
    given, cloudy and shadowed pixels are masked; without it nothing is cloud-masked.
    """
    index = get_index(key)
    satellite = get_satellite(index.satellite)

    missing = [band for band in index.bands_used() if band not in raw_bands]
    if missing:
        raise ValueError(f"{index.key} needs band(s) {missing}; got {sorted(raw_bands)}")

    # 1. scale and offset
    a = to_reflectance(np.asarray(raw_bands[index.a], dtype=float), satellite)
    b = to_reflectance(np.asarray(raw_bands[index.b], dtype=float), satellite)

    # 3. safe normalised difference
    result = normalized_difference(a, b)

    # 2. cloud mask
    if scl is not None:
        scl = np.asarray(scl)
        if scl.shape != result.shape:
            raise ValueError(f"SCL shape {scl.shape} does not match band shape {result.shape}")
        result = np.ma.array(
            np.ma.getdata(result), mask=np.ma.getmaskarray(result) | ~cloud_mask_from_scl(scl)
        )
    return result


def compute_statistics_array(values, aoi_mask: np.ndarray | None = None) -> Statistics:
    """Statistics over valid pixels.

    ``aoi_mask`` is ``True`` for pixels inside the area. Pixels outside the area do
    not count at all; pixels inside but masked (cloud, zero denominator) count in
    ``total_pixels`` but not in ``valid_pixels``, so the percentage exposes how much
    of the area the numbers really describe.
    """
    data = np.asarray(np.ma.getdata(values), dtype=float)
    masked = np.ma.getmaskarray(values) | ~np.isfinite(data)

    if aoi_mask is None:
        inside = np.ones(data.shape, dtype=bool)
    else:
        inside = np.asarray(aoi_mask, dtype=bool)
        if inside.shape != data.shape:
            raise ValueError(f"AOI mask shape {inside.shape} does not match {data.shape}")

    total = int(inside.sum())
    valid = inside & ~masked
    n_valid = int(valid.sum())
    pct = 100.0 * n_valid / total if total else 0.0

    if n_valid == 0:
        return Statistics(valid_pixels=0, total_pixels=total, valid_pixel_pct=pct)

    picked = data[valid]
    return Statistics(
        mean=float(picked.mean()),
        min=float(picked.min()),
        max=float(picked.max()),
        std=float(picked.std()),  # population standard deviation (ddof=0)
        valid_pixels=n_valid,
        total_pixels=total,
        valid_pixel_pct=pct,
    )
