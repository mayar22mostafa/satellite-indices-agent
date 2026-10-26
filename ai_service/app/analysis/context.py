"""Shared run context: stores Earth Engine objects by short IDs."""

from dataclasses import dataclass, field


@dataclass
class RunContext:
    aois: dict = field(default_factory=dict)     # aoi_id    -> ee.Geometry
    images: dict = field(default_factory=dict)   # image_ref -> {"image": ee.Image, "date": str}
    results: dict = field(default_factory=dict)  # result_id -> {"image": ee.Image, "aoi_id": str, ...}