from app.schemas.recommendation import UserPreference


KEYWORD_GROUPS = {
    "rent": ["월세", "전세", "저렴", "싼", "가격", "주거비", "예산"],
    "transport": ["지하철", "역", "교통", "버스", "출퇴근", "대중교통"],
    "park": ["공원", "산책", "녹지", "자연", "운동"],
    "food": ["햄버거", "카페", "음식점", "상권", "맛집", "식당"],
}


def parse_preferences_from_text(message: str) -> UserPreference:
    matched = {
        group: [keyword for keyword in keywords if keyword in message]
        for group, keywords in KEYWORD_GROUPS.items()
    }

    base_weights = {
        "rent": 1.0,
        "transport": 1.0,
        "park": 1.0,
        "food": 1.0,
    }

    for group, keywords in matched.items():
        if keywords:
            base_weights[group] += 1.0

    total = sum(base_weights.values())
    keywords = []
    for group_keywords in matched.values():
        keywords.extend(group_keywords)

    if not keywords:
        keywords = ["기본 추천"]

    return UserPreference(
        rent_weight=round(base_weights["rent"] / total, 4),
        transport_weight=round(base_weights["transport"] / total, 4),
        park_weight=round(base_weights["park"] / total, 4),
        food_weight=round(base_weights["food"] / total, 4),
        keywords=keywords,
    )

