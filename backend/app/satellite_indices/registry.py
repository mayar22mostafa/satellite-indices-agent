"""Registry v2: the single source of truth for satellites and indices (Pydantic).

Same public API as v1 (SENTINEL2, SATELLITES, INDICES, get_index, get_satellite,
coarsest_resolution_m, to_reflectance, list_capabilities, ...), but every entry is
now a validated Pydantic model. A typo in a band name, a negative resolution or an
index that points to a band the satellite does not have fails at import time,
not later in the middle of an analysis.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Reusable annotated types (the "data annotation": type + constraints + docs)
# ---------------------------------------------------------------------------
Metres = Annotated[int, Field(gt=0, description="Native pixel size in metres")]
SatelliteKey = Annotated[
    str,
    Field(pattern=r"^[a-z0-9_]+$", description="Internal lowercase key, e.g. 'sentinel2'"),
]
IndexKey = Annotated[
    str,
    Field(pattern=r"^[A-Z0-9]+$", description="Internal uppercase key, e.g. 'NDVI'"),
]
BandName = Annotated[str, Field(min_length=1, description="Band name in the EE collection")]
EECollectionId = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-]+)+$",
        description="Earth Engine image collection id, e.g. COPERNICUS/S2_SR_HARMONIZED",
    ),
]


class _Frozen(BaseModel):
    """Immutable, and reject unknown fields so typos are caught."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Band(_Frozen):
    name: BandName
    resolution_m: Metres
    description: str = Field(min_length=1)


class Satellite(_Frozen):
    key: SatelliteKey
    ee_collection: EECollectionId
    bands: dict[BandName, Band] = Field(min_length=1)
    scale_factor: float = Field(
        gt=0, description="stored value * scale_factor + offset = reflectance"
    )
    offset: float
    cloud_mask_method: Literal["scl", "cloud_score_plus"]
    cloud_property: str = Field(min_length=1, description="Image property with scene cloud %")

    @model_validator(mode="after")
    def _band_keys_match_names(self) -> Satellite:
        for key, band in self.bands.items():
            if key != band.name:
                raise ValueError(f"Band key {key!r} does not match band name {band.name!r}")
        return self


class Index(_Frozen):
    key: IndexKey
    name: str = Field(min_length=1)
    formula: str = Field(min_length=1, description="Human-readable only; not executed")
    # Normalized difference: (a - b) / (a + b), where a and b are band keys
    a: BandName
    b: BandName
    measures: str = Field(min_length=1)
    satellite: SatelliteKey = "sentinel2"

    @model_validator(mode="after")
    def _distinct_bands(self) -> Index:
        if self.a == self.b:
            raise ValueError(f"Index {self.key}: a and b must be different bands")
        return self

    def bands_used(self) -> tuple[str, str]:
        return (self.a, self.b)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
SENTINEL2 = Satellite(
    key="sentinel2",
    # L2A = surface reflectance, already atmospherically corrected.
    # HARMONIZED keeps values consistent across processing-baseline changes.
    ee_collection="COPERNICUS/S2_SR_HARMONIZED",
    bands={
        "B3": Band(name="B3", resolution_m=10, description="Green"),
        "B4": Band(name="B4", resolution_m=10, description="Red"),
        "B8": Band(name="B8", resolution_m=10, description="NIR"),
        "B11": Band(name="B11", resolution_m=20, description="SWIR1"),
        "SCL": Band(name="SCL", resolution_m=20, description="Scene classification layer"),
    },
    scale_factor=1 / 10000,  # stored value = reflectance * 10000
    offset=0.0,
    cloud_mask_method="scl",
    cloud_property="CLOUDY_PIXEL_PERCENTAGE",
)

SATELLITES: dict[str, Satellite] = {SENTINEL2.key: SENTINEL2}

INDICES: dict[str, Index] = {
    "NDVI": Index(
        key="NDVI",
        name="Normalized Difference Vegetation Index",
        formula="(NIR - Red) / (NIR + Red)",
        a="B8",
        b="B4",
        measures="Vegetation greenness",
    ),
    "NDWI": Index(
        key="NDWI",
        name="Normalized Difference Water Index",
        formula="(Green - NIR) / (Green + NIR)",
        a="B3",
        b="B8",
        measures="Open water",
    ),
    "NDBI": Index(
        key="NDBI",
        name="Normalized Difference Built-up Index",
        formula="(SWIR1 - NIR) / (SWIR1 + NIR)",
        a="B11",
        b="B8",
        measures="Built-up surfaces (computed at 20 m: B11 is a 20 m band)",
    ),
}


def _validate_registry() -> None:
    """Cross-checks that a single model cannot do: run once at import time."""
    for key, sat in SATELLITES.items():
        if key != sat.key:
            raise ValueError(f"SATELLITES key {key!r} does not match satellite key {sat.key!r}")
    for key, idx in INDICES.items():
        if key != idx.key:
            raise ValueError(f"INDICES key {key!r} does not match index key {idx.key!r}")
        if idx.satellite not in SATELLITES:
            raise ValueError(f"Index {key}: unknown satellite {idx.satellite!r}")
        sat = SATELLITES[idx.satellite]
        for band in idx.bands_used():
            if band not in sat.bands:
                raise ValueError(
                    f"Index {key}: band {band!r} is not defined for {sat.key} "
                    f"(available: {sorted(sat.bands)})"
                )


_validate_registry()

# Sentinel-2 Scene Classification Layer values that are NOT usable pixels.
# 3 cloud shadow, 8 cloud medium prob., 9 cloud high prob., 10 thin cirrus, 11 snow/ice
SCL_MASKED_CLASSES = (3, 8, 9, 10, 11)

# Area limit enforced by area reading (km2). Final value set after Cairo
# measurement in sprint 1 (see risks table in the proposal).
DEFAULT_MAX_AREA_KM2 = 2500.0


# ---------------------------------------------------------------------------
# Public functions (same behaviour as v1)
# ---------------------------------------------------------------------------
def list_capabilities() -> dict:
    """What the agent's list_capabilities tool will return."""
    return {
        "satellites": sorted(SATELLITES),
        "indices": {
            k: {
                "formula": i.formula,
                "bands": list(i.bands_used()),
                "measures": i.measures,
                "satellite": i.satellite,
            }
            for k, i in INDICES.items()
        },
    }


def get_index(key: str) -> Index:
    try:
        return INDICES[key.upper()]
    except KeyError:
        raise ValueError(f"Unknown index {key!r}. Supported: {sorted(INDICES)}") from None


def get_satellite(key: str) -> Satellite:
    try:
        return SATELLITES[key.lower()]
    except KeyError:
        raise ValueError(f"Unknown satellite {key!r}. Supported: {sorted(SATELLITES)}") from None


def coarsest_resolution_m(index: Index) -> int:
    """Statistics/computation scale: coarsest resolution among bands used."""
    sat = get_satellite(index.satellite)
    return max(sat.bands[b].resolution_m for b in index.bands_used())


def to_reflectance(raw, sat: Satellite):
    """Apply the satellite's scale and offset (works on numbers or numpy arrays)."""
    return raw * sat.scale_factor + sat.offset
