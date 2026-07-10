"""streamlit_app.py의 mock/실 LLM 전환 로직 단위 테스트.

load_agent/using_mock_llm/_mock_llm_reason은 os.environ만으로 분기하는
순수 로직이라 실제 Streamlit 런타임(스크립트 실행 컨텍스트) 없이도
검증할 수 있다. 다만 load_agent는 @st.cache_resource가 걸려 있어 테스트
간 캐시가 새면 이전 호출의 인스턴스가 그대로 반환된다 — 매 테스트 전
캐시를 비운다.

관점:
  - 기능(정상 분기): 키 유무 × STREAMLIT_USE_MOCK_LLM 유무 4가지 조합
  - 경계값: 빈 문자열로 설정된 환경변수는 os.environ.get이 truthy가
    아니므로(bool("") == False) "설정 안 함"과 동일하게 취급된다 —
    직관과 다를 수 있는 실제 동작을 문서화
  - 보안: _mock_llm_reason()이 실제 API 키 값을 절대 노출하지 않는지
"""
from __future__ import annotations

import pytest

import streamlit_app
from app.agent.mock_llm import MockLLM


@pytest.fixture(autouse=True)
def _clear_agent_cache():
    """load_agent()는 @st.cache_resource, run_agent_cached()는 @st.cache_data라
    테스트마다 새로 분기시키려면 이전 호출의 캐시를 비워야 한다."""
    streamlit_app.load_agent.clear()
    streamlit_app.run_agent_cached.clear()
    yield
    streamlit_app.load_agent.clear()
    streamlit_app.run_agent_cached.clear()


# ---------- using_mock_llm(): 키 유무 × 강제 mock 4가지 조합 ----------

def test_using_mock_llm_true_when_no_key(monkeypatch):
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    monkeypatch.delenv("STREAMLIT_USE_MOCK_LLM", raising=False)
    assert streamlit_app.using_mock_llm() is True


def test_using_mock_llm_false_when_key_present_and_not_forced(monkeypatch):
    monkeypatch.setenv("UPSTAGE_API_KEY", "real-key")
    monkeypatch.delenv("STREAMLIT_USE_MOCK_LLM", raising=False)
    assert streamlit_app.using_mock_llm() is False


def test_using_mock_llm_true_when_key_present_but_forced(monkeypatch):
    monkeypatch.setenv("UPSTAGE_API_KEY", "real-key")
    monkeypatch.setenv("STREAMLIT_USE_MOCK_LLM", "1")
    assert streamlit_app.using_mock_llm() is True


def test_using_mock_llm_true_when_no_key_and_forced(monkeypatch):
    """키도 없고 강제 플래그도 있는 경우 — 두 조건 중 하나만 있어도 mock이어야 한다."""
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    monkeypatch.setenv("STREAMLIT_USE_MOCK_LLM", "1")
    assert streamlit_app.using_mock_llm() is True


# ---------- 경계값: 빈 문자열 환경변수 ----------

def test_using_mock_llm_empty_string_flag_does_not_force_mock(monkeypatch):
    """STREAMLIT_USE_MOCK_LLM=''(빈 문자열)은 '설정함'이 아니라 '설정 안 함'과 같다
    (bool("") == False). set이냐 unset이냐가 아니라 값의 진리성으로 판단하는
    현재 구현의 실제 동작 — 셸에서 `STREAMLIT_USE_MOCK_LLM= streamlit run ...`처럼
    빈 값으로 export해도 강제 mock이 켜지지 않는다는 뜻."""
    monkeypatch.setenv("UPSTAGE_API_KEY", "real-key")
    monkeypatch.setenv("STREAMLIT_USE_MOCK_LLM", "")
    assert streamlit_app.using_mock_llm() is False


# ---------- _mock_llm_reason(): 사유 문구 + 키 노출 금지 ----------

def test_mock_llm_reason_reports_missing_key(monkeypatch):
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    assert streamlit_app._mock_llm_reason() == "UPSTAGE_API_KEY 없음"


def test_mock_llm_reason_reports_forced_flag_when_key_present(monkeypatch):
    monkeypatch.setenv("UPSTAGE_API_KEY", "real-key")
    monkeypatch.setenv("STREAMLIT_USE_MOCK_LLM", "1")
    assert streamlit_app._mock_llm_reason() == "STREAMLIT_USE_MOCK_LLM 설정됨"


def test_mock_llm_reason_never_leaks_the_actual_api_key(monkeypatch):
    """화면에 그대로 노출되는 캡션 문구이므로, 키 값 자체가 절대 섞여 들어가면 안 된다."""
    secret = "up_9gHwvBT5FPWMm55dxRcTO6SUmFWt1"
    monkeypatch.setenv("UPSTAGE_API_KEY", secret)
    monkeypatch.setenv("STREAMLIT_USE_MOCK_LLM", "1")
    assert secret not in streamlit_app._mock_llm_reason()


# ---------- load_agent(): 실제 분기 결과(agent.llm 타입)까지 확인 ----------

def test_load_agent_uses_mock_llm_when_no_key(monkeypatch):
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    agent = streamlit_app.load_agent()
    assert isinstance(agent.llm, MockLLM)


def test_load_agent_uses_mock_llm_when_forced_despite_key(monkeypatch):
    monkeypatch.setenv("UPSTAGE_API_KEY", "real-key")
    monkeypatch.setenv("STREAMLIT_USE_MOCK_LLM", "1")
    agent = streamlit_app.load_agent()
    assert isinstance(agent.llm, MockLLM)


