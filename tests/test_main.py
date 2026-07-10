"""main.py (FastAPI 컨트롤러) 단위 테스트.

실제 Solar API를 타지 않도록 get_agent 의존성을 MockLLM 기반 에이전트로
오버라이드한다 (main.py의 기본 _agent는 SolarLLM을 쓰므로 그대로 두면 테스트가
네트워크·키에 의존하게 된다).
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

import main
from app.agent.loop import RecommendationAgent
from app.agent.mock_llm import MockLLM

main.app.dependency_overrides[main.get_agent] = lambda: RecommendationAgent(llm=MockLLM())
client = TestClient(main.app)


def _parse_sse(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_recommend_streams_sse_content_type():
    resp = client.get("/recommend", params={"text": "안전하고 조용한 동네가 좋아요"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")


def test_recommend_recommendation_events_shape():
    resp = client.get("/recommend", params={"text": "안전하고 조용한 동네가 좋아요"})
    events = _parse_sse(resp.text)

    assert events[0]["type"] == "meta"
    assert events[0]["kind"] == "recommendation"
    assert set(events[0]["data"].keys()) == {"weights", "recommendations"}
    assert events[-1] == {"type": "done"}
    assert all(e["type"] == "delta" for e in events[1:-1])
    assert len(events) > 2  # meta + 여러 delta + done


def test_recommend_clarify_events_shape():
    resp = client.get("/recommend", params={"text": "아무데나 좋은 곳"})
    events = _parse_sse(resp.text)

    types_ = [e["type"] for e in events]
    assert types_ == ["meta", "delta", "done"]
    assert events[0]["kind"] == "clarify"
