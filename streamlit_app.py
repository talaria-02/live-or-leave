"""
Streamlit UI — 서울 지도를 항상 보여주고, 오른쪽 입력창에 필수/선택 요구사항을
입력하면(포커스를 벗어나는 순간) 지도가 자동으로 다시 그려진다.

흐름: 우측 입력(필수/선택) → RecommendationAgent.run(top_n=전체) 자동 호출
      → 상위 top_n1(진한초록)/다음 top_n2(연한초록)/하위 절반(저점수 빨강)+
        절반(필수조건 미충족 보라) 티어링 → 좌측에 지도, 동에 마우스오버하면
        실제 수치를 툴팁으로. 서울 밖은 베이스맵 자체를 꺼서 아예 안 그린다.

티어링·hover 텍스트 조립은 결정론적 포맷팅일 뿐이라 LLM을 안 쓴다 — LLM은
result.message(상위 3개 자연어 설명) 하나에만 관여한다 (agent.run 참고).

주의: "실시간"은 Streamlit의 기본 동작(위젯 값이 바뀌면 스크립트 전체 재실행)을
그대로 쓴 것이다. text_area는 매 타이핑이 아니라 포커스를 잃을 때(블러) 또는
Ctrl+Enter일 때 값이 갱신된다 — 진짜 키 입력마다 갱신하려면 별도 프론트엔드
작업이 필요하다.

기본값은 실제 Solar API다 (재입력할 때마다 parse_intent+explain 2회 호출).
UPSTAGE_API_KEY가 없으면 자동으로 mock으로 낮춘다(load_agent 참고). 키가 있어도
레이아웃·색깔 확인처럼 빠른 반복 작업만 할 땐 강제로 mock으로 전환 가능:
    STREAMLIT_USE_MOCK_LLM=1 streamlit run streamlit_app.py
어느 쪽이든 mock으로 동작 중이면 화면에 경고 캡션이 뜬다.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict

import pandas as pd
import plotly.express as px
import streamlit as st

from app.agent.loop import RecommendationAgent
from app.agent.mock_llm import MockLLM

st.set_page_config(page_title="살래말래 — 행정동 추천", layout="wide")

TOP_K1 = 10          # 진한초록으로 표시할 최상위 개수
TOP_K2 = 20          # 연한초록으로 표시할 다음 개수
BOTTOM_N = 10        # 저점수(빨강) 표시 개수 기준. 필수조건 미충족(보라)은 개수 제한
                     # 없이 전부 그린다 — 일부만 그리면 지도에 구멍이 뚫린다.

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

BORDER_WIDTH = 0.6
BORDER_COLOR = "#616161"


@st.cache_resource
def load_agent() -> RecommendationAgent:
    """RecommendationAgent()의 기본값은 실제 Solar API(SolarLLM)다.
    UPSTAGE_API_KEY가 없는 환경(로컬 UI 개발 등)에서 그대로 두면 API 호출이
    실패하므로 자동으로 MockLLM으로 낮춘다. 키가 있어도 레이아웃·색깔 확인처럼
    빠른 반복 작업만 할 땐 STREAMLIT_USE_MOCK_LLM=1로 강제로 mock을 쓸 수 있다."""
    if os.environ.get("UPSTAGE_API_KEY") and not os.environ.get("STREAMLIT_USE_MOCK_LLM"):
        return RecommendationAgent()
    return RecommendationAgent(llm=MockLLM())


def using_mock_llm() -> bool:
    return not os.environ.get("UPSTAGE_API_KEY") or bool(os.environ.get("STREAMLIT_USE_MOCK_LLM"))


def _mock_llm_reason() -> str:
    if not os.environ.get("UPSTAGE_API_KEY"):
        return "UPSTAGE_API_KEY 없음"
    return "STREAMLIT_USE_MOCK_LLM 설정됨"


# 추천 파이프라인(파싱·필터·스코어링) 코드가 바뀔 때마다 올린다.
# st.cache_data는 함수 인자만 캐시 키로 쓰고 하위 모듈(tools/scoring/solar_llm)
# 코드 변경은 감지하지 못하므로, 버전을 인자로 넘겨 낡은 결과를 무효화한다.
PIPELINE_VERSION = 3  # v3: '근처' 거리 필터 + Kakao 원본 좌표 저장·지도 핀


@st.cache_data(max_entries=128, show_spinner="추천 계산 중…")
def run_agent_cached(combined: str, mock: bool, pipeline_version: int) -> dict:
    """같은 입력 텍스트로는 LLM을 다시 호출하지 않는다.

    Streamlit은 위젯 하나만 바뀌어도 스크립트 전체를 재실행하므로, 캐시가
    없으면 무관한 rerun(예: 필수 입력 blur 후 선택 입력 blur)마다 동일 텍스트로
    parse_intent+explain 2회씩 재호출된다. mock 여부를 키에 포함해 mock으로
    받은 결과가 실 LLM 모드에서 재사용되는 일을 막는다.

    반환은 AgentResult가 아니라 dict — st.cache_data는 반환값을 pickle하는데,
    Streamlit의 모듈 핫리로드 아래에서는 커스텀 클래스 직렬화가 깨진다
    (UnserializableReturnValueError). 평범한 dict/list/str만 남긴다."""
    return asdict(load_agent().run(combined, top_n=500))


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

    # 실격 동은 전부 그린다 — 일부만 그리면 나머지가 지도에서 통째로 사라져
    # 구멍이 뚫린다. 필수 필터 결과 수백 개가 실격될 수 있는데(예: 클라이밍장
    # 없는 동 333개), 그 자체가 사용자에게 의미 있는 정보다.
    for d in disqualified:
        rows.append({
            "code": d["code"], "gu": d["gu"], "dong": d["dong"],
            "tier": "disqualified", "hover": _hover_for_disqualified(d),
        })
    return pd.DataFrame(rows)


def neutral_dataframe(geojson: dict) -> pd.DataFrame:
    """아직 아무 조건도 입력하지 않았을 때 — 전체 동을 회색으로만 표시."""
    rows = []
    for feat in geojson["features"]:
        p = feat["properties"]
        rows.append({
            "code": p["code"], "gu": p["gu"], "dong": p["dong"],
            "tier": "neutral", "hover": f"<b>{p['gu']} {p['dong']}</b>",
        })
    return pd.DataFrame(rows)


_HOVER_CSS = """
<style>
.choroplethlayer path {
    transition: filter 0.12s ease-out, stroke-width 0.12s ease-out;
}
.choroplethlayer path:hover {
    filter: brightness(1.35) saturate(1.5) drop-shadow(0 0 6px rgba(255,255,255,0.95));
    stroke: #ffffff !important;
    stroke-width: 2px !important;
    cursor: pointer;
}
</style>
"""


POINT_STYLE = {
    # 랜드마크("서울대 근처"의 기준점): 크고 눈에 띄는 별
    "landmark": dict(symbol="star", size=18, color="#ffd600",
                     line=dict(width=1.5, color="#212121")),
    # Kakao로 해석된 필수 업종의 실제 위치들: 작은 파란 점
    "facility": dict(symbol="circle", size=7, color="#1e88e5",
                     line=dict(width=1, color="#ffffff")),
}
POINT_LABELS = {"landmark": "기준 장소", "facility": "필수 업종 위치"}


def render_map(df: pd.DataFrame, geojson: dict, points: list[dict] | None = None) -> None:
    """마우스오버 시 폴리곤 자체가 밝아지며 흰 광택 테두리가 도는 효과는 순수
    CSS :hover로 구현한다 — 실제 DOM에 폴리곤별 <path>가 있는 SVG 렌더러
    (px.choropleth)에서만 가능하다 (WebGL/캔버스는 개별 요소가 없어 CSS를
    걸 대상이 없다). JS로 이 효과를 흉내내려던 이전 시도(components.html +
    plotly_hover 이벤트로 marker restyle)는 이 환경에서 WebGL 렌더링 자체를
    깨뜨렸는데, CSS :hover는 브라우저 내장 기능이라 그런 위험이 없다.

    좌표를 이미 93% 단순화해둔 덕에(평균 481점→33점/폴리곤) SVG로 돌아가도
    체감 성능 차이가 크지 않았다 — 단순화 전이었다면 이 전환은 못 했을 것.
    """
    fig = px.choropleth(
        df, geojson=geojson, locations="code", color="tier",
        featureidkey="properties.code",
        color_discrete_map=TIER_COLORS,
        category_orders={"tier": list(TIER_COLORS)},
        custom_data=["hover"],
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}<extra></extra>",
        marker_line_width=BORDER_WIDTH, marker_line_color=BORDER_COLOR,
    )
    for trace in fig.data:
        tier_color = TIER_COLORS.get(trace.name, "#333333")
        trace.hoverlabel = dict(
            bgcolor=tier_color, bordercolor="white",
            font=dict(color="white", size=14, family="Arial Black"),
        )
        trace.name = TIER_LABELS.get(trace.name, trace.name)
    # Kakao 좌표 핀 — 필터가 실제로 어떤 위치를 근거로 걸렸는지 눈으로 검증용.
    # choropleth 위에 겹쳐 그리므로 같은 geo 좌표계를 공유한다.
    for kind in ("facility", "landmark"):  # 랜드마크가 위에 오도록 마지막에
        pts = [p for p in (points or []) if p["kind"] == kind]
        if pts:
            fig.add_scattergeo(
                lon=[p["lon"] for p in pts], lat=[p["lat"] for p in pts],
                mode="markers", marker=POINT_STYLE[kind],
                name=POINT_LABELS[kind],
                text=[p["label"] for p in pts],
                hovertemplate="%{text}<extra></extra>",
                hoverlabel=dict(bgcolor="#263238", font=dict(color="white", size=13)),
            )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0), height=760,
        legend_title_text="",
        legend=dict(orientation="h", yanchor="bottom", y=1.0),
    )
    st.markdown(_HOVER_CSS, unsafe_allow_html=True)
    st.plotly_chart(fig, width="stretch")


def main() -> None:
    geojson = load_boundaries()
    col_map, col_input = st.columns([3, 1])

    with col_input:
        st.subheader("살래말래")
        st.caption("필수는 하드 필터, 선택은 점수에 반영됩니다.")
        if using_mock_llm():
            st.caption(f"⚠ Mock LLM으로 동작 중 ({_mock_llm_reason()})")
        required_text = st.text_area(
            "필수 요구사항", placeholder="예: 헬스장, 대형병원 있어야 함", height=100)
        optional_text = st.text_area(
            "선택 요구사항", placeholder="예: 안전하고 조용한 곳, 지하철 가까운 곳", height=150)
        message_slot = st.empty()

    if not required_text.strip() and not optional_text.strip():
        with col_map:
            render_map(neutral_dataframe(geojson), geojson)
        return

    combined = f"필수 요구사항: {required_text}\n선택 요구사항: {optional_text}"
    result = run_agent_cached(combined, using_mock_llm(), PIPELINE_VERSION)

    if result["kind"] == "clarify":
        message_slot.warning(result["message"])
        with col_map:
            render_map(neutral_dataframe(geojson), geojson)
        return

    message_slot.success(result["message"])
    data = result["data"]
    if data.get("unresolved_requirements"):
        st.warning("해석하지 못한 필수 조건 (필터 미적용): "
                   + ", ".join(data["unresolved_requirements"]))
    df = assign_tiers(data["recommendations"], data.get("disqualified", []))
    with col_map:
        render_map(df, geojson, points=data.get("map_points"))

    with col_input, st.expander("🔍 적용된 필터 검증"):
        st.caption(f"추천 {len(data['recommendations'])}개 / "
                   f"실격 {len(data.get('disqualified', []))}개 "
                   f"(파이프라인 v{PIPELINE_VERSION})")
        for line in result["trace"]:
            st.text(line)


if __name__ == "__main__":
    main()
