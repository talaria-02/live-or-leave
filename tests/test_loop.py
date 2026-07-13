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


# ---------- stream() — SSE 컨트롤러용 제너레이터 ----------

def test_stream_clarify_yields_meta_then_delta_then_done():
    events = list(_agent().stream("아무데나 좋은 곳"))
    types_ = [e["type"] for e in events]
    assert types_ == ["meta", "delta", "done"]
    assert events[0]["kind"] == "clarify"
    assert "data" not in events[0]
    assert events[1]["text"]


def test_stream_recommendation_yields_meta_with_data_then_deltas_then_done():
    events = list(_agent().stream("안전하고 조용한 동네가 좋아요"))
    assert events[0]["type"] == "meta"
    assert events[0]["kind"] == "recommendation"
    assert set(events[0]["data"].keys()) == {"weights", "recommendations"}
    assert events[-1] == {"type": "done"}

    delta_events = events[1:-1]
    assert len(delta_events) > 1  # 여러 청크로 쪼개져서 옴 (토큰 스트리밍 확인)
    assert all(e["type"] == "delta" for e in delta_events)


def test_stream_top_n_defaults_to_three():
    events = list(_agent().stream("안전하고 조용한 동네가 좋아요"))
    assert len(events[0]["data"]["recommendations"]) == 3


def test_stream_top_n_expands_recommendations_but_explain_stays_on_top_three():
    """top_n을 늘리면 data.recommendations는 다 담기지만, 설명은 run()과
    마찬가지로 항상 상위 3개만 근거로 삼아야 한다(프롬프트 폭주 방지)."""
    events = list(_agent().stream("안전하고 조용한 동네가 좋아요", top_n=50))
    assert len(events[0]["data"]["recommendations"]) == 50

    message = "".join(e["text"] for e in events if e["type"] == "delta")
    run_message = _agent().run("안전하고 조용한 동네가 좋아요", top_n=50).message
    assert message == run_message  # run()도 top_n=50이어도 설명은 상위 3개 기준


def test_stream_recommendation_deltas_reconstruct_same_message_as_run():
    text = "안전하고 조용한 동네가 좋아요"
    run_result = _agent().run(text)
    stream_events = list(_agent().stream(text))
    streamed_text = "".join(e["text"] for e in stream_events if e["type"] == "delta")
    assert streamed_text == run_result.message


def test_stream_yields_error_event_instead_of_raising():
    class _BrokenLLM:
        def parse_intent(self, text):
            raise ValueError("일부러 실패시킴")

    agent = RecommendationAgent(llm=_BrokenLLM())
    events = list(agent.stream("아무 문장"))
    assert events == [{"type": "error", "message": "일부러 실패시킴"}]
