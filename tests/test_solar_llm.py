"""agent/solar_llm.py 단위 테스트.

parse_intent/explain의 파싱·폴백·전달 로직 자체는 _call의 반환값에만 의존하므로,
monkeypatch로 _call을 대체해 그 로직을 _call 구현(LiteLLM 경유 Solar 호출)과
독립적으로 검증한다. _call 자체의 LiteLLM 연동은 별도 테스트에서 확인한다.
"""
from __future__ import annotations

import json
import sys
import types

import pytest

from app.agent.solar_llm import SolarLLM
from app.schemas.tools import Importance


def _stub_call(monkeypatch, response: str):
    monkeypatch.setattr(SolarLLM, "_call", lambda self, system, user: response)


def test_call_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        SolarLLM()._call("system", "user")


def test_call_invokes_litellm_with_solar_openai_compatible_endpoint(monkeypatch):
    captured = {}

    class _FakeMessage:
        content = "solar 응답"

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(completion=fake_completion))
    monkeypatch.setenv("UPSTAGE_API_KEY", "test-key")

    result = SolarLLM()._call("system", "user")

    assert result == "solar 응답"
    assert captured["model"] == "openai/solar-pro2-251215"
    assert captured["api_base"] == "https://api.upstage.ai/v1"
    assert captured["api_key"] == "test-key"
    assert captured["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
    ]
    assert captured["num_retries"] == 2  # 일시적 connection error 대비 재시도


# ---------- _call_stream (SSE용) ----------

def test_call_stream_raises_without_api_key(monkeypatch):
    """제너레이터라 함수 호출 자체는 안 터지고, 반복(iterate)할 때 터진다."""
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    gen = SolarLLM()._call_stream("system", "user")
    with pytest.raises(RuntimeError):
        next(gen)


def test_call_stream_yields_chunks_via_litellm(monkeypatch):
    captured = {}

    class _FakeDelta:
        def __init__(self, content):
            self.content = content

    class _FakeChoice:
        def __init__(self, content):
            self.delta = _FakeDelta(content)

    class _FakeChunk:
        def __init__(self, content):
            self.choices = [_FakeChoice(content)]

    def fake_completion(**kwargs):
        captured.update(kwargs)
        # 중간에 delta.content가 None인 청크(빈 하트비트 등)도 섞어서 걸러지는지 확인
        return iter([_FakeChunk("안녕"), _FakeChunk(None), _FakeChunk("하세요")])

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(completion=fake_completion))
    monkeypatch.setenv("UPSTAGE_API_KEY", "test-key")

    chunks = list(SolarLLM()._call_stream("system", "user"))

    assert chunks == ["안녕", "하세요"]
    assert captured["stream"] is True
    assert captured["num_retries"] == 2
    assert captured["model"] == "openai/solar-pro2-251215"


# ---------- explain_stream ----------

def test_explain_stream_short_circuits_on_empty_recommendations():
    chunks = list(SolarLLM().explain_stream("아무 문장", {"recommendations": []}))
    assert chunks == ["조건에 맞는 지역을 찾지 못했습니다."]


def test_explain_stream_yields_call_stream_chunks(monkeypatch):
    monkeypatch.setattr(SolarLLM, "_call_stream", lambda self, system, user: iter(["a", "b", "c"]))
    chunks = list(SolarLLM().explain_stream("아무 문장", _fake_result()))
    assert chunks == ["a", "b", "c"]


# ---------- parse_intent: _call 자체가 실패하는 경우 (예: API 키 미설정) ----------

def test_parse_intent_propagates_when_call_raises(monkeypatch):
    """_call 예외는 try/except 바깥에서 일어나므로 그대로 전파된다."""
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        SolarLLM().parse_intent("아무 문장")


# ---------- parse_intent: _call은 성공했지만 응답이 잘못된 경우 ----------

def test_parse_intent_falls_back_when_response_is_not_json(monkeypatch):
    _stub_call(monkeypatch, "이건 JSON이 아닙니다")
    intent = SolarLLM().parse_intent("아무 문장")
    assert intent.needs_clarification is True
    assert intent.clarify_question
    assert all(v == Importance.NONE for v in intent.preference.model_dump().values())


