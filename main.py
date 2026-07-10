"""
FastAPI 컨트롤러 — HTTP 요청을 받아 RecommendationAgent를 호출하고,
근거 설명을 SSE(Server-Sent Events)로 토큰 단위 스트리밍한다.

레이어 원칙: 이 파일은 HTTP 전송(라우팅·SSE 포맷팅)만 담당한다. 추천 로직·LLM
선택·에러 판단은 전부 app/agent/loop.py의 RecommendationAgent가 갖고 있다.

실행: uvicorn main:app --reload
"""
from __future__ import annotations

import json

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.agent.loop import RecommendationAgent

app = FastAPI(title="살래말래 (Live or Leave)")

# MVP 단계라 전체 허용. 실제 배포 전에는 프론트 도메인으로 좁힐 것.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 요청마다 CsvDongRepository(dong_metrics.csv)를 새로 읽지 않도록 프로세스 수명 동안 재사용.
_agent = RecommendationAgent()


def get_agent() -> RecommendationAgent:
    return _agent


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/recommend")
def recommend(text: str, agent: RecommendationAgent = Depends(get_agent)) -> StreamingResponse:
    def event_stream():
        for event in agent.stream(text):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
