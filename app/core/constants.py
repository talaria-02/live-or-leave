GREEN_THRESHOLD = 0.7
ORANGE_THRESHOLD = 0.3
TOP_RECOMMENDATION_COUNT = 3


def score_to_color(score: float) -> str:
    if score >= GREEN_THRESHOLD:
        return "green"
    if score >= ORANGE_THRESHOLD:
        return "orange"
    return "red"