def test_parse_intent_falls_back_when_label_is_invalid(monkeypatch):
    _stub_call(monkeypatch, json.dumps({
        "safety": "극단적으로중요", "convenience": "none",
        "mobility": "none", "environment": "none",
    }))
    intent = SolarLLM().parse_intent("아무 문장")
    assert intent.needs_clarification is True


# ---------- parse_intent: 정상 JSON 응답 ----------

def test_parse_intent_parses_valid_json_response(monkeypatch):
    _stub_call(monkeypatch, json.dumps({
        "safety": "very_high", "convenience": "none",
        "mobility": "medium", "environment": "none",
        "require_large_hospital": True,
        "needs_clarification": False, "clarify_question": None,
    }))
    intent = SolarLLM().parse_intent("안전하고 대형병원 있는 곳")
    assert intent.preference.safety == Importance.VERY_HIGH
    assert intent.preference.mobility == Importance.MEDIUM
    assert intent.require_large_hospital is True
    assert intent.needs_clarification is False


def test_parse_intent_strips_markdown_code_fence(monkeypatch):
    _stub_call(monkeypatch, "```json\n" + json.dumps({
        "safety": "none", "convenience": "high",
        "mobility": "none", "environment": "none",
    }) + "\n```")
    intent = SolarLLM().parse_intent("편의점 많은 곳")
    assert intent.preference.convenience == Importance.HIGH


class _FakeFacilityRepo:
    def categories(self):
        return {"버거", "헬스장"}


def test_parse_intent_extracts_extra_categories_within_closed_set(monkeypatch):
    monkeypatch.setattr("app.agent.solar_llm.get_facility_repository", lambda: _FakeFacilityRepo())
    _stub_call(monkeypatch, json.dumps({
        "safety": "none", "convenience": "none", "mobility": "none", "environment": "none",
        "extra_categories": ["버거", "존재하지않는업종"],
    }))
    intent = SolarLLM().parse_intent("버거집 있는 곳")
    assert intent.extra_categories == ["버거"]  # 닫힌 집합 밖은 걸러짐


def test_parse_intent_accepts_open_keywords_for_required_categories(monkeypatch):
    """필수 업종은 extra와 달리 닫힌 집합 필터를 통과하지 않는다 — CSV 밖 시설
    ('클라이밍장' 등)은 Kakao 좌표검색으로 해석되므로 열린 키워드 그대로 보존."""
    _stub_call(monkeypatch, json.dumps({
        "safety": "none", "convenience": "none", "mobility": "none", "environment": "none",
        "required_categories": ["클라이밍장", " 도서관 ", "", "클라이밍장"],
    }))
    intent = SolarLLM().parse_intent("클라이밍장이랑 도서관 꼭 있어야 해요")
    assert intent.required_categories == ["클라이밍장", "도서관"]  # 공백 정리·중복·빈값 제거


def test_parse_intent_separates_required_near_from_required_categories(monkeypatch):
    """'서울대 근처'는 거리 필터(required_near)로만 — LLM이 지시를 어기고
    required_categories에도 중복시키면 코드가 걸러내야 한다 (이름 매칭
    노이즈 필터가 되는 걸 방지)."""
    _stub_call(monkeypatch, json.dumps({
        "safety": "none", "convenience": "none", "mobility": "none", "environment": "none",
        "required_categories": ["서울대", "클라이밍"],
        "required_near": ["서울대"],
    }))
    intent = SolarLLM().parse_intent("서울대 근처에 클라이밍장 있는 곳")
    assert intent.required_near == ["서울대"]
    assert intent.required_categories == ["클라이밍"]  # 중복 제거됨


def test_parse_intent_caps_required_categories_at_five(monkeypatch):
    _stub_call(monkeypatch, json.dumps({
        "safety": "none", "convenience": "none", "mobility": "none", "environment": "none",
        "required_categories": [f"업종{i}" for i in range(10)],
    }))
    intent = SolarLLM().parse_intent("이것저것 다 필요해요")
    assert len(intent.required_categories) == 5


# ---------- explain ----------

def test_explain_short_circuits_on_empty_recommendations():
    """추천이 비어 있으면 _call을 호출하지 않고 고정 문구를 반환해야 한다."""
    msg = SolarLLM().explain("아무 문장", {"recommendations": []})
    assert msg == "조건에 맞는 지역을 찾지 못했습니다."


