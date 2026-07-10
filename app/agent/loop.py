"""
ReAct 루프 오케스트레이터.

흐름: 관측(사용자 입력) → 판단(입구 LLM 의도 파싱)
      → [모호하면 되묻기 1회로 종료]
      → 행동(recommend 도구 호출) → 관측(결과)
      → 종합(출구 LLM 근거 설명)

앞선 논의대로 '도구 자율 연쇄'는 절제한다. 흐름은 입구→도구→출구로 고정하되,
되묻기라는 최소한의 agentic 분기만 둔다. max_steps로 무한 루프를 차단한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agent.solar_llm import SolarLLM
from app.agent.tools import ToolExecutor
from app.data.csv_repository import CsvDongRepository
from app.schemas.tools import RecommendTool


@dataclass
class AgentResult:
    kind: str                       # "recommendation" | "clarify"
    message: str
    trace: list[str] = field(default_factory=list)  # ReAct 관측/행동 로그
    data: dict | None = None


class RecommendationAgent:
    def __init__(self, max_steps: int = 4, llm=None):
        repo = CsvDongRepository()
        # 프로덕션 기본값은 실제 Solar API. llm=MockLLM() 등으로 테스트에서만 교체.
        self.llm = llm or SolarLLM()
        self.tools = ToolExecutor(repo)
        self.max_steps = max_steps

    def run(self, user_text: str) -> AgentResult:
        trace: list[str] = []
        steps = 0

        # --- 판단: 입구 LLM 의도 파싱 ---
        steps += 1
        intent = self.llm.parse_intent(user_text)
        trace.append(f"[step {steps}] parse_intent → {intent.preference.model_dump()} "
                     f"(hospital={intent.require_large_hospital}, "
                     f"clarify={intent.needs_clarification})")

        # --- agentic 분기: 모호하면 되묻기로 종료 ---
        if intent.needs_clarification:
            trace.append(f"[step {steps}] needs_clarification → 되묻기 반환")
            return AgentResult(
                kind="clarify",
                message=intent.clarify_question or "조금 더 구체적으로 알려주세요.",
                trace=trace,
            )

        # --- 행동: recommend 도구 호출 ---
        steps += 1
        if steps > self.max_steps:
            return AgentResult(kind="clarify", message="처리 한도를 초과했습니다.", trace=trace)
        tool_args = RecommendTool(
            preference=intent.preference,
            require_large_hospital=intent.require_large_hospital,
            extra_categories=intent.extra_categories,
            top_n=3,
        )
        result = self.tools.recommend(tool_args)
        top = [r["gu"] for r in result["recommendations"]]
        trace.append(f"[step {steps}] tool:recommend → weights={result['weights']} "
                     f"top={top}")

        # --- 종합: 출구 LLM 근거 설명 ---
        steps += 1
        message = self.llm.explain(user_text, result)
        trace.append(f"[step {steps}] explain → 근거 설명 생성 ({len(top)}건)")

        return AgentResult(
            kind="recommendation", message=message, trace=trace, data=result
        )

    def stream(self, user_text: str):
        """SSE 컨트롤러(main.py)용 제너레이터 버전의 run().

        run()과 동일한 흐름(파싱→[되묻기]→도구→설명)을 따르되, 설명 단계를
        토큰 단위 이벤트로 흘려보낸다. 실패해도 예외를 밖으로 던지지 않고
        {"type": "error"} 이벤트로 알린다 — SSE는 응답이 이미 시작된 상태라
        HTTP 상태 코드로는 실패를 표현할 수 없기 때문이다.

        이벤트 종류: meta(kind/trace/[data]) → delta(text)* → done, 또는 error(message).
        """
        trace: list[str] = []
        try:
            steps = 1
            intent = self.llm.parse_intent(user_text)
            trace.append(f"[step {steps}] parse_intent → {intent.preference.model_dump()} "
                         f"(hospital={intent.require_large_hospital}, "
                         f"clarify={intent.needs_clarification})")

            if intent.needs_clarification:
                trace.append(f"[step {steps}] needs_clarification → 되묻기 반환")
                yield {"type": "meta", "kind": "clarify", "trace": list(trace)}
                yield {"type": "delta", "text": intent.clarify_question or "조금 더 구체적으로 알려주세요."}
                yield {"type": "done"}
                return

            steps += 1
            if steps > self.max_steps:
                yield {"type": "meta", "kind": "clarify", "trace": list(trace)}
                yield {"type": "delta", "text": "처리 한도를 초과했습니다."}
                yield {"type": "done"}
                return
            tool_args = RecommendTool(
                preference=intent.preference,
                require_large_hospital=intent.require_large_hospital,
                extra_categories=intent.extra_categories,
                top_n=3,
            )
            result = self.tools.recommend(tool_args)
            top = [r["gu"] for r in result["recommendations"]]
            trace.append(f"[step {steps}] tool:recommend → weights={result['weights']} "
                         f"top={top}")

            steps += 1
            trace.append(f"[step {steps}] explain_stream → 근거 설명 스트리밍 시작 ({len(top)}건)")
            yield {"type": "meta", "kind": "recommendation", "trace": list(trace), "data": result}

            for chunk in self.llm.explain_stream(user_text, result):
                yield {"type": "delta", "text": chunk}

            yield {"type": "done"}
        except Exception as e:
            yield {"type": "error", "message": str(e)}
