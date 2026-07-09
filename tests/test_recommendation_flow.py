from fastapi.testclient import TestClient

from app.core.constants import score_to_color
from app.main import create_app


client = TestClient(create_app())


def test_health_check() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "live-or-leave"}


def test_recommendation_flow_with_mock_data() -> None:
    response = client.post(
        "/api/v1/recommend/sync",
        json={
            "message": "월세가 저렴하고 지하철이 가까우며, 공원과 햄버거집이 많은 서울 동네를 추천해줘."
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["preferences"]["keywords"]
    assert len(payload["recommendations"]) == 3

    for recommendation in payload["recommendations"]:
        assert recommendation["district"]
        assert 0 <= recommendation["score"] <= 1
        assert recommendation["color"] in {"green", "orange", "red"}
        assert recommendation["reasons"]


def test_score_color_mapping() -> None:
    assert score_to_color(0.7) == "green"
    assert score_to_color(0.69) == "orange"
    assert score_to_color(0.3) == "orange"
    assert score_to_color(0.29) == "red"

