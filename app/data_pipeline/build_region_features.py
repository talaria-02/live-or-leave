from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_DIR = Path("/Users/jeong-yeongjun/Downloads/dataset 2")
OUTPUT_PATH = PROJECT_ROOT / "processed" / "region_features.csv"

SEOUL_GU_LIST = [
    "종로구",
    "중구",
    "용산구",
    "성동구",
    "광진구",
    "동대문구",
    "중랑구",
    "성북구",
    "강북구",
    "도봉구",
    "노원구",
    "은평구",
    "서대문구",
    "마포구",
    "양천구",
    "강서구",
    "구로구",
    "금천구",
    "영등포구",
    "동작구",
    "관악구",
    "서초구",
    "강남구",
    "송파구",
    "강동구",
]

SEOUL_GU_SET = set(SEOUL_GU_LIST)

CAFE_KEYWORDS = [
    "카페",
    "커피",
    "디저트",
    "베이커리",
    "제과",
    "스타벅스",
    "투썸",
    "이디야",
    "메가커피",
    "컴포즈",
    "빽다방",
]

HAMBURGER_KEYWORDS = [
    "햄버거",
    "버거",
    "롯데리아",
    "맥도날드",
    "버거킹",
    "맘스터치",
    "KFC",
    "프랭크버거",
    "노브랜드버거",
    "파이브가이즈",
    "쉐이크쉑",
]

FASTFOOD_KEYWORDS = [
    "패스트푸드",
    "햄버거",
    "버거",
    "치킨",
    "피자",
    "KFC",
    "롯데리아",
    "맥도날드",
    "버거킹",
    "맘스터치",
]

LARGE_PARK_BONUS = {
    "종로구": 3,
    "강북구": 4,
    "도봉구": 3,
    "노원구": 3,
    "서초구": 3,
    "송파구": 3,
    "성동구": 2,
    "마포구": 2,
    "광진구": 2,
    "영등포구": 2,
}


def normalize_region_name(name: str | float | None) -> str | None:
    if name is None or pd.isna(name):
        return None

    text = unicodedata.normalize("NFC", str(name)).strip()
    text = re.sub(r"\s+", "", text)
    text = text.replace("서울특별시", "").replace("서울시", "")

    for gu in SEOUL_GU_LIST:
        if gu in text:
            return gu

    aliases = {
        "종로": "종로구",
        "중": "중구",
        "용산": "용산구",
        "성동": "성동구",
        "광진": "광진구",
        "동대문": "동대문구",
        "중랑": "중랑구",
        "성북": "성북구",
        "강북": "강북구",
        "도봉": "도봉구",
        "노원": "노원구",
        "은평": "은평구",
        "서대문": "서대문구",
        "마포": "마포구",
        "양천": "양천구",
        "강서": "강서구",
        "구로": "구로구",
        "금천": "금천구",
        "영등포": "영등포구",
        "동작": "동작구",
        "관악": "관악구",
        "서초": "서초구",
        "강남": "강남구",
        "송파": "송파구",
        "강동": "강동구",
    }
    return aliases.get(text)


def find_dataset_file(dataset_dir: Path, required_keywords: list[str], suffix: str) -> Path:
    for path in dataset_dir.iterdir():
        normalized_name = unicodedata.normalize("NFC", path.name)
        if path.suffix.lower() == suffix and all(
            keyword in normalized_name for keyword in required_keywords
        ):
            return path
    raise FileNotFoundError(f"Dataset not found: {required_keywords} ({suffix})")


def load_base_regions() -> pd.DataFrame:
    return pd.DataFrame({"region_name": SEOUL_GU_LIST})


def to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace("-", pd.NA), errors="coerce")


def minmax_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    min_value = values.min()
    max_value = values.max()
    if pd.isna(min_value) or pd.isna(max_value) or min_value == max_value:
        return pd.Series([50.0] * len(values), index=series.index)

    score = (values - min_value) / (max_value - min_value) * 100
    if not higher_is_better:
        score = 100 - score
    return score.round(2)


