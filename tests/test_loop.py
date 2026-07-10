"""agent/loop.py (RecommendationAgent) 단위 테스트.

RecommendationAgent 기본값은 실제 Solar API이므로, 여기서는 결과 shape·
되묻기 분기·trace 로그를 빠르고 결정론적으로 검증하기 위해 MockLLM을 명시적으로
주입한다. (test_flow.py는 시나리오 전체 흐름 검증, 여기는 AgentResult 구조 세분화 검증)
"""
from __future__ import annotations

from app.agent.loop import RecommendationAgent
from app.agent.mock_llm import MockLLM


def _agent() -> RecommendationAgent:
    return RecommendationAgent(llm=MockLLM())


def test_clarify_result_shape_has_no_data():
    result = _agent().run("아무데나 좋은 곳")
    assert result.kind == "clarify"
    assert result.message
    assert result.data is None
    assert len(result.trace) >= 1


def test_recommendation_result_shape():
    result = _agent().run("안전하고 조용한 동네가 좋아요")
    assert result.kind == "recommendation"
    assert result.data is not None
    assert set(result.data.keys()) == {"weights", "recommendations"}
    assert len(result.data["recommendations"]) == 3  # loop.py가 top_n=3 고정

    for rec in result.data["recommendations"]:
        assert set(rec.keys()) >= {"rank", "dong", "gu", "total_score", "contributions", "scores"}

    ranks = [r["rank"] for r in result.data["recommendations"]]
    assert ranks == [1, 2, 3]


def test_recommendation_scores_sorted_descending():
    result = _agent().run("공원 많고 조용한 동네")
    totals = [r["total_score"] for r in result.data["recommendations"]]
    assert totals == sorted(totals, reverse=True)


def test_trace_logs_parse_intent_and_tool_and_explain_steps():
    result = _agent().run("안전하고 지하철 가까운 곳")
    joined = " ".join(result.trace)
    assert "parse_intent" in joined
    assert "tool:recommend" in joined
    assert "explain" in joined


def test_trace_stops_after_clarification_without_calling_tool():
    result = _agent().run("아무데나 좋은 곳")
    joined = " ".join(result.trace)
    assert "needs_clarification" in joined
    assert "tool:recommend" not in joined
