import pytest
from pydantic import ValidationError

from ai_service.app.agent.schemas import AnalysisPlan


def test_indices_plan_is_valid():
    plan = AnalysisPlan(
        analysis_type="indices",
        indices=["NDVI"],
        start_date="2025-06-01",
        end_date="2025-06-30",
    )

    assert plan.analysis_type == "indices"
    assert plan.indices == ["NDVI"]


def test_land_cover_plan_allows_empty_indices():
    plan = AnalysisPlan(
        analysis_type="land_cover",
        indices=[],
        start_date="2025-06-01",
        end_date="2025-06-30",
    )

    assert plan.analysis_type == "land_cover"
    assert plan.indices == []


def test_both_plan_requires_indices():
    plan = AnalysisPlan(
        analysis_type="both",
        indices=["NDVI"],
        start_date="2025-06-01",
        end_date="2025-06-30",
    )

    assert plan.analysis_type == "both"
    assert "NDVI" in plan.indices


def test_indices_plan_rejects_empty_indices():
    with pytest.raises(ValidationError):
        AnalysisPlan(
            analysis_type="indices",
            indices=[],
            start_date="2025-06-01",
            end_date="2025-06-30",
        )


def test_both_plan_rejects_empty_indices():
    with pytest.raises(ValidationError):
        AnalysisPlan(
            analysis_type="both",
            indices=[],
            start_date="2025-06-01",
            end_date="2025-06-30",
        )


def test_land_cover_rejects_indices():
    with pytest.raises(ValidationError):
        AnalysisPlan(
            analysis_type="land_cover",
            indices=["NDVI"],
            start_date="2025-06-01",
            end_date="2025-06-30",
        )


def test_plan_rejects_reversed_dates():
    with pytest.raises(ValidationError):
        AnalysisPlan(
            analysis_type="indices",
            indices=["NDVI"],
            start_date="2025-06-30",
            end_date="2025-06-01",
        )
