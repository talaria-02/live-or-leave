"""
Streamlit UI — 필수/선택 요구사항을 받아 425개 행정동을 지도에 티어별로 색칠한다.

흐름: 필수/선택 입력창 → RecommendationAgent.run(top_n=전체) 한 번 호출
      → 상위 top_n1(진한초록)/다음 top_n2(연한초록)/하위 절반(저점수 빨강)+
        절반(필수조건 미충족 빨강) 티어링 → Plotly choropleth로 지도 렌더링,
        동에 마우스오버하면 실제 수치를 툴팁으로.

티어링·hover 텍스트 조립은 결정론적 포맷팅일 뿐이라 LLM을 안 쓴다 — LLM은
result.message(상위 3개 자연어 설명) 하나에만 관여한다 (agent.run 참고).
"""
from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from app.agent.loop import RecommendationAgent

st.set_page_config(page_title="살래말래 — 행정동 추천", layout="wide")

TOP_K1 = 10          # 진한초록으로 표시할 최상위 개수
TOP_K2 = 20          # 연한초록으로 표시할 다음 개수
BOTTOM_N = 10        # 비추천(빨강) 총 개수 — 절반 저점수 / 절반 필수조건 미충족

TIER_COLORS = {
    "top1": "#1b5e20",
    "top2": "#81c784",
    "low_score": "#ef5350",
    "disqualified": "#7b1fa2",
    "neutral": "#e0e0e0",
}
TIER_LABELS = {
    "top1": "추천 (상위)",
    "top2": "추천",
    "low_score": "비추천 (낮은 점수)",
    "disqualified": "비추천 (필수조건 미충족)",
    "neutral": "그 외",
}


@st.cache_resource
def load_agent() -> RecommendationAgent:
    return RecommendationAgent()


@st.cache_data
def load_boundaries() -> dict:
    with open("dong_boundaries.geojson", encoding="utf-8") as f:
        return json.load(f)


def _hover_for_recommendation(rec: dict) -> str:
    raw = rec["scores"]["raw"]
    lines = [
        f"<b>{rec['gu']} {rec['dong']}</b> (종합 {rec['total_score']})",
        f"안전: 범죄율 {raw['crime_rate']}/만명, CCTV {raw['cctv_cnt']}대",
        f"편의: 편의점 {raw['conv_cnt']}·마트 {raw['mart_cnt']}·병원 {raw['hosp_cnt']}",
        f"이동: 버스 {raw['bus_cnt']}개, 지하철 접근성 {raw['subway_access']}",
        f"환경: 공원 {raw['park_cnt']}곳",
    ]
    extra = rec.get("extra_facilities")
    if extra:
        lines.append("요청 업종: " + ", ".join(f"{k} {v}곳" for k, v in extra.items()))
    return "<br>".join(lines)


def _hover_for_disqualified(d: dict) -> str:
    return (f"<b>{d['gu']} {d['dong']}</b><br>"
            f"필수 요구사항 미충족: {', '.join(d['missing'])}")


def assign_tiers(recommendations: list[dict], disqualified: list[dict]) -> pd.DataFrame:
    n = len(recommendations)
    low_score_n = BOTTOM_N - BOTTOM_N // 2
    rows = []
    for i, rec in enumerate(recommendations):
        if i < TOP_K1:
            tier = "top1"
        elif i < TOP_K1 + TOP_K2:
            tier = "top2"
        elif i >= n - low_score_n:
            tier = "low_score"
        else:
            tier = "neutral"
        rows.append({
            "code": rec["scores"]["code"], "gu": rec["gu"], "dong": rec["dong"],
            "tier": tier, "hover": _hover_for_recommendation(rec),
        })

    for d in disqualified[: BOTTOM_N // 2]:
        rows.append({
            "code": d["code"], "gu": d["gu"], "dong": d["dong"],
            "tier": "disqualified", "hover": _hover_for_disqualified(d),
        })
    return pd.DataFrame(rows)


def render_map(df: pd.DataFrame, geojson: dict) -> None:
    fig = px.choropleth_map(
        df, geojson=geojson, locations="code", color="tier",
        featureidkey="properties.code",
        color_discrete_map=TIER_COLORS,
        category_orders={"tier": list(TIER_COLORS)},
        custom_data=["hover"],
        map_style="carto-positron",
        zoom=9.5, center={"lat": 37.5665, "lon": 126.9780},
        opacity=0.75,
    )
    fig.update_traces(hovertemplate="%{customdata[0]}<extra></extra>")
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0), height=720,
        legend_title_text="",
    )
    for trace in fig.data:
        trace.name = TIER_LABELS.get(trace.name, trace.name)
    st.plotly_chart(fig, width="stretch")


def main() -> None:
    st.title("살래말래 — 서울 행정동 추천")
    st.caption("필수 요구사항은 하드 필터, 선택 요구사항은 점수에 반영됩니다.")

    col1, col2 = st.columns(2)
    with col1:
        required_text = st.text_area(
            "필수 요구사항", placeholder="예: 헬스장, 대형병원 있어야 함", height=100)
    with col2:
        optional_text = st.text_area(
            "선택 요구사항", placeholder="예: 안전하고 조용한 곳, 지하철 가까운 곳", height=100)

    if not st.button("추천받기", type="primary"):
        return

    agent = load_agent()
    combined = f"필수 요구사항: {required_text}\n선택 요구사항: {optional_text}"
    with st.spinner("분석 중..."):
        result = agent.run(combined, top_n=500)

    if result.kind == "clarify":
        st.warning(result.message)
        return

    st.success(result.message)

    df = assign_tiers(result.data["recommendations"], result.data.get("disqualified", []))
    geojson = load_boundaries()
    render_map(df, geojson)


if __name__ == "__main__":
    main()
