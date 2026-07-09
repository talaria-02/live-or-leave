from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCORE_PATH = PROJECT_ROOT / "processed" / "region_scores.csv"

DEFAULT_WEIGHTS = {
    "running_score": 0.35,
    "park_score": 0.30,
    "food_score": 0.25,
    "lifestyle_score": 0.10,
}

KEYWORD_WEIGHT_BOOST = {
    "running_score": 0.15,
    "park_score": 0.12,
    "food_score": 0.12,
    "lifestyle_score": 0.08,
}

KEYWORD_GROUPS = {
    "running": ["러닝", "달리기", "조깅", "운동", "산책"],
    "park": ["공원", "녹지", "한강", "산책로"],
    "food": ["햄버거", "버거", "맥도날드", "롯데리아", "버거킹", "맘스터치", "KFC"],
    "lifestyle": ["20대", "대학생", "사회초년생", "카페", "놀거리", "상권"],
}

PREFERENCE_TO_SCORE_COLUMN = {
    "running": "running_score",
    "park": "park_score",
    "food": "food_score",
    "lifestyle": "lifestyle_score",
}

REQUIRED_SCORE_COLUMNS = [
    "region_name",
    "park_score",
    "food_score",
    "running_score",
    "lifestyle_score",
    "final_score",
    "grade",
]

SCORE_BREAKDOWN_COLUMNS = [
    "running_score",
    "park_score",
    "food_score",
    "lifestyle_score",
]


def load_region_scores(path: str | Path = DEFAULT_SCORE_PATH) -> pd.DataFrame:
    """
    region_scores.csv를 로드하고 필수 컬럼을 검증한다.
    """
    path = Path(path)
    scores = pd.read_csv(path)
    missing_columns = [
        column for column in REQUIRED_SCORE_COLUMNS if column not in scores.columns
    ]
    if missing_columns:
        raise ValueError(
            "Missing required columns in region_scores.csv: "
            + ", ".join(missing_columns)
        )

    for column in SCORE_BREAKDOWN_COLUMNS:
        scores[column] = pd.to_numeric(scores[column], errors="coerce")
        if scores[column].isna().any():
            median_value = scores[column].median()
            fill_value = 0 if pd.isna(median_value) else median_value
            scores[column] = scores[column].fillna(fill_value)

    return scores


def extract_preferences(query: str) -> list[str]:
    """
    query에서 규칙 기반으로 preference category를 추출한다.
    반환 예: ["running", "park", "food", "lifestyle"]
    """
    normalized_query = query.lower()
    matched_preferences = []
    for preference, keywords in KEYWORD_GROUPS.items():
        if any(keyword.lower() in normalized_query for keyword in keywords):
            matched_preferences.append(preference)
    return matched_preferences


def build_weights(matched_preferences: list[str]) -> dict[str, float]:
    """
    기본 가중치에 preference boost를 적용한 뒤 합이 1이 되도록 normalize한다.
    """
    weights = DEFAULT_WEIGHTS.copy()
    for preference in set(matched_preferences):
        score_column = PREFERENCE_TO_SCORE_COLUMN.get(preference)
        if score_column is None:
            continue
        weights[score_column] += KEYWORD_WEIGHT_BOOST[score_column]

    total_weight = sum(weights.values())
    if total_weight == 0:
        raise ValueError("Total recommendation weight cannot be zero")

    return {
        score_column: weight / total_weight
        for score_column, weight in weights.items()
    }


def calculate_query_scores(
    df: pd.DataFrame, weights: dict[str, float]
) -> pd.DataFrame:
    """
    query 기반 가중치로 final_score를 재계산한다.
    """
    scored = df.copy()

    # 사용자 query마다 관심 조건이 달라질 수 있으므로 저장된 final_score 대신 재계산한다.
    scored["final_score"] = (
        weights["running_score"] * scored["running_score"]
        + weights["park_score"] * scored["park_score"]
        + weights["food_score"] * scored["food_score"]
        + weights["lifestyle_score"] * scored["lifestyle_score"]
    ).round(2)
    scored["grade"] = scored["final_score"].map(assign_grade)
    return scored.sort_values("final_score", ascending=False)


