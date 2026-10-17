import pytest
from pydantic import ValidationError

from satellite_indices import registry
from satellite_indices.reference_check import (
    INDEPENDENT_BANDS,
    INDEPENDENT_COLLECTION,
    INDEPENDENT_SCALE_M,
    INDEPENDENT_SCL_MASKED,
)


def test_sentinel2_is_registered():
    sat = registry.get_satellite("Sentinel2")  # lookup ignores case
    assert sat is registry.SENTINEL2
    assert sat.ee_collection == "COPERNICUS/S2_SR_HARMONIZED"
    assert sat.scale_factor == pytest.approx(1 / 10000)
    assert sat.offset == 0


def test_unknown_names_list_supported_values():
    with pytest.raises(ValueError, match="Supported"):
        registry.get_index("EVI")
    with pytest.raises(ValueError, match="Supported"):
        registry.get_satellite("landsat")


def test_every_index_uses_bands_the_satellite_has():
    for index in registry.INDICES.values():
        sat = registry.get_satellite(index.satellite)
        for band in index.bands_used():
            assert band in sat.bands


def test_coarsest_resolution():
    assert registry.coarsest_resolution_m(registry.get_index("NDVI")) == 10
    assert registry.coarsest_resolution_m(registry.get_index("NDWI")) == 10
    assert registry.coarsest_resolution_m(registry.get_index("NDBI")) == 20


def test_to_reflectance():
    assert registry.to_reflectance(5000, registry.SENTINEL2) == pytest.approx(0.5)


def test_list_capabilities_has_all_indices():
    caps = registry.list_capabilities()
    assert caps["satellites"] == ["sentinel2"]
    assert set(caps["indices"]) == {"NDVI", "NDWI", "NDBI"}
    assert caps["indices"]["NDBI"]["bands"] == ["B11", "B8"]


# --- Pydantic validation: mistakes fail when the registry is built -------------
def test_negative_resolution_is_rejected():
    with pytest.raises(ValidationError):
        registry.Band(name="B3", resolution_m=-10, description="Green")


def test_unknown_cloud_method_is_rejected():
    data = registry.SENTINEL2.model_dump()
    data["cloud_mask_method"] = "magic"
    with pytest.raises(ValidationError):
        registry.Satellite(**data)


def test_index_with_identical_bands_is_rejected():
    with pytest.raises(ValidationError):
        registry.Index(key="X1", name="n", formula="f", a="B8", b="B8", measures="m")


def test_index_key_must_be_uppercase():
    with pytest.raises(ValidationError):
        registry.Index(key="ndvi", name="n", formula="f", a="B8", b="B4", measures="m")


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        registry.Band(name="B3", resolution_m=10, description="Green", colour="green")


def test_registry_objects_are_immutable():
    with pytest.raises(ValidationError):
        registry.SENTINEL2.offset = 1.0


# --- The registry agrees with the independent textbook definitions ------------
def test_registry_matches_independent_definitions():
    """Catches a mistyped band or class in the registry (see reference_check.py)."""
    assert registry.SENTINEL2.ee_collection == INDEPENDENT_COLLECTION
    assert tuple(registry.SCL_MASKED_CLASSES) == INDEPENDENT_SCL_MASKED
    for key, bands in INDEPENDENT_BANDS.items():
        index = registry.get_index(key)
        assert index.bands_used() == bands
        assert registry.coarsest_resolution_m(index) == INDEPENDENT_SCALE_M[key]
