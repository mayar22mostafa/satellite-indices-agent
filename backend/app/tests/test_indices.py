import numpy as np
import pytest
from pydantic import ValidationError

from satellite_indices.indices import (
    Statistics,
    cloud_mask_from_scl,
    compute_index_array,
    compute_statistics_array,
    normalized_difference,
)


def values(masked_array) -> list[float | None]:
    """Flatten a masked array, using None for masked pixels."""
    return [
        None if m else round(float(v), 6)
        for v, m in zip(
            np.ma.getdata(masked_array).ravel(),
            np.ma.getmaskarray(masked_array).ravel(),
            strict=True,
        )
    ]


# --- One test per index formula (values worked out by hand) --------------------
def test_ndvi_formula():
    # (NIR - Red) / (NIR + Red); reflectance = raw / 10000
    # pixel 1: (0.6 - 0.2) / (0.6 + 0.2) =  0.4 / 0.8 =  0.5
    # pixel 2: (0.2 - 0.6) / (0.2 + 0.6) = -0.4 / 0.8 = -0.5
    raw = {"B8": np.array([6000, 2000]), "B4": np.array([2000, 6000])}
    assert values(compute_index_array("NDVI", raw)) == [0.5, -0.5]


def test_ndwi_formula():
    # (Green - NIR) / (Green + NIR)
    # pixel 1: (0.4 - 0.1) / (0.4 + 0.1) =  0.3 / 0.5 =  0.6
    # pixel 2: (0.1 - 0.3) / (0.1 + 0.3) = -0.2 / 0.4 = -0.5
    raw = {"B3": np.array([4000, 1000]), "B8": np.array([1000, 3000])}
    assert values(compute_index_array("NDWI", raw)) == [0.6, -0.5]


def test_ndbi_formula():
    # (SWIR1 - NIR) / (SWIR1 + NIR)
    # pixel 1: (0.3 - 0.1) / (0.3 + 0.1) =  0.2 / 0.4 =  0.5
    # pixel 2: (0.2 - 0.4) / (0.2 + 0.4) = -0.2 / 0.6 = -0.333333
    raw = {"B11": np.array([3000, 2000]), "B8": np.array([1000, 4000])}
    assert values(compute_index_array("NDBI", raw)) == [0.5, -0.333333]


def test_index_key_is_case_insensitive():
    raw = {"B8": np.array([6000]), "B4": np.array([2000])}
    assert values(compute_index_array("ndvi", raw)) == [0.5]


def test_unknown_index_and_missing_band_raise_clear_errors():
    with pytest.raises(ValueError, match="Unknown index"):
        compute_index_array("EVI", {})
    with pytest.raises(ValueError, match=r"needs band\(s\) \['B4'\]"):
        compute_index_array("NDVI", {"B8": np.array([1000])})


# --- Edge cases ----------------------------------------------------------------
def test_zero_denominator_is_masked_not_inf_or_nan():
    raw = {"B8": np.array([0, 5000]), "B4": np.array([0, 1000])}
    result = compute_index_array("NDVI", raw)
    assert values(result) == [None, 0.666667]
    assert np.isfinite(np.ma.getdata(result)).all()


def test_nan_input_is_masked():
    result = normalized_difference(np.array([np.nan, 3.0]), np.array([1.0, 1.0]))
    assert values(result) == [None, 0.5]


def test_masked_input_stays_masked():
    a = np.ma.array([5.0, 3.0], mask=[True, False])
    b = np.array([1.0, 1.0])
    assert values(normalized_difference(a, b)) == [None, 0.5]


def test_shape_mismatch_is_rejected():
    with pytest.raises(ValueError, match="shapes differ"):
        normalized_difference(np.ones((2, 2)), np.ones((3, 3)))
    raw = {"B8": np.ones((2, 2)), "B4": np.ones((2, 2))}
    with pytest.raises(ValueError, match="SCL shape"):
        compute_index_array("NDVI", raw, scl=np.zeros((3, 3), dtype=int))


def test_cloud_mask_classes():
    # 3 shadow, 8/9 cloud, 10 cirrus, 11 snow are unusable; 4 vegetation, 5 bare, 6 water usable
    scl = np.array([3, 4, 5, 6, 8, 9, 10, 11])
    usable = cloud_mask_from_scl(scl).tolist()
    assert usable == [False, True, True, True, False, False, False, False]


def test_cloudy_pixels_are_masked_in_the_index():
    raw = {"B8": np.array([5000, 5000]), "B4": np.array([1000, 1000])}
    result = compute_index_array("NDVI", raw, scl=np.array([4, 9]))
    assert values(result) == [0.666667, None]


def test_without_scl_nothing_is_cloud_masked():
    raw = {"B8": np.array([5000, 5000]), "B4": np.array([1000, 1000])}
    assert values(compute_index_array("NDVI", raw)) == [0.666667, 0.666667]


# --- Statistics ----------------------------------------------------------------
def test_statistics_use_population_std_and_valid_pixels_only():
    data = np.ma.array([1.0, 3.0, 100.0], mask=[False, False, True])
    stats = compute_statistics_array(data)
    assert stats.mean == pytest.approx(2.0)
    assert stats.min == 1.0
    assert stats.max == 3.0
    assert stats.std == pytest.approx(1.0)  # population: sqrt(((1-2)^2 + (3-2)^2) / 2)
    assert (stats.valid_pixels, stats.total_pixels) == (2, 3)
    assert stats.valid_pixel_pct == pytest.approx(66.6667, abs=1e-3)


def test_statistics_respect_the_area_mask():
    data = np.ma.array([[1.0, 2.0], [3.0, 4.0]], mask=[[False, True], [False, False]])
    inside = np.array([[True, True], [False, False]])
    stats = compute_statistics_array(data, aoi_mask=inside)
    assert stats.total_pixels == 2  # pixels outside the area do not count at all
    assert stats.valid_pixels == 1  # the masked pixel inside the area counts as invalid
    assert stats.valid_pixel_pct == 50.0
    assert stats.mean == 1.0


def test_statistics_with_no_valid_pixels():
    data = np.ma.array([1.0, 2.0], mask=[True, True])
    stats = compute_statistics_array(data)
    assert stats.mean is None and stats.std is None
    assert stats.valid_pixels == 0
    assert stats.valid_pixel_pct == 0.0


def test_statistics_area_mask_shape_is_checked():
    with pytest.raises(ValueError, match="AOI mask shape"):
        compute_statistics_array(np.ones((2, 2)), aoi_mask=np.ones((3, 3), dtype=bool))


def test_readme_quick_start_example():
    raw = {
        "B8": np.array([[5000, 3000], [2000, 7000]]),
        "B4": np.array([[1000, 3000], [4000, 1000]]),
    }
    scl = np.array([[4, 5], [4, 9]])
    stats = compute_statistics_array(compute_index_array("NDVI", raw, scl=scl))
    assert stats.as_dict() == {
        "mean": 0.1111,
        "min": -0.3333,
        "max": 0.6667,
        "std": 0.4157,
        "valid_pixels": 3,
        "total_pixels": 4,
        "valid_pixel_pct": 75.0,
    }


def test_statistics_model_rejects_inconsistent_values():
    with pytest.raises(ValidationError):
        Statistics(valid_pixels=5, total_pixels=4, valid_pixel_pct=50)
    with pytest.raises(ValidationError):
        Statistics(valid_pixels=0, total_pixels=4, valid_pixel_pct=0, mean=0.5)
    with pytest.raises(ValidationError):
        Statistics(valid_pixels=1, total_pixels=1, valid_pixel_pct=150, mean=0.5)
