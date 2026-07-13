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
UPSTAGE_API_KEY가 없으면 자동으로 mock으로 낮춘다(load_agent 참고, app.agent.factory
공유). 키가 있어도 레이아웃·색깔 확인처럼 빠른 반복 작업만 할 땐 강제로 mock으로 전환 가능:
    USE_MOCK_LLM=1 streamlit run streamlit_app.py
어느 쪽이든 mock으로 동작 중이면 화면에 경고 캡션이 뜬다. main.py(FastAPI)도 이
판단(app.agent.factory.using_mock_llm)을 그대로 공유한다 — 두 앱이 같은
환경변수에 항상 같은 결정을 내린다.
"""
from __future__ import annotations

import json
from dataclasses import asdict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.agent.factory import build_recommendation_agent, mock_llm_reason, using_mock_llm
from app.agent.loop import RecommendationAgent

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

# 지도 베이스 스타일 (MapLibre, 토큰 불필요)
MAP_STYLES = {
    "위성사진": "satellite",
    "위성+도로": "satellite-streets",
    "일반": "open-street-map",
    "어두움": "carto-darkmatter",
}
SEOUL_CENTER = {"lat": 37.5642, "lon": 126.9976}
SEOUL_ZOOM = 10.4
DEFAULT_MAP_STYLE = "어두움"
TIER_OPACITY = 0.62          # 색깔 티어(추천/비추천) — 위성사진이 비쳐 보이도록 반투명
NEUTRAL_TIER_OPACITY = 0.0   # '그 외'는 채우지 않는다 — 서울 안쪽은 위성사진 그대로
OUTSIDE_DIM_OPACITY = 0.6    # 서울 바깥을 어둡게 깔아 서울이 도드라지게(스포트라이트 효과)

# 서울 핵심시설 — 지도 방향감·검증용 고정 마커 (교통/병원/대학/랜드마크)
CORE_FACILITIES: list[dict] = [
    {"name": "서울역", "cat": "교통", "lat": 37.5547, "lon": 126.9707},
    {"name": "용산역", "cat": "교통", "lat": 37.5299, "lon": 126.9646},
    {"name": "청량리역", "cat": "교통", "lat": 37.5802, "lon": 127.0479},
    {"name": "왕십리역", "cat": "교통", "lat": 37.5613, "lon": 127.0374},
    {"name": "강남역", "cat": "교통", "lat": 37.4979, "lon": 127.0276},
    {"name": "홍대입구역", "cat": "교통", "lat": 37.5570, "lon": 126.9236},
    {"name": "김포공항", "cat": "교통", "lat": 37.5586, "lon": 126.7906},
    {"name": "서울대병원", "cat": "병원", "lat": 37.5799, "lon": 126.9990},
    {"name": "세브란스병원", "cat": "병원", "lat": 37.5622, "lon": 126.9410},
    {"name": "삼성서울병원", "cat": "병원", "lat": 37.4881, "lon": 127.0855},
    {"name": "서울아산병원", "cat": "병원", "lat": 37.5270, "lon": 127.1085},
    {"name": "서울대학교", "cat": "대학", "lat": 37.4598, "lon": 126.9511},
    {"name": "연세대학교", "cat": "대학", "lat": 37.5658, "lon": 126.9386},
    {"name": "고려대학교", "cat": "대학", "lat": 37.5895, "lon": 127.0323},
    {"name": "시청", "cat": "랜드마크", "lat": 37.5663, "lon": 126.9779},
    {"name": "경복궁", "cat": "랜드마크", "lat": 37.5796, "lon": 126.9770},
    {"name": "N서울타워", "cat": "랜드마크", "lat": 37.5512, "lon": 126.9882},
    {"name": "코엑스", "cat": "랜드마크", "lat": 37.5088, "lon": 127.0627},
    {"name": "롯데월드타워", "cat": "랜드마크", "lat": 37.5125, "lon": 127.1025},
    {"name": "국회의사당", "cat": "랜드마크", "lat": 37.5319, "lon": 126.9140},
    {"name": "상암 DMC", "cat": "랜드마크", "lat": 37.5779, "lon": 126.8897},
]
FACILITY_CAT_STYLE = {
    "교통": dict(color="#00e5ff", symbol="circle"),
    "병원": dict(color="#ff5252", symbol="circle"),
    "대학": dict(color="#ffab40", symbol="circle"),
    "랜드마크": dict(color="#eeff41", symbol="circle"),
}


@st.cache_resource
def load_agent() -> RecommendationAgent:
    """mock 판단·생성 로직은 app.agent.factory 공유 — main.py(FastAPI)와
    이 판단이 어긋나지 않는다. 여기서는 Streamlit 프로세스 재사용을 위해
    build_recommendation_agent() 결과를 @st.cache_resource로 캐싱만 한다."""
    return build_recommendation_agent()


def _mock_llm_reason() -> str:
    return mock_llm_reason()


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


@st.cache_data
def load_outside_seoul_mask() -> dict:
    """서울 바깥 전체(지도가 확대/축소돼도 안 뚫리도록 지구 전체 범위)를 덮는
    마스크 폴리곤 — 구멍이 정확히 서울 426개 동의 합집합 모양이다. 위성사진
    위에 이걸 어둡게 깔면 구멍(서울)만 밝게 도드라져 보인다(스포트라이트 효과)."""
    from shapely.geometry import box, mapping, shape
    from shapely.ops import unary_union

    geojson = load_boundaries()
    seoul = unary_union([shape(f["geometry"]) for f in geojson["features"]])
    world = box(-180, -85, 180, 85)  # 위경도 전체(위도는 웹메르카토르 한계인 ±85)
    mask = world.difference(seoul)
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"id": "OUTSIDE"}, "geometry": mapping(mask)}
    ]}


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


POINT_STYLE = {
    # 랜드마크("서울대 근처"의 기준점): 크고 눈에 띄는 별
    "landmark": dict(size=16, color="#ffd600"),
    # Kakao로 해석된 필수 업종의 실제 위치들: 작은 파란 점
    "facility": dict(size=8, color="#1e88e5"),
}
POINT_LABELS = {"landmark": "기준 장소", "facility": "필수 업종 위치"}


def render_map(
    df: pd.DataFrame,
    geojson: dict,
    points: list[dict] | None = None,
    map_style: str = "satellite",
    show_core: bool = True,
) -> None:
    """MapLibre 타일 기반 지도(px.choropleth_map) — 위성사진 등 실제 베이스맵
    위에 행정동 티어를 반투명으로 얹는다. 예전 px.choropleth(SVG)에서 쓰던
    CSS :hover 광택 효과는 WebGL 타일 렌더러에는 폴리곤별 DOM이 없어 불가 —
    위성 베이스맵과 맞바꾼 트레이드오프다. plotly 내장 hover 툴팁은 유지된다.
    """
    fig = px.choropleth_map(
        df, geojson=geojson, locations="code", color="tier",
        featureidkey="properties.code",
        color_discrete_map=TIER_COLORS,
        category_orders={"tier": list(TIER_COLORS)},
        custom_data=["hover"],
        map_style=map_style,
        center=SEOUL_CENTER, zoom=SEOUL_ZOOM,
        opacity=TIER_OPACITY,
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}<extra></extra>",
        marker_line_width=BORDER_WIDTH, marker_line_color=BORDER_COLOR,
    )

    # 서울 바깥을 어둡게 깔아 서울이 도드라지게 (스포트라이트 효과). 구멍이
    # 정확히 서울 모양이라 Seoul 안쪽 fill(위 choropleth_map)과 겹치지 않는다 —
    # 그래서 trace 순서 상관없이 시각적으로 안전하다.
    mask_geojson = load_outside_seoul_mask()
    fig.add_trace(go.Choroplethmap(
        geojson=mask_geojson, locations=["OUTSIDE"], featureidkey="properties.id",
        z=[1], colorscale=[[0, "black"], [1, "black"]], showscale=False,
        marker=dict(opacity=OUTSIDE_DIM_OPACITY, line=dict(width=0)),
        name="서울 바깥", hoverinfo="skip",
    ))

    for trace in fig.data:
        tier_color = TIER_COLORS.get(trace.name, "#333333")
        trace.hoverlabel = dict(
            bgcolor=tier_color, bordercolor="white",
            font=dict(color="white", size=14, family="Arial Black"),
        )
        if trace.name == "neutral":
            trace.marker.opacity = NEUTRAL_TIER_OPACITY
        trace.name = TIER_LABELS.get(trace.name, trace.name)

    # 서울 핵심시설 — 방향감 기준점 (교통/병원/대학/랜드마크, 범례로 켜고 끔)
    if show_core:
        for cat, style in FACILITY_CAT_STYLE.items():
            items = [f for f in CORE_FACILITIES if f["cat"] == cat]
            fig.add_scattermap(
                lon=[f["lon"] for f in items], lat=[f["lat"] for f in items],
                mode="markers+text",
                marker=dict(size=10, color=style["color"]),
                text=[f["name"] for f in items],
                textfont=dict(size=10, color="#ffffff"),
                textposition="top center",
                name=f"핵심시설·{cat}",
                hovertemplate="%{text}<extra></extra>",
                hoverlabel=dict(bgcolor="#263238", font=dict(color="white", size=13)),
            )

    # Kakao 좌표 핀 — 필터가 실제로 어떤 위치를 근거로 걸렸는지 눈으로 검증용
    for kind in ("facility", "landmark"):  # 랜드마크가 위에 오도록 마지막에
        pts = [p for p in (points or []) if p["kind"] == kind]
        if pts:
            fig.add_scattermap(
                lon=[p["lon"] for p in pts], lat=[p["lat"] for p in pts],
                mode="markers", marker=POINT_STYLE[kind],
                name=POINT_LABELS[kind],
                text=[p["label"] for p in pts],
                hovertemplate="%{text}<extra></extra>",
                hoverlabel=dict(bgcolor="#263238", font=dict(color="white", size=13)),
            )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0), height=760,
        legend_title_text="",
        legend=dict(orientation="h", yanchor="bottom", y=1.0,
                    bgcolor="rgba(0,0,0,0.45)", font=dict(color="white")),
        # 위젯 하나 건드릴 때마다(체크박스·셀렉트박스·텍스트 blur) Streamlit이
        # 완전히 새 Figure를 넘기는데, uirevision이 없으면 Plotly가 이걸 "새
        # 지도"로 보고 사용자가 확대/이동해둔 카메라 위치를 매번 초기화한다.
        # 고정값으로 두면 데이터(색·핀)만 갱신되고 카메라는 유지된다.
        uirevision="seoul-map",
    )
    # key 고정 — Streamlit이 매 rerun마다 이 컴포넌트를 같은 인스턴스로 취급해
    # Plotly.react(데이터만 갱신)를 쓰게 강제한다. key 없으면(또는 위치가
    # 흔들리면) 리마운트로 취급돼 지도가 매번 처음부터 다시 그려질 수 있다.
    st.plotly_chart(fig, width="stretch", config={"responsive": True}, key="seoul_map")


# 지도를 뷰포트 전체로 채우고, 입력 패널은 우측에 뜬 반투명 오버레이로 띄운다.
# panel은 position:fixed라 문서 흐름과 무관하게 항상 우측 상단에 고정된다 —
# 그래서 지도(정상 흐름)를 어디서 그리든 패널이 그 위에 뜬다.
FULLSCREEN_CSS = """
<style>
[data-testid="stHeader"] { display: none; }
[data-testid="stAppViewContainer"], [data-testid="stMain"] { padding: 0 !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }
/* 지도(js-plotly-plot) 자체는 100vh로 늘렸지만, Streamlit이 최초 렌더 크기
   (fig.layout.height=760)로 고정 inline height를 박아둔 조상 div들이 그대로
   남아 있어서 그 아래로 빈 칸이 생겼다 — 그 조상들만 콕 집어 같이 늘린다. */