def build_park_features(dataset_dir: Path = DEFAULT_DATASET_DIR) -> pd.DataFrame:
    area_path = find_dataset_file(dataset_dir, ["공원", "1인당", "면적"], ".xlsx")
    ratio_path = find_dataset_file(dataset_dir, ["공원", "공원율"], ".xlsx")

    area_raw = pd.read_excel(area_path, sheet_name=0, header=None)
    area_df = area_raw.iloc[4:].copy()
    area_df["region_name"] = area_df[1].map(normalize_region_name)
    area_df["park_area_per_person"] = to_numeric(area_df[3])
    area_df = area_df[area_df["region_name"].isin(SEOUL_GU_SET)]
    area_df = area_df[["region_name", "park_area_per_person"]]

    ratio_raw = pd.read_excel(ratio_path, sheet_name=0, header=None)
    ratio_df = ratio_raw.iloc[4:].copy()
    ratio_df["region_name"] = ratio_df[1].map(normalize_region_name)
    ratio_df["park_ratio"] = to_numeric(ratio_df[4])
    ratio_df = ratio_df[ratio_df["region_name"].isin(SEOUL_GU_SET)]
    ratio_df = ratio_df[["region_name", "park_ratio"]]

    features = load_base_regions().merge(area_df, on="region_name", how="left")
    features = features.merge(ratio_df, on="region_name", how="left")
    features["park_area_per_person"] = features["park_area_per_person"].fillna(
        features["park_area_per_person"].median()
    )
    features["park_ratio"] = features["park_ratio"].fillna(features["park_ratio"].median())

    park_base_score = (
        minmax_score(features["park_area_per_person"]) * 0.55
        + minmax_score(features["park_ratio"]) * 0.45
    )
    features["park_count"] = (12 + park_base_score / 100 * 32).round().astype(int)
    features["large_park_count"] = (park_base_score / 34).round().astype(int)
    features["large_park_count"] = features.apply(
        lambda row: max(
            int(row["large_park_count"]),
            LARGE_PARK_BONUS.get(row["region_name"], 0),
        ),
        axis=1,
    )

    return features


def keyword_mask(df: pd.DataFrame, columns: list[str], keywords: list[str]) -> pd.Series:
    pattern = "|".join(re.escape(keyword) for keyword in keywords)
    text = df[columns].fillna("").astype(str).agg(" ".join, axis=1)
    return text.str.contains(pattern, case=False, regex=True)


def build_food_features(dataset_dir: Path = DEFAULT_DATASET_DIR) -> pd.DataFrame:
    store_path = find_dataset_file(dataset_dir, ["상가", "서울"], ".csv")
    usecols = [
        "상호명",
        "상권업종대분류명",
        "상권업종중분류명",
        "상권업종소분류명",
        "표준산업분류명",
        "시군구명",
    ]
    store_df = pd.read_csv(store_path, encoding="utf-8-sig", usecols=usecols)
    store_df["region_name"] = store_df["시군구명"].map(normalize_region_name)
    store_df = store_df[store_df["region_name"].isin(SEOUL_GU_SET)].copy()

    food_df = store_df[store_df["상권업종대분류명"].eq("음식")].copy()
    text_columns = ["상호명", "상권업종소분류명", "표준산업분류명"]
    hamburger_text_columns = ["상호명", "상권업종소분류명"]

    food_count = food_df.groupby("region_name").size().rename("food_count")
    cafe_count = (
        food_df[keyword_mask(food_df, text_columns, CAFE_KEYWORDS)]
        .groupby("region_name")
        .size()
        .rename("cafe_count")
    )
    hamburger_count = (
        food_df[keyword_mask(food_df, hamburger_text_columns, HAMBURGER_KEYWORDS)]
        .groupby("region_name")
        .size()
        .rename("hamburger_count")
    )
    fastfood_count = (
        food_df[keyword_mask(food_df, text_columns, FASTFOOD_KEYWORDS)]
        .groupby("region_name")
        .size()
        .rename("fastfood_count")
    )

    features = load_base_regions()
    for count_series in [food_count, cafe_count, hamburger_count, fastfood_count]:
        features = features.merge(
            count_series.reset_index(), on="region_name", how="left"
        )

    count_columns = ["food_count", "cafe_count", "hamburger_count", "fastfood_count"]
    features[count_columns] = features[count_columns].fillna(0).astype(int)
    return features


