"""Registry v2: the single source of truth for satellites and indices (dataclasses).

Adding an index or a satellite = adding a new entry here, not new code.
Every analysis tool reads bands, scale/offset, resolution, cloud-mask rules and index
formulas from this file, so the scientific rules are always applied.

The entries are plain frozen dataclasses, so the file has no dependency beyond the standard
library and reads like ordinary Python. Each class checks itself in ``__post_init__``: a typo
in a band name, a negative resolution, an index that points at a band the satellite does not
have, or a formula text that no longer matches its bands fails when the module is imported,
not in the middle of an analysis. (Pydantic is still used for the data that crosses a
boundary: results, saved runs, settings, the agent's plans. See ``models.py``.)
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

_KEY_SATELLITE = re.compile(r"^[a-z0-9_]+$")
_KEY_INDEX = re.compile(r"^[A-Z0-9]+$")
_EE_COLLECTION = re.compile(r"^[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-]+)+$")
_CLOUD_MASK_METHODS = ("scl", "cloud_score_plus")
_REVIEW_STATUSES = ("draft", "approved")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


@dataclass(frozen=True)
class Band:
    name: str  # band name as it appears in the Earth Engine collection
    resolution_m: int  # native pixel size in metres
    description: str

    def __post_init__(self) -> None:
        _require(bool(self.name), "Band name cannot be empty")
        _require(
            _is_int(self.resolution_m) and self.resolution_m > 0,
            f"Band {self.name!r}: resolution_m must be a positive whole number of metres, "
            f"got {self.resolution_m!r}",
        )
        _require(bool(self.description), f"Band {self.name!r}: description cannot be empty")


@dataclass(frozen=True)
class Satellite:
    key: str
    ee_collection: str  # Earth Engine image collection id
    bands: Mapping[str, Band]
    scale_factor: float  # stored value * scale_factor + offset = reflectance
    offset: float
    cloud_mask_method: str  # "scl" or "cloud_score_plus" (decided in week 1)
    cloud_property: str  # image property holding scene cloud %
    cloud_mask_band: str  # band holding the classification used to mask
    cloud_mask_classes: tuple[int, ...]  # class values of that band that are NOT usable pixels

    def __post_init__(self) -> None:
        _require(
            bool(_KEY_SATELLITE.match(self.key)),
            f"Satellite key {self.key!r} must be lower case letters, digits or _",
        )
        _require(
            bool(_EE_COLLECTION.match(self.ee_collection)),
            f"ee_collection {self.ee_collection!r} is not an Earth Engine collection id",
        )
        _require(len(self.bands) > 0, f"Satellite {self.key}: it needs at least one band")
        for name, band in self.bands.items():
            _require(
                isinstance(band, Band) and name == band.name,
                f"Band key {name!r} does not match band name {getattr(band, 'name', band)!r}",
            )
        _require(
            _is_number(self.scale_factor) and self.scale_factor > 0,
            f"scale_factor must be above 0, got {self.scale_factor!r}",
        )
        _require(_is_number(self.offset), f"offset must be a number, got {self.offset!r}")
        _require(
            self.cloud_mask_method in _CLOUD_MASK_METHODS,
            f"cloud_mask_method {self.cloud_mask_method!r} must be one of {_CLOUD_MASK_METHODS}",
        )
        _require(bool(self.cloud_property), "cloud_property cannot be empty")
        _require(
            self.cloud_mask_band in self.bands,
            f"cloud_mask_band {self.cloud_mask_band!r} is not a defined band",
        )
        classes = tuple(self.cloud_mask_classes)
        _require(len(classes) > 0, "cloud_mask_classes needs at least one class")
        _require(all(_is_int(c) for c in classes), "cloud_mask_classes must be whole numbers")
        _require(len(set(classes)) == len(classes), "cloud_mask_classes must not repeat")
        _require(all(c >= 0 for c in classes), "cloud_mask_classes must be non-negative")
        # Frozen: store read-only copies so nobody can change the bands or classes later.
        object.__setattr__(self, "cloud_mask_classes", classes)
        object.__setattr__(self, "bands", MappingProxyType(dict(self.bands)))


@dataclass(frozen=True)
class ValueBand:
    """A range of index values and what it usually means (a rule of thumb, not a classification)."""

    low: float
    high: float
    label: str

    def __post_init__(self) -> None:
        _require(bool(self.label), "A value band needs a label")
        _require(self.low < self.high, f"value band {self.label!r}: low must be below high")


@dataclass(frozen=True)
class IndexMeaning:
    """What an index means, in words the agent may repeat. Written by the science owner.

    The agent must explain an index only with this text, never from its own knowledge, so the
    explanation is the one the team reviewed. ``review_status`` stays ``draft`` until a named
    person approves it (``approved`` needs ``approved_by``).
    """

    summary: str  # one plain sentence: what the index shows
    how_to_read: tuple[ValueBand, ...]
    limitations: tuple[str, ...]  # what it does NOT tell you
    review_status: str = "draft"
    approved_by: str | None = None

    def __post_init__(self) -> None:
        _require(bool(self.summary), "A meaning needs a summary")
        bands, limitations = tuple(self.how_to_read), tuple(self.limitations)
        _require(len(bands) > 0, "A meaning needs at least one value band")
        _require(len(limitations) > 0, "A meaning needs at least one limitation")
        _require(
            self.review_status in _REVIEW_STATUSES,
            f"review_status {self.review_status!r} must be one of {_REVIEW_STATUSES}",
        )
        if self.review_status == "approved" and not self.approved_by:
            raise ValueError("an approved meaning must say who approved it (approved_by)")
        if self.review_status == "draft" and self.approved_by:
            raise ValueError("a draft meaning cannot have an approver; set review_status")
        object.__setattr__(self, "how_to_read", bands)
        object.__setattr__(self, "limitations", limitations)


@dataclass(frozen=True)
class Index:
    key: str
    name: str
    formula: str  # human-readable; checked against the bands
    # Normalized difference: (a - b) / (a + b), where a and b are band keys
    a: str
    b: str
    measures: str
    meaning: IndexMeaning
    satellite: str = "sentinel2"
    # Physically possible values; used by the plausibility checks in models.py
    value_range: tuple[float, float] = (-1.0, 1.0)

    def __post_init__(self) -> None:
        _require(
            bool(_KEY_INDEX.match(self.key)),
            f"Index key {self.key!r} must be upper case letters or digits",
        )
        _require(
            bool(self.name and self.formula and self.measures), f"Index {self.key}: empty text"
        )
        _require(bool(self.a and self.b), f"Index {self.key}: both bands are needed")
        _require(self.a != self.b, f"Index {self.key}: a and b must be different bands")
        _require(
            bool(_KEY_SATELLITE.match(self.satellite)),
            f"Index {self.key}: bad satellite key {self.satellite!r}",
        )
        low, high = self.value_range
        _require(low < high, f"Index {self.key}: value_range must be (low, high) with low < high")
        object.__setattr__(self, "value_range", (low, high))

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
        "B3": Band("B3", 10, "Green"),
        "B4": Band("B4", 10, "Red"),
        "B8": Band("B8", 10, "NIR"),
        "B11": Band("B11", 20, "SWIR1"),
        "SCL": Band("SCL", 20, "Scene classification layer"),
    },
    scale_factor=1 / 10000,  # stored value = reflectance * 10000
    offset=0.0,
    cloud_mask_method="scl",  # provisional: confirmed after the week-1 comparison on Cairo
    cloud_property="CLOUDY_PIXEL_PERCENTAGE",
    cloud_mask_band="SCL",
    # SCL classes that are NOT usable pixels:
    # 3 cloud shadow, 8 cloud medium prob., 9 cloud high prob., 10 thin cirrus, 11 snow/ice
    cloud_mask_classes=(3, 8, 9, 10, 11),
)

_SATELLITES: dict[str, Satellite] = {SENTINEL2.key: SENTINEL2}

_INDICES: dict[str, Index] = {
    "NDVI": Index(
        "NDVI",
        "Normalized Difference Vegetation Index",
        "(NIR - Red) / (NIR + Red)",
        a="B8",
        b="B4",
        measures="Vegetation greenness",
        meaning=IndexMeaning(
            summary="How green and dense the vegetation is (higher means more, healthier green).",
            how_to_read=(
                ValueBand(-1.0, 0.1, "water, bare surfaces, built-up, snow or cloud"),
                ValueBand(0.1, 0.3, "sparse vegetation or sparse crops"),
                ValueBand(0.3, 0.6, "moderate vegetation"),
                ValueBand(0.6, 1.0, "dense, healthy vegetation"),
            ),
            limitations=(
                "The ranges are rules of thumb; they shift with crop, season and soil colour.",
                "It does not say why vegetation is low (harvest, drought, disease or bare soil).",
                "It saturates over very dense vegetation, so small changes there are hard to see.",
            ),
        ),
    ),
    "NDWI": Index(
        "NDWI",
        "Normalized Difference Water Index",
        "(Green - NIR) / (Green + NIR)",
        a="B3",
        b="B8",
        measures="Open water",
        meaning=IndexMeaning(
            summary="Where open water is (higher means more likely open water).",
            how_to_read=(
                ValueBand(-1.0, 0.0, "land: vegetation, soil, built-up"),
                ValueBand(0.0, 0.3, "mixed or uncertain: wet ground, shallow or muddy water"),
                ValueBand(0.3, 1.0, "open water"),
            ),
            limitations=(
                "This is the open-water index (Green and NIR). It does not measure how much "
                "water is inside plants or soil.",
                "Built-up surfaces and shadows can look like water; compare with the image.",
                "The ranges are rules of thumb; turbid or shallow water gives lower values.",
            ),
        ),
    ),

    "MNDWI": Index(
        "MNDWI",
        "Modified Normalized Difference Water Index",
        "(Green - SWIR1) / (Green + SWIR1)",
        a="B3",
        b="B11",
        measures="Open water and water-related surface contrast",
        meaning=IndexMeaning(
            summary=(
                "Highlights open water relative to some built-up and bare surfaces."
            ),
            how_to_read=(
                ValueBand(-1.0, 0.0, "usually non-water surfaces"),
                ValueBand(0.0, 1.0, "potential water; verify against the imagery"),
            ),
            limitations=(
                "Thresholds vary with water turbidity, shallow water, soil, "
                "built-up surfaces and season.",
                "A positive value does not prove that a pixel is water.",
                "The index is computed at 20 m because B11 has 20 m native resolution.",
            ),
        ),
    ),

    "NDBI": Index(
        "NDBI",
        "Normalized Difference Built-up Index",
        "(SWIR1 - NIR) / (SWIR1 + NIR)",
        a="B11",
        b="B8",
        measures="Built-up surfaces (computed at 20 m: B11 is a 20 m band)",
        meaning=IndexMeaning(
            summary=(
                "How built-up the surface is (higher means more likely buildings and roads). "
                "Computed at 20 m."
            ),
            how_to_read=(
                ValueBand(-1.0, -0.1, "vegetation or water"),
                ValueBand(-0.1, 0.1, "mixed surfaces or bare ground"),
                ValueBand(0.1, 1.0, "likely built-up, but check against bare soil"),
            ),
            limitations=(
                "Dry bare soil and sand also give positive values; it is not a building count.",
                "The 20 m resolution cannot show single buildings or narrow streets.",
                "The ranges are rules of thumb; they differ between cities and seasons.",
            ),
        ),
    ),
}


def _validate_registry(satellites: Mapping[str, Satellite], indices: Mapping[str, Index]) -> None:
    """Cross-checks that a single entry cannot do on its own. Run once, at import time."""
    for key, sat in satellites.items():
        if key != sat.key:
            raise ValueError(f"SATELLITES key {key!r} does not match satellite key {sat.key!r}")
    for key, idx in indices.items():
        if key != idx.key:
            raise ValueError(f"INDICES key {key!r} does not match index key {idx.key!r}")
        if idx.satellite not in satellites:
            raise ValueError(f"Index {key}: unknown satellite {idx.satellite!r}")
        sat = satellites[idx.satellite]
        for band in idx.bands_used():
            if band not in sat.bands:
                raise ValueError(
                    f"Index {key}: band {band!r} is not defined for {sat.key} "
                    f"(available: {sorted(sat.bands)})"
                )
        # The readable formula must describe exactly the bands the code will use.
        da, db = sat.bands[idx.a].description, sat.bands[idx.b].description
        expected = f"({da} - {db}) / ({da} + {db})"
        if idx.formula != expected:
            raise ValueError(
                f"Index {key}: formula {idx.formula!r} does not match its bands "
                f"(a={idx.a} {da}, b={idx.b} {db}); expected {expected!r}"
            )


_validate_registry(_SATELLITES, _INDICES)

# Read-only views: nothing can add, replace or delete an entry after import.
SATELLITES: Mapping[str, Satellite] = MappingProxyType(_SATELLITES)
INDICES: Mapping[str, Index] = MappingProxyType(_INDICES)

# Kept as a module constant because the mask code imports it by name.
SCL_MASKED_CLASSES: tuple[int, ...] = SENTINEL2.cloud_mask_classes

# Area limit enforced by area reading (km2). Final value set after Cairo
# measurement in sprint 1 (see risks table in the proposal). Can be overridden
# per machine with the MAX_AREA_KM2 environment variable (see settings.py).
DEFAULT_MAX_AREA_KM2 = 2500.0

# Cloud limit used when the engineer does not give one (percent, measured over the area).
DEFAULT_MAX_CLOUD_PCT = 20.0


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------
def list_capabilities() -> dict:
    """What the agent's list_capabilities tool returns."""
    return {
        "satellites": sorted(SATELLITES),
        "indices": {
            k: {
                "formula": i.formula,
                "bands": list(i.bands_used()),
                "measures": i.measures,
                "satellite": i.satellite,
                "resolution_m": coarsest_resolution_m(i),
                "meaning": describe_meaning(i.key),
            }
            for k, i in INDICES.items()
        },
    }


def describe_meaning(key: str) -> dict:
    """The reviewed explanation of an index, as plain data for the agent."""
    meaning = get_index(key).meaning
    return {
        "summary": meaning.summary,
        "how_to_read": [
            {"from": b.low, "to": b.high, "means": b.label} for b in meaning.how_to_read
        ],
        "limitations": list(meaning.limitations),
        "review_status": meaning.review_status,
        "approved_by": meaning.approved_by,
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
