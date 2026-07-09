from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_PATH = PROJECT_ROOT / "processed" / "region_features.csv"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "processed" / "region_scores.csv"

REQUIRED_FEATURE_COLUMNS = [
    "region_name",
    "park_count",
    "park_area_per_person",
    "park_ratio",
    "large_park_count",
    "food_count",
    "cafe_count",
    "hamburger_count",
    "fastfood_count",
    "running_friendly_score",
    "commercial_area_score",
]

REQUIRED_SCORE_COLUMNS = [
    "region_name",
    "park_score",
    "food_score",
    "running_score",
    "lifestyle_score",
    "final_score",
    "grade",
    "park_count_score",
    "park_area_per_person_score",
    "park_ratio_score",
    "large_park_count_score",
    "food_count_score",
    "cafe_count_score",
    "hamburger_count_score",
    "fastfood_count_score",
    "commercial_area_score_norm",
]

SCORE_COLUMNS = [
    "park_score",
    "food_score",
    "running_score",
    "lifestyle_score",
    "final_score",
    "park_count_score",
    "park_area_per_person_score",
    "park_ratio_score",
    "large_park_count_score",
    "food_count_score",
    "cafe_count_score",
    "hamburger_count_score",
    "fastfood_count_score",
    "commercial_area_score_norm",
]


def minmax_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """
    입력 Series를 0~100 범위로 min-max scaling한다.
    higher_is_better=False인 경우 역방향 점수화한다.
    min == max인 경우 50점으로 처리한다.
    결측값은 중앙값으로 대체한다.
    """
    numeric = pd.to_numeric(series, errors="coerce")
    median = numeric.median()
    if pd.isna(median):
        numeric = numeric.fillna(0)
    else:
        numeric = numeric.fillna(median)

    min_value = numeric.min()
    max_value = numeric.max()
    if pd.isna(min_value) or pd.isna(max_value) or min_value == max_value:
        return pd.Series(np.full(len(numeric), 50.0), index=series.index)

    score = (numeric - min_value) / (max_value - min_value) * 100
    if not higher_is_better:
        score = 100 - score
    return score.round(2)


def validate_required_columns(df: pd.DataFrame, required_columns: list[str]) -> None:
    """
    region_features.csv에 필요한 컬럼이 모두 있는지 확인한다.
    없으면 명확한 ValueError를 발생시킨다.
    """
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Missing required columns in region_features.csv: "
            + ", ".join(missing_columns)
        )


def assign_grade(final_score: float) -> str:
    """
    final_score에 따라 green/orange/red 등급을 반환한다.
    """
    if final_score >= 70:
        return "green"
    if final_score >= 40:
        return "orange"
    return "red"


def _validate_region_scores(scores: pd.DataFrame) -> None:
    validate_required_columns(scores, REQUIRED_SCORE_COLUMNS)

    if len(scores) == 25:
        print("[OK] region count: 25")
    else:
        raise ValueError(f"Expected 25 regions, got {len(scores)}")

    duplicated_count = scores["region_name"].duplicated().sum()
    if duplicated_count == 0:
        print("[OK] no duplicated region_name")
    else:
        raise ValueError(f"Duplicated region_name count: {duplicated_count}")

    invalid_score_columns = []
    for column in SCORE_COLUMNS:
        if not scores[column].between(0, 100).all():
            invalid_score_columns.append(column)
    if not invalid_score_columns:
        print("[OK] score range valid: 0~100")
    else:
        raise ValueError(f"Score columns out of 0~100 range: {invalid_score_columns}")

    invalid_grades = sorted(set(scores["grade"]) - {"green", "orange", "red"})
    if not invalid_grades:
        print("[OK] grade values valid")
    else:
        raise ValueError(f"Invalid grade values: {invalid_grades}")

    if scores["hamburger_count_score"].nunique() == 1:
        print("[WARN] hamburger_count_score has the same value for all regions")

    if scores["running_score"].nunique() == 1:
        print("[WARN] running_score has the same value for all regions")

    print(
        "[WARN] running_friendly_score is mock-derived; "
        "replace with real running facility/path data later"
    )
    print("[INFO] Top 5 regions by final_score:")
    print(
        scores.sort_values("final_score", ascending=False)
        .head(5)[["region_name", "final_score", "grade"]]
        .to_string(index=False)
    )


