"""agent/mock_llm.py 단위 테스트 (키워드 매칭 규칙 검증)."""
from __future__ import annotations

from app.agent.mock_llm import MockLLM
from app.schemas.tools import Importance


def test_two_or_more_keyword_hits_yield_very_high():
    intent = MockLLM().parse_intent("안전하고 무서운 밤길이 걱정돼요")
    assert intent.preference.safety == Importance.VERY_HIGH
    assert intent.preference.convenience == Importance.NONE
    assert intent.preference.mobility == Importance.NONE
    assert intent.preference.environment == Importance.NONE
    assert intent.needs_clarification is False


def test_single_keyword_hit_yields_high():
    intent = MockLLM().parse_intent("병원 근처가 좋아요")
    assert intent.preference.convenience == Importance.HIGH
    assert intent.preference.safety == Importance.NONE
    assert intent.preference.mobility == Importance.NONE
    assert intent.preference.environment == Importance.NONE


def test_no_keyword_hits_triggers_clarification():
    intent = MockLLM().parse_intent("오늘 날씨가 좋네요")
    assert intent.needs_clarification is True
    assert intent.clarify_question
    assert all(v == Importance.NONE for v in intent.preference.model_dump().values())


def test_large_hospital_keyword_sets_require_flag():
    intent = MockLLM().parse_intent("대형병원 근처였으면 좋겠어요")
    assert intent.require_large_hospital is True


def test_no_hospital_keyword_leaves_flag_false():
    intent = MockLLM().parse_intent("편의점 많은 동네가 좋아요")
    assert intent.require_large_hospital is False


def test_multiple_categories_can_be_detected_simultaneously():
    intent = MockLLM().parse_intent("안전하고 무서운 밤길 말고, 공원 산책하기 좋은 조용한 동네")
    assert intent.preference.safety == Importance.VERY_HIGH
    assert intent.preference.environment == Importance.VERY_HIGH
    assert intent.needs_clarification is False


# ---------- extra_categories (임의 업종) ----------

def test_facility_synonym_maps_free_text_to_real_category_label():
    intent = MockLLM().parse_intent("버거집 있는 동네가 좋아요")
    assert intent.extra_categories == ["버거"]
    assert intent.needs_clarification is False


def test_facility_synonym_expands_one_word_to_multiple_categories():
    intent = MockLLM().parse_intent("운동할 수 있는 곳이 있었으면")
    assert set(intent.extra_categories) == {"헬스장", "수영장", "종합 스포츠시설"}


def test_facility_only_request_does_not_trigger_clarification():
    """4개 카테고리 언급이 전혀 없어도 업종이 언급됐으면 되묻지 않아야 한다."""
    intent = MockLLM().parse_intent("헬스장 있는 곳")
    assert intent.needs_clarification is False


def test_no_facility_keyword_leaves_extra_categories_empty():
    intent = MockLLM().parse_intent("안전한 동네가 좋아요")
    assert intent.extra_categories == []


# ---------- 필수/선택 요구사항 구조화 입력 ----------

def test_required_section_becomes_hard_filter_not_score():
    text = "필수 요구사항: 헬스장\n선택 요구사항: 안전하고 무서운 밤길 없는 조용한 동네"
    intent = MockLLM().parse_intent(text)
    assert intent.required_categories == ["헬스장"]
    assert "헬스장" not in intent.extra_categories
    assert intent.preference.safety == Importance.VERY_HIGH
    assert intent.preference.environment != Importance.NONE


def test_optional_section_keywords_do_not_leak_into_required():
    text = "필수 요구사항: 버거\n선택 요구사항: 헬스장 있으면 좋겠어요"
    intent = MockLLM().parse_intent(text)
    assert intent.required_categories == ["버거"]
    assert intent.extra_categories == ["헬스장"]


def test_marker_order_can_be_reversed():
    text = "선택 요구사항: 안전하고 무서운 밤길 없는 곳\n필수 요구사항: 헬스장"
    intent = MockLLM().parse_intent(text)
    assert intent.required_categories == ["헬스장"]
    assert intent.preference.safety == Importance.VERY_HIGH


def test_no_markers_treats_whole_text_as_optional_backward_compat():
    """마커 없는 자유 문장은 기존처럼 전부 선택(점수화) 요구사항으로 취급된다."""
    intent = MockLLM().parse_intent("헬스장 있는 곳")
    assert intent.required_categories == []
    assert intent.extra_categories == ["헬스장"]


def test_required_only_with_no_optional_keywords_does_not_trigger_clarification():
    intent = MockLLM().parse_intent("필수 요구사항: 헬스장\n선택 요구사항: ")
    assert intent.needs_clarification is False
    assert intent.required_categories == ["헬스장"]


# ---------- explain ----------

