from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

CORE_QUERY = "나는 러닝을 좋아하는 20대 남자야. 근처에 공원과 햄버거집이 많은 동네를 추천해줘."


def assert_score_range(value) -> None:
    assert isinstance(value, (int, float))
    assert 0 <= value <= 100


def assert_valid_recommendation_item(item: dict, expected_rank: int) -> None:
    required_keys = {
        "rank",
        "region_name",
        "final_score",
        "grade",
        "reason",
        "score_breakdown",
        "matched_preferences",
    }
    assert required_keys.issubset(item.keys())

    assert item["rank"] == expected_rank
    assert isinstance(item["region_name"], str)
    assert item["region_name"].strip() != ""
    assert_score_range(item["final_score"])
    assert item["grade"] in {"green", "orange", "red"}
    assert isinstance(item["reason"], str)
    assert item["reason"].strip() != ""

    assert isinstance(item["score_breakdown"], dict)
    for key in ["running_score", "park_score", "food_score", "lifestyle_score"]:
        assert key in item["score_breakdown"]
        assert_score_range(item["score_breakdown"][key])

    assert isinstance(item["matched_preferences"], list)


def test_health_check() -> None:
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"


def test_recommend_core_scenario() -> None:
    response = client.post("/recommend", json={"query": CORE_QUERY})

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "query" in data
    assert "matched_preferences" in data
    assert "weights" in data
    assert "recommendations" in data
    assert data["query"] == CORE_QUERY

    matched_preferences = set(data["matched_preferences"])
    assert {"running", "park", "food"}.issubset(matched_preferences)
    # lifestyle("20대")은 구현 정책에 따라 감지 여부가 달라질 수 있어 강제 검증하지 않는다.

    weights = data["weights"]
    for key in ["running_score", "park_score", "food_score", "lifestyle_score"]:
        assert key in weights
        assert isinstance(weights[key], (int, float))
        assert weights[key] >= 0
    assert abs(sum(weights.values()) - 1.0) < 1e-6

    recommendations = data["recommendations"]
    assert len(recommendations) == 3
    for idx, item in enumerate(recommendations, start=1):
        assert_valid_recommendation_item(item, expected_rank=idx)

    scores = [item["final_score"] for item in recommendations]
    assert scores == sorted(scores, reverse=True)


def test_recommend_empty_query_validation() -> None:
    response = client.post("/recommend", json={"query": ""})

    assert response.status_code in (400, 422)


def test_recommend_query_with_partial_preferences() -> None:
    query = "공원이 많은 동네를 추천해줘."
    response = client.post("/recommend", json={"query": query})

    assert response.status_code == 200
    data = response.json()
    assert "park" in data["matched_preferences"]

    recommendations = data["recommendations"]
    assert len(recommendations) == 3
    for idx, item in enumerate(recommendations, start=1):
        assert_valid_recommendation_item(item, expected_rank=idx)
