from __future__ import annotations

from typing import Dict

from fastapi import FastAPI, HTTPException

from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.services.recommendation_service import recommend_regions


def create_app() -> FastAPI:
    app = FastAPI(
        title="SalraeMallae Recommendation API",
        description="서울시 자치구 기반 개인화 주거 지역 추천 MVP API",
        version="0.1.0",
    )

    @app.get("/")
    def health_check() -> Dict[str, str]:
        return {"status": "ok", "message": "Recommendation API is running"}

    @app.post("/recommend", response_model=RecommendationResponse)
    def recommend(request: RecommendationRequest) -> RecommendationResponse:
        try:
            return recommend_regions(query=request.query, top_k=3)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"필요한 데이터 파일을 찾을 수 없습니다: {str(exc)}",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"추천 처리 중 오류가 발생했습니다: {str(exc)}",
            ) from exc

    return app


app = create_app()