def assign_grade(score: float) -> str:
    """
    final_score에 따라 green/orange/red를 반환한다.
    """
    if score >= 70:
        return "green"
    if score >= 40:
        return "orange"
    return "red"


def _score_level(score: float) -> str:
    if score >= 80:
        return "매우 높습니다"
    if score >= 65:
        return "높은 편입니다"
    if score >= 50:
        return "보통 수준입니다"
    return "낮은 편입니다"


def generate_reason(row: pd.Series, matched_preferences: list[str]) -> str:
    """
    실제 점수에 기반한 추천 이유를 생성한다.
    """
    score_labels = {
        "running_score": "러닝 친화도",
        "park_score": "공원 관련 지표",
        "food_score": "햄버거/외식 인프라",
        "lifestyle_score": "20대 생활 인프라",
    }
    ordered_scores = sorted(
        SCORE_BREAKDOWN_COLUMNS,
        key=lambda column: float(row[column]),
        reverse=True,
    )

    main_parts = []
    for column in ordered_scores[:2]:
        score = float(row[column])
        main_parts.append(f"{score_labels[column]}가 상대적으로 {_score_level(score)}")

    weaker_columns = [
        column for column in ordered_scores[-2:] if float(row[column]) < 50
    ]
    weaker_sentence = ""
    if weaker_columns:
        weakest_column = weaker_columns[-1]
        weaker_sentence = (
            f" 다만 {score_labels[weakest_column]}는 데이터 기준 낮은 편입니다."
        )

    matched_text = ", ".join(matched_preferences) if matched_preferences else "기본 조건"
    return (
        f"{row['region_name']}는 데이터 기준 {', '.join(main_parts)}. "
        f"감지된 조건({matched_text})을 기준으로 산정했습니다."
        f"{weaker_sentence}"
    )


def _build_recommendation_item(
    rank: int, row: pd.Series, matched_preferences: list[str]
) -> dict:
    return {
        "rank": rank,
        "region_name": row["region_name"],
        "final_score": round(float(row["final_score"]), 2),
        "grade": row["grade"],
        "reason": generate_reason(row, matched_preferences),
        "score_breakdown": {
            column: round(float(row[column]), 2)
            for column in SCORE_BREAKDOWN_COLUMNS
        },
        "matched_preferences": matched_preferences,
    }


def recommend_regions(
    query: str,
    score_path: str | Path = DEFAULT_SCORE_PATH,
    top_k: int = 3,
) -> dict:
    """
    사용자 query를 받아 추천 결과 Top K를 반환한다.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    if top_k <= 0:
        raise ValueError("top_k must be greater than zero")

    scores = load_region_scores(score_path)
    matched_preferences = extract_preferences(query)
    weights = build_weights(matched_preferences)
    query_scores = calculate_query_scores(scores, weights)

    recommendations = [
        _build_recommendation_item(index + 1, row, matched_preferences)
        for index, (_, row) in enumerate(query_scores.head(top_k).iterrows())
    ]

    return {
        "query": query,
        "matched_preferences": matched_preferences,
        "weights": weights,
        "recommendations": recommendations,
    }


def _validate_demo_result(result: dict) -> None:
    recommendations = result["recommendations"]
    required_recommendation_fields = {
        "rank",
        "region_name",
        "final_score",
        "grade",
        "reason",
        "score_breakdown",
        "matched_preferences",
    }

    assert len(recommendations) == 3
    assert set(result["matched_preferences"]) == {
        "running",
        "park",
        "food",
        "lifestyle",
    }

    previous_score = 101.0
    for recommendation in recommendations:
        assert required_recommendation_fields <= set(recommendation)
        assert 0 <= recommendation["final_score"] <= 100
        assert recommendation["grade"] in {"green", "orange", "red"}
        assert recommendation["reason"]
        assert recommendation["final_score"] <= previous_score
        previous_score = recommendation["final_score"]


if __name__ == "__main__":
    demo_query = (
        "나는 러닝을 좋아하는 20대 남자야. "
        "근처에 공원과 햄버거집이 많은 동네를 추천해줘."
    )
    demo_result = recommend_regions(demo_query)
    _validate_demo_result(demo_result)
    print(demo_result)
