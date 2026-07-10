"""agent/tools.py (ToolExecutor) 단위 테스트 — FakeRepo로 CSV와 분리."""
from __future__ import annotations

from app.agent.tools import ToolExecutor
from app.schemas.tools import CategoryPreference, CompareTool, Importance, RecommendTool
from tests.conftest import FakeRepo


def test_recommend_returns_normalized_weights_and_ranked_recommendations(sample_raws):
    executor = ToolExecutor(FakeRepo(sample_raws))
    args = RecommendTool(
        preference=CategoryPreference(
            safety=Importance.VERY_HIGH, convenience=Importance.NONE,
            mobility=Importance.NONE, environment=Importance.NONE),
        top_n=2,
    )
    result = executor.recommend(args)
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-9
    assert len(result["recommendations"]) == 2
    assert result["recommendations"][0]["dong"] == "A동"  # safety 최고점


def test_recommend_applies_hospital_filter(sample_raws):
    executor = ToolExecutor(FakeRepo(sample_raws))
    args = RecommendTool(
        preference=CategoryPreference(
            safety=Importance.NONE, convenience=Importance.VERY_HIGH,
            mobility=Importance.NONE, environment=Importance.NONE),
        require_large_hospital=True, top_n=3,
    )
    result = executor.recommend(args)
    dongs = {r["dong"] for r in result["recommendations"]}
    assert "B동" not in dongs  # hosp_cnt=0인 B동은 제외되어야 함


def test_compare_found(sample_raws):
    executor = ToolExecutor(FakeRepo(sample_raws))
    result = executor.compare(CompareTool(gu_a="A동", gu_b="C동"))
    assert result["a"]["dong"] == "A동"
    assert result["b"]["dong"] == "C동"


def test_compare_missing_returns_error(sample_raws):
    executor = ToolExecutor(FakeRepo(sample_raws))
    result = executor.compare(CompareTool(gu_a="A동", gu_b="존재하지않는동"))
    assert result == {"error": "존재하지 않는 행정동"}


class _FakeFacilityRepo:
    def __init__(self, table: dict[tuple[str, str, str], int]):
        self._table = table

    def count(self, gu: str, dong: str, category: str) -> int:
        return self._table.get((gu, dong, category), 0)


def test_recommend_folds_extra_category_into_weights_and_ranking(monkeypatch, sample_raws):
    monkeypatch.setattr(
        "app.agent.tools.get_facility_repository",
        lambda: _FakeFacilityRepo({("강남구", "A동", "버거"): 5, ("서초구", "C동", "버거"): 1}),
    )
    executor = ToolExecutor(FakeRepo(sample_raws))
    args = RecommendTool(
        preference=CategoryPreference(
            safety=Importance.NONE, convenience=Importance.NONE,
            mobility=Importance.NONE, environment=Importance.NONE),
        extra_categories=["버거"], top_n=3,
    )
    result = executor.recommend(args)
    assert "버거" in result["weights"]
    top = result["recommendations"][0]
    assert top["dong"] == "A동"  # 버거 5개로 최다
    assert top["extra_facilities"] == {"버거": 5}


def test_recommend_without_extra_categories_omits_extra_facilities_key(sample_raws):
    executor = ToolExecutor(FakeRepo(sample_raws))
    args = RecommendTool(
        preference=CategoryPreference(
            safety=Importance.VERY_HIGH, convenience=Importance.NONE,
            mobility=Importance.NONE, environment=Importance.NONE),
        top_n=1,
    )
    result = executor.recommend(args)
    assert "extra_facilities" not in result["recommendations"][0]
