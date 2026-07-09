from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field


class RecommendationRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description="사용자의 자연어 주거/라이프스타일 조건",
    )


class ScoreBreakdown(BaseModel):
    running_score: float = Field(..., ge=0, le=100)
    park_score: float = Field(..., ge=0, le=100)
    food_score: float = Field(..., ge=0, le=100)
    lifestyle_score: float = Field(..., ge=0, le=100)


class RecommendationItem(BaseModel):
    rank: int = Field(..., ge=1)
    region_name: str
    final_score: float = Field(..., ge=0, le=100)
    grade: Literal["green", "orange", "red"]
    reason: str = Field(..., min_length=1)
    score_breakdown: ScoreBreakdown
    matched_preferences: List[str]


class RecommendationResponse(BaseModel):
    query: str
    matched_preferences: List[str]
    weights: Dict[str, float]
    recommendations: List[RecommendationItem]


class ErrorResponse(BaseModel):
    detail: str
