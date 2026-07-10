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

from app.agent.mock_llm import MockLLM
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
    def __init__(self, max_steps: int = 4):
        repo = CsvDongRepository()
        self.llm = MockLLM()
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
            required_categories=intent.required_categories,
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