def _fake_result() -> dict:
    raw = dict(crime_rate=1.0, cctv_cnt=1, conv_cnt=1, mart_cnt=1,
               hosp_cnt=1, bus_cnt=1, subway_access=0.5, park_cnt=1)
    return {"recommendations": [{
        "gu": "강남구", "dong": "역삼동", "total_score": 0.5, "scores": {"raw": raw},
    }]}


def test_explain_propagates_call_failure_when_recommendations_exist(monkeypatch):
    """explain은 parse_intent와 달리 _call 실패를 폴백 없이 그대로 전파한다 (현재 구현)."""
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        SolarLLM().explain("아무 문장", _fake_result())


def test_explain_returns_call_result_when_recommendations_exist(monkeypatch):
    _stub_call(monkeypatch, "생성된 설명 텍스트")
    msg = SolarLLM().explain("아무 문장", _fake_result())
    assert msg == "생성된 설명 텍스트"


def test_explain_passes_weights_and_contributions_into_the_prompt(monkeypatch):
    """LLM이 '선택 근거'를 말하려면 가중치·기여도가 프롬프트에 실려 있어야 한다."""
    captured = {}

    def fake_call(self, system, user):
        captured["system"] = system
        captured["user"] = user
        return "설명"

    monkeypatch.setattr(SolarLLM, "_call", fake_call)
    result = {
        "weights": {"safety": 1.0, "convenience": 0.0, "mobility": 0.0, "environment": 0.0},
        "recommendations": [{
            "gu": "강남구", "dong": "역삼동", "total_score": 0.9,
            "contributions": {"safety": 0.9, "convenience": 0.0, "mobility": 0.0, "environment": 0.0},
            "scores": {"raw": dict(crime_rate=1.0, cctv_cnt=1, conv_cnt=1, mart_cnt=1,
                                    hosp_cnt=1, bus_cnt=1, subway_access=0.5, park_cnt=1)},
        }],
    }
    SolarLLM().explain("안전한 곳", result)
    assert "safety" in captured["user"] and "0.9" in captured["user"]
    assert "기여도" in captured["system"]


def test_explain_includes_caveat_only_for_prioritized_categories(monkeypatch):
    captured = {}

    def fake_call(self, system, user):
        captured["user"] = user
        return "설명"

    monkeypatch.setattr(SolarLLM, "_call", fake_call)
    result = {
        "weights": {"safety": 1.0, "convenience": 0.0, "mobility": 0.0, "environment": 0.0},
        "recommendations": [{
            "gu": "강남구", "dong": "역삼동", "total_score": 0.9,
            "contributions": {"safety": 0.9, "convenience": 0.0, "mobility": 0.0, "environment": 0.0},
            "scores": {"raw": dict(crime_rate=1.0, cctv_cnt=1, conv_cnt=1, mart_cnt=1,
                                    hosp_cnt=1, bus_cnt=1, subway_access=0.5, park_cnt=1)},
        }],
    }
    SolarLLM().explain("안전한 곳", result)
    assert "자치구 값을 공통 적용" in captured["user"]
    assert "최근접 역까지 거리" not in captured["user"]


def test_explain_includes_extra_facility_status_and_caveat(monkeypatch):
    captured = {}

    def fake_call(self, system, user):
        captured["user"] = user
        return "설명"

    monkeypatch.setattr(SolarLLM, "_call", fake_call)
    result = {
        "weights": {"safety": 0.0, "convenience": 0.0, "mobility": 0.0,
                    "environment": 0.0, "버거": 1.0},
        "recommendations": [{
            "gu": "강남구", "dong": "역삼동", "total_score": 0.5,
            "contributions": {"버거": 0.5},
            "extra_facilities": {"버거": 0},
            "scores": {"raw": dict(crime_rate=1.0, cctv_cnt=1, conv_cnt=1, mart_cnt=1,
                                    hosp_cnt=1, bus_cnt=1, subway_access=0.5, park_cnt=1)},
        }],
    }
    SolarLLM().explain("버거집 있는 곳", result)
    assert "요청 업종 현황" in captured["user"]
    assert "행정동에 등록된 업소 수 기준" in captured["user"]