def test_load_agent_uses_real_llm_when_key_present_and_not_forced(monkeypatch):
    """실 API를 호출하지는 않는다 — SolarLLM 생성자는 키를 읽어 저장만 하고
    네트워크 요청은 parse_intent/explain 호출 시점에야 일어난다."""
    monkeypatch.setenv("UPSTAGE_API_KEY", "real-key")
    monkeypatch.delenv("STREAMLIT_USE_MOCK_LLM", raising=False)
    agent = streamlit_app.load_agent()
    assert not isinstance(agent.llm, MockLLM)
    assert agent.llm.api_key == "real-key"


# ---------- assign_tiers(): 지도 완전성 — 실격 동도 전부 그려야 함 ----------

def test_assign_tiers_renders_every_disqualified_dong():
    """실격 동을 일부만 그리면 나머지가 지도에서 통째로 사라져 구멍이 뚫린다.
    필수 필터로 수백 개가 실격돼도(예: 클라이밍장 없는 동 333개) 전부
    disqualified 티어로 포함돼야 한다."""
    recs = [{
        "gu": "강남구", "dong": f"추천{i}동", "total_score": 0.9 - i * 0.01,
        "scores": {"code": f"R{i}", "raw": dict(
            crime_rate=1.0, cctv_cnt=1, conv_cnt=1, mart_cnt=1,
            hosp_cnt=1, bus_cnt=1, subway_access=0.5, park_cnt=1)},
    } for i in range(3)]
    disq = [{"code": f"D{i}", "gu": "강북구", "dong": f"실격{i}동", "missing": ["클라이밍"]}
            for i in range(300)]

    df = streamlit_app.assign_tiers(recs, disq)

    assert len(df) == 3 + 300  # 하나도 빠지면 안 됨
    assert (df["tier"] == "disqualified").sum() == 300


# ---------- run_agent_cached(): 같은 입력이면 LLM 재호출 금지 ----------

def test_run_agent_cached_calls_llm_only_once_for_same_input(monkeypatch):
    """Streamlit rerun마다 같은 텍스트로 parse_intent+explain이 재호출되는 걸
    막는 게 이 캐시의 존재 이유다. 같은 (텍스트, mock여부) 키로 두 번 불러도
    agent.run은 한 번만 실행돼야 한다."""
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    calls = {"n": 0}
    real_run = streamlit_app.RecommendationAgent.run

    def counting_run(self, user_text, top_n=3):
        calls["n"] += 1
        return real_run(self, user_text, top_n=top_n)

    monkeypatch.setattr(streamlit_app.RecommendationAgent, "run", counting_run)
    v = streamlit_app.PIPELINE_VERSION
    streamlit_app.run_agent_cached("필수 요구사항: \n선택 요구사항: 안전한 곳", False, v)
    streamlit_app.run_agent_cached("필수 요구사항: \n선택 요구사항: 안전한 곳", False, v)
    assert calls["n"] == 1


def test_run_agent_cached_distinguishes_mock_flag_in_cache_key(monkeypatch):
    """mock으로 계산한 결과가 실 LLM 모드에서 재사용되면 안 되므로
    mock 여부가 캐시 키에 포함돼야 한다 — 같은 텍스트라도 플래그가 다르면 재실행."""
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    calls = {"n": 0}
    real_run = streamlit_app.RecommendationAgent.run

    def counting_run(self, user_text, top_n=3):
        calls["n"] += 1
        return real_run(self, user_text, top_n=top_n)

    monkeypatch.setattr(streamlit_app.RecommendationAgent, "run", counting_run)
    v = streamlit_app.PIPELINE_VERSION
    streamlit_app.run_agent_cached("필수 요구사항: \n선택 요구사항: 안전한 곳", True, v)
    streamlit_app.run_agent_cached("필수 요구사항: \n선택 요구사항: 안전한 곳", False, v)
    assert calls["n"] == 2


def test_run_agent_cached_invalidates_on_pipeline_version_bump(monkeypatch):
    """하위 모듈(필터·스코어링) 코드가 바뀌어도 st.cache_data는 모른다 —
    PIPELINE_VERSION을 키에 넣어 버전이 오르면 낡은 결과를 버리게 한다."""
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    calls = {"n": 0}
    real_run = streamlit_app.RecommendationAgent.run

    def counting_run(self, user_text, top_n=3):
        calls["n"] += 1
        return real_run(self, user_text, top_n=top_n)

    monkeypatch.setattr(streamlit_app.RecommendationAgent, "run", counting_run)
    streamlit_app.run_agent_cached("필수 요구사항: \n선택 요구사항: 안전한 곳", False, 1)
    streamlit_app.run_agent_cached("필수 요구사항: \n선택 요구사항: 안전한 곳", False, 2)
    assert calls["n"] == 2


def test_load_agent_result_is_cached_across_calls(monkeypatch):
    """st.cache_resource이므로 같은 프로세스 내 재호출은 새 인스턴스를 만들지 않고
    캐시된 동일 객체를 반환해야 한다 (매 rerun마다 에이전트를 새로 만들지 않기 위함)."""
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    first = streamlit_app.load_agent()
    second = streamlit_app.load_agent()
    assert first is second