def test_explain_no_recommendations_returns_fixed_message():
    msg = MockLLM().explain("아무 텍스트", {"recommendations": []})
    assert msg == "조건에 맞는 지역을 찾지 못했습니다."


def _fake_result(hosp_cnt: int, weights: dict | None = None,
                  contributions: dict | None = None) -> dict:
    raw = dict(crime_rate=1.0, cctv_cnt=2, conv_cnt=3, mart_cnt=4,
               hosp_cnt=hosp_cnt, bus_cnt=5, subway_access=0.7, park_cnt=6)
    rec = {"gu": "강남구", "dong": "역삼동", "total_score": 0.5, "scores": {"raw": raw}}
    if contributions is not None:
        rec["contributions"] = contributions
    result = {"recommendations": [rec]}
    if weights is not None:
        result["weights"] = weights
    return result


def test_explain_includes_raw_metric_values():
    msg = MockLLM().explain("조용한 동네", _fake_result(hosp_cnt=1))
    assert "강남구 역삼동" in msg
    assert "CCTV 2대" in msg
    assert "편의점 3" in msg
    assert "마트 4" in msg
    assert "버스 5개" in msg
    assert "공원 6곳" in msg


def test_explain_flags_missing_large_hospital():
    msg = MockLLM().explain("대형병원 근처였으면", _fake_result(hosp_cnt=0))
    assert "요청하신 대형병원이 반경 내 없습니다." in msg


def test_explain_no_warning_when_hospital_present():
    msg = MockLLM().explain("대형병원 근처였으면", _fake_result(hosp_cnt=1))
    assert "요청하신 대형병원이 반경 내 없습니다." not in msg


def test_explain_states_selection_basis_from_weights_and_contributions():
    result = _fake_result(
        hosp_cnt=1,
        weights={"safety": 0.5, "mobility": 0.5, "convenience": 0.0, "environment": 0.0},
        contributions={"safety": 0.4, "mobility": 0.3, "convenience": 0.0, "environment": 0.0},
    )
    msg = MockLLM().explain("안전하고 이동 편한 곳", result)
    assert "선택 근거" in msg
    assert "안전" in msg and "이동" in msg
    assert "0.4" in msg and "0.3" in msg  # 실제 기여도 수치가 근거로 언급됨
    assert "편의" not in msg.split("선택 근거")[1].split("\n")[0]  # 무관한 항목은 근거에서 제외


def test_explain_falls_back_gracefully_without_weights_or_contributions():
    """weights/contributions가 없어도(구버전 호출) 죽지 않고 균형 문구로 대체돼야 한다."""
    msg = MockLLM().explain("아무 텍스트", _fake_result(hosp_cnt=1))
    assert "선택 근거" in msg


def test_explain_appends_caveat_for_prioritized_category():
    result = _fake_result(hosp_cnt=1, weights={
        "safety": 1.0, "convenience": 0.0, "mobility": 0.0, "environment": 0.0})
    msg = MockLLM().explain("안전한 곳", result)
    assert "[데이터 안내]" in msg
    assert "자치구 값을 공통 적용" in msg  # safety 각주 (구 상속)


def test_explain_omits_caveats_for_categories_the_user_did_not_prioritize():
    result = _fake_result(hosp_cnt=1, weights={
        "safety": 1.0, "convenience": 0.0, "mobility": 0.0, "environment": 0.0})
    msg = MockLLM().explain("안전한 곳", result)
    assert "최근접 역까지 거리" not in msg  # mobility 각주는 언급 안 됨


def test_explain_has_no_caveat_block_when_no_weights_given():
    msg = MockLLM().explain("아무 텍스트", _fake_result(hosp_cnt=1))
    assert "[데이터 안내]" not in msg


def test_explain_reports_extra_facility_count_when_present():
    result = _fake_result(hosp_cnt=1)
    result["recommendations"][0]["extra_facilities"] = {"버거": 3}
    msg = MockLLM().explain("버거집 있는 곳", result)
    assert "버거: 해당 행정동에 3곳" in msg


def test_explain_flags_extra_facility_not_found():
    result = _fake_result(hosp_cnt=1)
    result["recommendations"][0]["extra_facilities"] = {"헬스장": 0}
    msg = MockLLM().explain("헬스장 있는 곳", result)
    assert "요청하신 '헬스장' 관련 시설이 이 행정동에는 없어 반영되지 않았습니다." in msg


def test_explain_notes_extra_facility_counting_methodology():
    result = _fake_result(hosp_cnt=1)
    result["recommendations"][0]["extra_facilities"] = {"버거": 2}
    msg = MockLLM().explain("버거집 있는 곳", result)
    assert "해당 행정동에 등록된 업소 수 기준" in msg


def test_explain_no_extra_facility_note_when_not_requested():
    msg = MockLLM().explain("안전한 곳", _fake_result(hosp_cnt=1))
    assert "등록된 업소 수 기준" not in msg
