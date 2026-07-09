from fastapi import APIRouter

from app.agents.recommendation_agent import RecommendationAgent
from app.schemas.recommendation import RecommendRequest, RecommendResponse

router = APIRouter(prefix="/recommend", tags=["recommendation"])


@router.post("/sync", response_model=RecommendResponse)
def recommend_sync(request: RecommendRequest) -> RecommendResponse:
    return RecommendationAgent().run(request.message)

