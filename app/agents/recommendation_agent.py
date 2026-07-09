from app.schemas.recommendation import RecommendResponse
from app.tools.recommendation_tools import (
    load_region_features,
    parse_user_preferences,
    score_regions,
)


class RecommendationAgent:
    """Day2 ReAct-style loop with rule-based tools.

    Day3 can replace parse_user_preferences with an LLM structured-output tool
    without changing the API response contract.
    """

    def run(self, message: str) -> RecommendResponse:
        preference = parse_user_preferences(message)
        regions = load_region_features()
        recommendations = score_regions(regions, preference)

        district_names = ", ".join(region.district for region in recommendations)
        summary = (
            f"입력 조건({', '.join(preference.keywords)}) 기준으로 "
            f"{district_names} 순으로 추천됩니다."
        )

        return RecommendResponse(
            preferences=preference,
            recommendations=recommendations,
            summary=summary,
        )

