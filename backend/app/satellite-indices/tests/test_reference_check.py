import json

import pytest

from satellite_indices import reference_check as rc
from satellite_indices.aoi import read_aoi
from satellite_indices.indices import Statistics

SQUARE_GEOJSON = {
    "type": "Polygon",
    "coordinates": [[[30.98, 30.76], [31.0, 30.76], [31.0, 30.78], [30.98, 30.78], [30.98, 30.76]]],
}


def test_hand_reference_passes():
    assert rc.check_against_hand_reference() == []


def test_hand_reference_numbers_are_internally_consistent():
    expected = rc.HAND_REFERENCE.expected
    present = [v for row in rc.HAND_REFERENCE.expected_index for v in row if v is not None]
    assert expected.mean == pytest.approx(sum(present) / len(present), abs=1e-5)
    assert expected.min == pytest.approx(min(present), abs=1e-5)
    assert expected.max == pytest.approx(max(present), abs=1e-5)
    assert expected.valid_pixel_pct == 100 * len(present) / 4


def test_compare_passes_within_tolerance():
    ours = {"mean": 0.1111, "min": -0.3333, "max": 0.6667, "std": 0.4157, "valid_pixel_pct": 75.0}
    assert rc.compare_to_reference(ours, rc.HAND_REFERENCE.expected, tol=0.01) == []


def test_compare_reports_each_difference():
    ours = {"mean": 0.30, "min": -0.3333, "max": 0.6667, "valid_pixel_pct": 40.0}
    problems = rc.compare_to_reference(ours, rc.HAND_REFERENCE.expected, tol=0.01)
    assert len(problems) == 3  # mean, std (missing), valid_pixel_pct
    assert any(p.startswith("mean:") for p in problems)
    assert any(p.startswith("std: ours is missing") for p in problems)
    assert any(p.startswith("valid_pixel_pct:") for p in problems)


def test_compare_skips_keys_the_reference_does_not_specify():
    reference = rc.ReferenceStats(mean=0.5)
    assert rc.compare_to_reference({"mean": 0.505, "min": 99}, reference, tol=0.01) == []


def test_compare_accepts_statistics_objects_and_checks_tolerance_edges():
    ours = Statistics(
        mean=0.52, valid_pixels=3, total_pixels=4, valid_pixel_pct=75, min=0, max=1, std=0.1
    )
    assert rc.compare_to_reference(ours, {"mean": 0.5}, tol=0.01) != []
    assert rc.compare_to_reference(ours, {"mean": 0.5}, tol=0.05) == []


def test_negative_tolerance_is_rejected():
    with pytest.raises(ValueError):
        rc.compare_to_reference({}, {}, tol=-1)


def test_a_wrong_pipeline_would_be_caught():
    """If someone forgot the cloud mask, the valid percentage would be 100, not 75."""
    wrong = {"mean": 0.3333, "min": -0.3333, "max": 0.75, "std": 0.45, "valid_pixel_pct": 100.0}
    problems = rc.compare_to_reference(wrong, rc.HAND_REFERENCE.expected)
    assert any("valid_pixel_pct" in p for p in problems)


# --- Code Editor script --------------------------------------------------------
def test_code_editor_script_contents():
    image_id = "20260920T083611_20260920T084512_T36RUU"
    script = rc.code_editor_script(SQUARE_GEOJSON, image_id, "ndwi")
    assert f'ee.Image("COPERNICUS/S2_SR_HARMONIZED/{image_id}")' in script
    assert 'var bands = ["B3", "B8"];' in script
    assert "var scale = 10;" in script
    assert "scl.neq(3).and(scl.neq(8)).and(scl.neq(9)).and(scl.neq(10)).and(scl.neq(11))" in script
    assert "normalizedDifference" in script
    assert "valid_pixel_pct" in script


def test_code_editor_script_uses_coarsest_scale_for_ndbi():
    script = rc.code_editor_script(SQUARE_GEOJSON, "X1", "NDBI")
    assert "var scale = 20;" in script


def test_code_editor_script_keeps_full_image_ids():
    script = rc.code_editor_script(SQUARE_GEOJSON, "COPERNICUS/S2_SR_HARMONIZED/ABC")
    assert 'ee.Image("COPERNICUS/S2_SR_HARMONIZED/ABC")' in script


@pytest.mark.parametrize("bad_id", ['x"); evil(); ("', "a b", "", "id;drop"])
def test_code_editor_script_rejects_unsafe_image_ids(bad_id):
    with pytest.raises(ValueError, match="unexpected characters"):
        rc.code_editor_script(SQUARE_GEOJSON, bad_id)


def test_code_editor_script_rejects_unknown_index():
    with pytest.raises(ValueError, match="Unknown index"):
        rc.code_editor_script(SQUARE_GEOJSON, "X1", "EVI")


# --- Command line --------------------------------------------------------------
def test_cli_hand_reference(capsys):
    assert rc.main(["--check-hand-reference"]) == 0
    assert "Hand reference: PASS" in capsys.readouterr().out


def test_cli_prints_script_for_the_bundled_area(capsys):
    assert rc.main(["--print-code-editor-script", "--image-id", "ABC123"]) == 0
    out = capsys.readouterr().out
    assert "ABC123" in out and "ee.Geometry" in out
    assert read_aoi(rc._default_aoi_path()).area_km2 > 0


def test_cli_compare_files(tmp_path, capsys):
    ours, ref = tmp_path / "ours.json", tmp_path / "ref.json"
    ours.write_text(json.dumps({"mean": 0.5}))
    ref.write_text(json.dumps({"mean": 0.9}))
    assert rc.main(["--compare", str(ours), str(ref)]) == 1
    assert "Comparison: FAIL" in capsys.readouterr().out
    ref.write_text(json.dumps({"mean": 0.505}))
    assert rc.main(["--compare", str(ours), str(ref)]) == 0


def test_cli_without_arguments_prints_help(capsys):
    assert rc.main([]) == 2
    assert "usage" in capsys.readouterr().out.lower()
