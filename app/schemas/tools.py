"""
에이전트 도구 스키마 — LLM이 채우는 구조화된 입출력 정의.

핵심 설계 (앞선 논의 반영):
  - LLM은 '숫자'를 직접 만들지 않는다. 4단계 라벨(중요도)만 고르게 하고,
    라벨→가중치 매핑은 결정론적 코드가 수행한다. (일관성 확보)
  - 가중치 합=1 정규화, 파싱 실패 시 폴백은 서비스 계층 책임.
"""
from __future__ import annotations

from enum import Enum

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
        description="'버거집', '헬스장' 같이 4개 카테고리 밖에서 언급된 업종 — "
        "실제 존재하는 상권업종소분류명 문자열로만 채운다 (자유 생성 금지)",
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
    top_n: int = Field(default=3, ge=1, le=25)


class CompareTool(BaseModel):
    """도구: 두 자치구의 지표 비교."""

    gu_a: str
    gu_b: str


class ClarifyTool(BaseModel):
    """도구: 사용자에게 되묻기."""

    question: str