[data-testid="stElementContainer"]:has(.js-plotly-plot),
[data-testid="stFullScreenFrame"]:has(.js-plotly-plot),
[data-testid="stVerticalBlock"]:has(.js-plotly-plot),
[data-testid="stMainBlockContainer"]:has(.js-plotly-plot),
[data-testid="stPlotlyChart"] {
    /* Streamlit이 flex-basis(예: 760px)를 height보다 우선 적용해두는 flex
       레이아웃이라, height만으로는 안 늘어난다 — flex도 같이 덮어써야 한다. */
    width: 100vw !important; height: 100vh !important;
    flex: 1 1 auto !important;
}
[data-testid="stVerticalBlock"]:has(.js-plotly-plot) {
    /* 같은 블록의 형제 요소(숨겨진 CSS 마크다운, position:fixed 패널)와의
       flex gap이 지도 높이만큼 빈 칸으로 남는 걸 막는다. */
    gap: 0 !important;
}
[data-testid="stPlotlyChart"] > div, .js-plotly-plot, .plot-container {
    width: 100vw !important; height: 100vh !important;
}
.st-key-panel {
    position: fixed; top: 0; right: 0;
    width: 380px; height: 100vh; overflow-y: auto;
    z-index: 1000;
    background: rgba(15, 16, 20, 0.82);
    backdrop-filter: blur(10px);
    padding: 1.4rem 1.2rem;
    box-shadow: -6px 0 24px rgba(0, 0, 0, 0.45);
}
</style>
"""


@st.fragment
def _app_body(geojson: dict) -> None:
    """앱 전체를 프래그먼트 하나로 감싼다.

    Streamlit은 위젯(텍스트 입력 blur, 셀렉트박스, 체크박스) 하나만 바뀌어도
    스크립트 전체를 처음부터 다시 실행하는 게 기본 동작이다. run_agent_cached/
    load_boundaries 등은 이미 st.cache_data라 재계산 자체는 공짜지만, "전체
    재실행"이라는 오버헤드 자체는 그대로 남는다. 위젯을 만드는 코드를 전부
    이 프래그먼트 안에 두면, 그중 뭘 누르든 이 함수만 다시 실행되고 바깥
    main()은 두 번 다시 돌지 않는다 — 그래서 매번 "처음부터" 도는 느낌이
    사라진다. (Streamlit 정책상 프래그먼트가 만든 위젯은 프래그먼트 밖에서
    만든 컨테이너에 못 넣으므로, panel 컨테이너도 이 안에서 새로 만든다.)

    단, 지도가 확대·이동해둔 위치까지 지켜주진 못한다 — Streamlit이 Plotly
    지도를 내용(색·핀)이 바뀔 때마다 완전히 새 컴포넌트로 마운트하는 동작이라
    (uirevision을 걸어도 이 조합에서는 카메라가 리셋됨, 직접 확인함), 그건
    커스텀 JS 브릿지 없이는 못 고치는 프레임워크 한계로 받아들인다.
    """
    panel = st.container(key="panel")
    with panel:
        st.subheader("살래말래")
        st.caption("필수는 하드 필터, 선택은 점수에 반영됩니다.")
        if using_mock_llm():
            st.caption(f"⚠ Mock LLM으로 동작 중 ({_mock_llm_reason()})")
        required_text = st.text_area(
            "필수 요구사항", placeholder="예: 헬스장, 대형병원 있어야 함", height=100)
        optional_text = st.text_area(
            "선택 요구사항", placeholder="예: 안전하고 조용한 곳, 지하철 가까운 곳", height=150)
        message_slot = st.empty()
        style_name = st.selectbox(
            "지도 스타일", list(MAP_STYLES), index=list(MAP_STYLES).index(DEFAULT_MAP_STYLE))
        show_core = st.checkbox("서울 핵심시설 표시", value=True)
    map_kw = dict(map_style=MAP_STYLES[style_name], show_core=show_core)

    if not required_text.strip() and not optional_text.strip():
        render_map(neutral_dataframe(geojson), geojson, **map_kw)
        return

    combined = f"필수 요구사항: {required_text}\n선택 요구사항: {optional_text}"
    result = run_agent_cached(combined, using_mock_llm(), PIPELINE_VERSION)

    if result["kind"] == "clarify":
        message_slot.warning(result["message"])
        render_map(neutral_dataframe(geojson), geojson, **map_kw)
        return

    message_slot.success(result["message"])
    data = result["data"]
    if data.get("unresolved_requirements"):
        with panel:
            st.warning("해석하지 못한 필수 조건 (필터 미적용): "
                       + ", ".join(data["unresolved_requirements"]))
    df = assign_tiers(data["recommendations"], data.get("disqualified", []))
    render_map(df, geojson, points=data.get("map_points"), **map_kw)

    with panel, st.expander("🔍 적용된 필터 검증"):
        st.caption(f"추천 {len(data['recommendations'])}개 / "
                   f"실격 {len(data.get('disqualified', []))}개 "
                   f"(파이프라인 v{PIPELINE_VERSION})")
        for line in result["trace"]:
            st.text(line)


def main() -> None:
    geojson = load_boundaries()
    st.markdown(FULLSCREEN_CSS, unsafe_allow_html=True)
    _app_body(geojson)


if __name__ == "__main__":
    main()