def add_mock_or_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    park_score = (
        minmax_score(df["park_count"]) * 0.2
        + minmax_score(df["park_area_per_person"]) * 0.3
        + minmax_score(df["park_ratio"]) * 0.35
        + minmax_score(df["large_park_count"]) * 0.15
    )
    commercial_score = (
        minmax_score(df["food_count"]) * 0.35
        + minmax_score(df["cafe_count"]) * 0.25
        + minmax_score(df["hamburger_count"]) * 0.25
        + minmax_score(df["fastfood_count"]) * 0.15
    )

    df["running_friendly_score"] = park_score.round(2)
    df["commercial_area_score"] = commercial_score.round(2)
    return df


def validate_region_features(df: pd.DataFrame) -> None:
    required_columns = [
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
    missing_columns = [column for column in required_columns if column not in df.columns]
    duplicated_regions = df["region_name"].duplicated().sum()
    missing_values = df[required_columns].isna().sum().sum()
    numeric_columns = [column for column in required_columns if column != "region_name"]
    non_numeric_columns = [
        column for column in numeric_columns if not pd.api.types.is_numeric_dtype(df[column])
    ]

    if len(df) == 25:
        print("[OK] region count: 25")
    else:
        print(f"[ERROR] region count: {len(df)}")

    if not missing_columns:
        print("[OK] required columns exist")
    else:
        print(f"[ERROR] missing columns: {missing_columns}")

    if duplicated_regions == 0:
        print("[OK] no duplicated region_name")
    else:
        print(f"[ERROR] duplicated region_name count: {duplicated_regions}")

    if not non_numeric_columns:
        print("[OK] all numeric features are numeric")
    else:
        print(f"[ERROR] non-numeric features: {non_numeric_columns}")

    if missing_values == 0:
        print("[OK] no missing values")
    else:
        print(f"[ERROR] missing values: {missing_values}")

    if df["hamburger_count"].sum() > 0:
        print(f"[OK] hamburger_count total: {int(df['hamburger_count'].sum())}")
    else:
        print("[ERROR] hamburger_count is zero for all regions")

    if df[["park_count", "park_area_per_person", "park_ratio"]].sum().sum() > 0:
        print("[OK] park features populated")
    else:
        print("[ERROR] park features are empty")

    print("[WARN] park_count generated as mock-derived count")
    print("[WARN] large_park_count generated as mock-derived count")
    print("[WARN] running_friendly_score generated as mock-derived score")
    print("[WARN] commercial_area_score generated as derived aggregate score")

    if missing_columns or duplicated_regions or missing_values or non_numeric_columns:
        raise ValueError("region_features validation failed")


def build_region_features(dataset_dir: Path = DEFAULT_DATASET_DIR) -> pd.DataFrame:
    base = load_base_regions()
    park_features = build_park_features(dataset_dir)
    food_features = build_food_features(dataset_dir)

    features = base.merge(park_features, on="region_name", how="left")
    features = features.merge(food_features, on="region_name", how="left")

    numeric_columns = [
        "park_count",
        "park_area_per_person",
        "park_ratio",
        "large_park_count",
        "food_count",
        "cafe_count",
        "hamburger_count",
        "fastfood_count",
    ]
    for column in numeric_columns:
        if column in {"food_count", "cafe_count", "hamburger_count", "fastfood_count"}:
            features[column] = features[column].fillna(0)
        else:
            features[column] = features[column].fillna(features[column].median())

    count_columns = [
        "park_count",
        "large_park_count",
        "food_count",
        "cafe_count",
        "hamburger_count",
        "fastfood_count",
    ]
    features[count_columns] = features[count_columns].round().astype(int)
    features["park_area_per_person"] = features["park_area_per_person"].round(2)
    features["park_ratio"] = features["park_ratio"].round(2)

    features = add_mock_or_derived_features(features)
    features = features[
        [
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
    ]
    validate_region_features(features)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"[OK] wrote {OUTPUT_PATH}")
    return features


if __name__ == "__main__":
    build_region_features()
