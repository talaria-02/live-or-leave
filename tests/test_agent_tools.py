"""agent/tools.py (ToolExecutor) 단위 테스트 — FakeRepo로 CSV와 분리."""
from __future__ import annotations

from app.agent.tools import ToolExecutor
from app.schemas.tools import (
    CategoryPreference,
    CompareTool,
    FilterClause,
    Importance,
    MetricLevel,
    RecommendTool,
)
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
    # 조용히 사라지면 지도에 구멍이 뚫린다 — 실격 목록에 사유와 함께 보고돼야 함
    assert result["disqualified"] == [
        {"code": "B1", "gu": "강남구", "dong": "B동", "missing": ["대형병원"]}
    ]


def test_recommend_hospital_filter_falls_back_when_no_dong_qualifies(no_hospital_raws):
    """전부 hosp_cnt=0이면 필터를 생략한다(기존 rank() 폴백과 동일) —
    빈 추천보다는 병원 조건만 무시한 추천이 낫다는 기존 설계 유지."""
    executor = ToolExecutor(FakeRepo(no_hospital_raws))
    args = RecommendTool(
        preference=CategoryPreference(
            safety=Importance.VERY_HIGH, convenience=Importance.NONE,
            mobility=Importance.NONE, environment=Importance.NONE),
        require_large_hospital=True, top_n=2,
    )
    result = executor.recommend(args)
    assert len(result["recommendations"]) == 2  # 전 지역 실격 아님
    assert "disqualified" not in result


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
    """HybridFacilityRepository와 동일 인터페이스(count/resolvable)의 테스트 대역."""

    def __init__(self, table: dict[tuple[str, str, str], int]):
        self._table = table

    def count(self, gu: str, dong: str, category: str) -> int:
        return self._table.get((gu, dong, category), 0)

    def resolvable(self, category: str) -> bool:
        return True

    def places_for(self, category: str):
        return None  # CSV 출처 취급 (좌표 없음)


