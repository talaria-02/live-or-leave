from app.repositories.region_repository import RegionRepository
from app.schemas.recommendation import RegionFeature, RegionScore, UserPreference
from app.services.preference_service import parse_preferences_from_text
from app.services.recommendation_service import score_regions as score_region_features


def parse_user_preferences(message: str) -> UserPreference:
    return parse_preferences_from_text(message)


def load_region_features() -> list[RegionFeature]:
    return RegionRepository().list_regions()


def score_regions(
    regions: list[RegionFeature],
    preference: UserPreference,
) -> list[RegionScore]:
    return score_region_features(regions, preference)

