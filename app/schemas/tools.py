"""
에이전트 도구 스키마 — LLM이 채우는 구조화된 입출력 정의.

핵심 설계 (앞선 논의 반영):
  - LLM은 '숫자'를 직접 만들지 않는다. 4단계 라벨(중요도)만 고르게 하고,
    라벨→가중치 매핑은 결정론적 코드가 수행한다. (일관성 확보)
  - 가중치 합=1 정규화, 파싱 실패 시 폴백은 서비스 계층 책임.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Importance(str, Enum):
    """카테고리 중요도 라벨. LLM은 이 중 하나만 선택한다."""

    VERY_HIGH = "very_high"   # 매우 중요
    HIGH = "high"             # 중요
    MEDIUM = "medium"         # 보통
    NONE = "none"             # 관계없음


# 라벨 → 고정 점수 매핑 (코드가 소유, LLM이 건드리지 않음)
IMPORTANCE_SCORE: dict[Importance, float] = {
    Importance.VERY_HIGH: 1.0,
    Importance.HIGH: 0.6,
    Importance.MEDIUM: 0.3,
    Importance.NONE: 0.0,
}


class MetricLevel(str, Enum):
    """metric 필터 전용 라벨 — Importance(중요도)와 의미가 달라 별도 정의한다.
    '이 지표가 얼마나 좋아야 하는가'를 백분위 컷오프로 코드가 해석한다
    (LLM은 라벨만 고르고 숫자는 안 만든다는 원칙 그대로)."""

    MODERATE = "moderate"        # 방향성 기준 상위 50% 안
    STRICT = "strict"            # 상위 30% 안
    VERY_STRICT = "very_strict"  # 상위 15% 안


class FilterClause(BaseModel):
    """필수 요구사항 1건 — type에 따라 아래 필드 중 해당하는 것만 채워진다.

    거리(near)·업종(category)·행정구역(gu)·지표(metric), 4종류를 하나의
    목록(ParsedIntent.required_filters)으로 표현한다. 새 필터 종류가 생겨도
    여기 타입 하나 추가 + tools.py에 실행 함수 하나 추가로 끝나게 하기 위함
    (에이전트 흐름·LLM 호출 횟수는 그대로)."""

    type: Literal["category", "near", "gu", "metric"]

    # type="category" — 업종 존재 필터
    category: str | None = Field(
        default=None,
        description="'헬스장', '약국'처럼 존재해야 하는 업종·시설명. 상권업종소분류명이나 "
        "Kakao 표준 카테고리명이 우선이지만, 없으면 열린 키워드도 허용.",
    )

    # type="near" — 랜드마크 거리 필터
    place: str | None = Field(default=None, description="'서울대', '강남역' 등 기준 장소명")
    radius_km: float | None = Field(
        default=None, description="반경(km). 생략하면 기본값(3km) 사용"
    )
    group: str | None = Field(
        default=None,
        description="같은 group명을 가진 near 조건끼리는 OR(하나만 만족해도 통과), "
        "group이 없거나 서로 다르면 AND. '강남역이나 홍대입구역 중 아무데나' 같은 "
        "경우에만 채우고, 보통은 비워둔다.",
    )

    # type="gu" — 행정구역 포함/제외
    gu: list[str] | None = Field(
        default=None, description="자치구명 목록(예: ['강남구']) 또는 '강남3구' 같은 통칭"
    )
    exclude: bool = Field(
        default=False, description="True면 이 구들을 제외(그 외 지역만), False면 이 구들 안에서만"
    )

    # type="metric" — 지표 임계값
    field: str | None = Field(
        default=None,
        description="crime_rate/cctv_cnt/conv_cnt/mart_cnt/hosp_cnt/bus_cnt/subway_access/"
        "park_cnt 중 하나만 (그 외 문자열 생성 금지)",
    )
    level: MetricLevel | None = Field(
        default=None, description="이 지표가 좋은 쪽으로 얼마나 엄격해야 하는지"
    )


class CategoryPreference(BaseModel):
    """입구 LLM의 출력 스키마 — 카테고리별 중요도 라벨."""

    safety: Importance = Field(..., description="안전(범죄 적고 CCTV 많음) 중요도")
    convenience: Importance = Field(..., description="편의(편의점·마트·병원) 중요도")
    mobility: Importance = Field(..., description="이동(지하철·버스 접근성) 중요도")
    environment: Importance = Field(..., description="환경(공원·녹지) 중요도")


class ParsedIntent(BaseModel):
    """입구 LLM 전체 출력 — 선호 + 명시적 필수조건 + 되묻기 여부."""

    preference: CategoryPreference
    require_large_hospital: bool = Field(
        default=False, description="'대형병원 있어야' 류의 필수조건 감지 시 True"
    )
    extra_categories: list[str] = Field(
        default_factory=list,
        description="'버거집', '헬스장' 같이 4개 카테고리 밖에서 '선택'으로 언급된 업종 — "
        "점수에 반영(가중치 참여). 실제 존재하는 상권업종소분류명 문자열로만 채운다 (자유 생성 금지)",
    )
    required_filters: list[FilterClause] = Field(
        default_factory=list,
        description="'필수'로 언급된 조건 전부 — 점수화가 아니라 하드 필터(전부 AND, "
        "단 같은 group의 near끼리는 OR). 업종 존재/거리/행정구역/지표 임계값 4종.",
    )
    needs_clarification: bool = Field(
        default=False, description="성향이 모호해 되물어야 하면 True"
    )
    clarify_question: str | None = Field(
        default=None, description="되물을 질문 (needs_clarification=True일 때)"
    )


# ---- 도구(tool) 입출력 스키마 : ReAct 루프에서 LLM이 호출 ----

class RecommendTool(BaseModel):
    """도구: 선호를 받아 상위 N개 자치구 추천."""

    preference: CategoryPreference
    require_large_hospital: bool = False
    extra_categories: list[str] = Field(default_factory=list)
    required_filters: list[FilterClause] = Field(default_factory=list)
    top_n: int = Field(default=3, ge=1, le=500)


class CompareTool(BaseModel):
    """도구: 두 자치구의 지표 비교."""

    gu_a: str
    gu_b: str


class ClarifyTool(BaseModel):
    """도구: 사용자에게 되묻기."""

    question: str