def build_region_scores(
    input_path: str | Path = DEFAULT_INPUT_PATH,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> pd.DataFrame:
    """
    region_features.csv를 읽고, 자치구별 점수 컬럼을 계산한 뒤
    region_scores.csv로 저장한다.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    features = pd.read_csv(input_path)
    print("[OK] loaded region_features.csv")
    validate_required_columns(features, REQUIRED_FEATURE_COLUMNS)
    print("[OK] required columns exist")

    scores = features[["region_name"]].copy()

    scores["park_count_score"] = minmax_score(features["park_count"])
    scores["park_area_per_person_score"] = minmax_score(
        features["park_area_per_person"]
    )
    scores["park_ratio_score"] = minmax_score(features["park_ratio"])
    scores["large_park_count_score"] = minmax_score(features["large_park_count"])

    scores["food_count_score"] = minmax_score(features["food_count"])
    scores["cafe_count_score"] = minmax_score(features["cafe_count"])
    scores["hamburger_count_score"] = minmax_score(features["hamburger_count"])
    scores["fastfood_count_score"] = minmax_score(features["fastfood_count"])
    scores["running_friendly_score_norm"] = minmax_score(
        features["running_friendly_score"]
    )
    scores["commercial_area_score_norm"] = minmax_score(
        features["commercial_area_score"]
    )

    # 공원 점수: 러닝/산책 환경에 더 가까운 1인당 공원면적과 공원율을 더 크게 반영한다.
    scores["park_score"] = (
        0.25 * scores["park_count_score"]
        + 0.35 * scores["park_area_per_person_score"]
        + 0.25 * scores["park_ratio_score"]
        + 0.15 * scores["large_park_count_score"]
    )

    # 음식 점수: 핵심 질의에 햄버거집이 직접 등장하므로 hamburger_count를 가장 크게 반영한다.
    scores["food_score"] = (
        0.20 * scores["food_count_score"]
        + 0.15 * scores["cafe_count_score"]
        + 0.45 * scores["hamburger_count_score"]
        + 0.20 * scores["fastfood_count_score"]
    )

    # 러닝 점수: Mock-derived running_friendly_score를 쓰되 park_score를 함께 반영해 교체 가능성을 유지한다.
    scores["running_score"] = (
        0.60 * scores["running_friendly_score_norm"]
        + 0.40 * scores["park_score"]
    )

    # 생활 인프라 점수: 20대 사용자 맥락을 보조로만 반영한다.
    scores["lifestyle_score"] = (
        0.50 * scores["commercial_area_score_norm"]
        + 0.30 * scores["food_score"]
        + 0.20 * scores["cafe_count_score"]
    )

    # 최종 점수: 러닝/공원을 가장 중요하게 보고, 햄버거집/생활 인프라를 그 다음으로 반영한다.
    scores["final_score"] = (
        0.35 * scores["running_score"]
        + 0.30 * scores["park_score"]
        + 0.25 * scores["food_score"]
        + 0.10 * scores["lifestyle_score"]
    )

    for column in [
        "park_score",
        "food_score",
        "running_score",
        "lifestyle_score",
        "final_score",
    ]:
        scores[column] = scores[column].round(2)

    scores["grade"] = scores["final_score"].map(assign_grade)
    scores = scores[
        [
            "region_name",
            "park_score",
            "food_score",
            "running_score",
            "lifestyle_score",
            "final_score",
            "grade",
            "park_count_score",
            "park_area_per_person_score",
            "park_ratio_score",
            "large_park_count_score",
            "food_count_score",
            "cafe_count_score",
            "hamburger_count_score",
            "fastfood_count_score",
            "commercial_area_score_norm",
        ]
    ]

    _validate_region_scores(scores)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"[OK] wrote {output_path}")
    return scores


if __name__ == "__main__":
    region_scores = build_region_scores()
    print(region_scores.sort_values("final_score", ascending=False).head(10))