def test_recommend_folds_extra_category_into_weights_and_ranking(monkeypatch, sample_raws):
    monkeypatch.setattr(
        "app.agent.tools.get_hybrid_facility_repository",
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


def test_recommend_applies_required_category_hard_filter_and_reports_disqualified(
    monkeypatch, sample_raws
):
    monkeypatch.setattr(
        "app.agent.tools.get_hybrid_facility_repository",
        lambda: _FakeFacilityRepo({
            ("강남구", "A동", "헬스장"): 1,
            ("서초구", "C동", "헬스장"): 2,
            # B동은 테이블에 없음 → 0으로 취급 → 실격
        }),
    )
    executor = ToolExecutor(FakeRepo(sample_raws))
    args = RecommendTool(
        preference=CategoryPreference(
            safety=Importance.VERY_HIGH, convenience=Importance.NONE,
            mobility=Importance.NONE, environment=Importance.NONE),
        required_filters=[FilterClause(type="category", category="헬스장")], top_n=3,
    )
    result = executor.recommend(args)
    dongs = {r["dong"] for r in result["recommendations"]}
    assert "B동" not in dongs  # 하드필터 통과 못 함
    assert len(result["disqualified"]) == 1
    assert result["disqualified"][0]["dong"] == "B동"
    assert result["disqualified"][0]["missing"] == ["헬스장"]


def test_recommend_without_required_categories_omits_disqualified_key(sample_raws):
    executor = ToolExecutor(FakeRepo(sample_raws))
    args = RecommendTool(
        preference=CategoryPreference(
            safety=Importance.VERY_HIGH, convenience=Importance.NONE,
            mobility=Importance.NONE, environment=Importance.NONE),
        top_n=1,
    )
    result = executor.recommend(args)
    assert "disqualified" not in result


# ---------- gu 필터 (행정구역 포함/제외) — API 호출 없이 로컬 데이터만 ----------
# sample_raws: A동·B동=강남구, C동=서초구

def test_gu_filter_includes_only_matching_gu(sample_raws):
    executor = ToolExecutor(FakeRepo(sample_raws))
    result = executor.recommend(RecommendTool(
        preference=CategoryPreference(
            safety=Importance.NONE, convenience=Importance.NONE,
            mobility=Importance.NONE, environment=Importance.NONE),
        required_filters=[FilterClause(type="gu", gu=["강남구"])], top_n=3,
    ))
    dongs = {r["dong"] for r in result["recommendations"]}
    assert dongs == {"A동", "B동"}
    assert result["disqualified"][0]["dong"] == "C동"
    assert "강남구 안에 없음" in result["disqualified"][0]["missing"][0]


def test_gu_filter_exclude_flips_the_match(sample_raws):
    executor = ToolExecutor(FakeRepo(sample_raws))
    result = executor.recommend(RecommendTool(
        preference=CategoryPreference(
            safety=Importance.NONE, convenience=Importance.NONE,
            mobility=Importance.NONE, environment=Importance.NONE),
        required_filters=[FilterClause(type="gu", gu=["강남구"], exclude=True)], top_n=3,
    ))
    dongs = {r["dong"] for r in result["recommendations"]}
    assert dongs == {"C동"}


def test_gu_filter_resolves_known_alias(sample_raws):
    """'강남3구' 같은 통칭은 GU_ALIASES로 해석된다 — LLM이 실제 구 이름을
    몰라도 안전하게 동작 (서초구는 alias 목록에 포함, sample_raws엔 서초구=C동)."""
    executor = ToolExecutor(FakeRepo(sample_raws))
    result = executor.recommend(RecommendTool(
        preference=CategoryPreference(
            safety=Importance.NONE, convenience=Importance.NONE,
            mobility=Importance.NONE, environment=Importance.NONE),
        required_filters=[FilterClause(type="gu", gu=["강남3구"])], top_n=3,
    ))
    dongs = {r["dong"] for r in result["recommendations"]}
    assert dongs == {"A동", "B동", "C동"}  # 강남3구=강남/서초/송파 → 셋 다 해당


# ---------- metric 필터 (지표 임계값) — API 호출 없이 로컬 데이터만 ----------
# crime_rate: A=10(최저·가장 안전), C=20, B=30(최고·가장 위험)

def test_metric_filter_strict_keeps_only_top_tier(sample_raws):
    executor = ToolExecutor(FakeRepo(sample_raws))
    result = executor.recommend(RecommendTool(
        preference=CategoryPreference(
            safety=Importance.NONE, convenience=Importance.NONE,
            mobility=Importance.NONE, environment=Importance.NONE),
        required_filters=[FilterClause(type="metric", field="crime_rate", level=MetricLevel.STRICT)],
        top_n=3,
    ))
    dongs = {r["dong"] for r in result["recommendations"]}
    assert dongs == {"A동"}  # 상위 30% 안 = 가장 안전한 1곳만


def test_metric_filter_moderate_is_more_lenient_than_strict(sample_raws):
    executor = ToolExecutor(FakeRepo(sample_raws))
    result = executor.recommend(RecommendTool(
        preference=CategoryPreference(
            safety=Importance.NONE, convenience=Importance.NONE,
            mobility=Importance.NONE, environment=Importance.NONE),
        required_filters=[FilterClause(type="metric", field="crime_rate", level=MetricLevel.MODERATE)],
        top_n=3,
    ))
    dongs = {r["dong"] for r in result["recommendations"]}
    assert dongs == {"A동", "C동"}  # 상위 50% 안 = 2곳


def test_metric_filter_higher_is_better_field(sample_raws):
    """park_cnt는 클수록 좋은 지표 — invert 방향이 crime_rate와 반대로 적용돼야 한다.
    A=10(최다), C=6, B=3(최소)."""
    executor = ToolExecutor(FakeRepo(sample_raws))
    result = executor.recommend(RecommendTool(
        preference=CategoryPreference(
            safety=Importance.NONE, convenience=Importance.NONE,
            mobility=Importance.NONE, environment=Importance.NONE),
        required_filters=[FilterClause(type="metric", field="park_cnt", level=MetricLevel.STRICT)],
        top_n=3,
    ))
    dongs = {r["dong"] for r in result["recommendations"]}
    assert dongs == {"A동"}  # 공원 가장 많은 곳(=상위 30%)만 통과
