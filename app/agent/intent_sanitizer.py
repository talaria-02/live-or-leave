"""Post-process LLM intent outputs to keep tool calls conservative.

The LLM is allowed to interpret natural language, but it must not invent
facility requirements from background facts such as occupation. This module
keeps only explicitly requested facility categories and forces clarification for
vague preference-only questions.
"""
from __future__ import annotations

import re

# UI가 "필수 요구사항:"/"선택 요구사항:" 구역으로 나눠 보낼 때 쓰는 마커.
# 마커가 없는 자유 문장은 전부 '선택 요구사항'으로 취급해 기존 동작을 그대로 유지한다.
REQUIRED_MARKER = "필수 요구사항"
OPTIONAL_MARKER = "선택 요구사항"


def split_required_optional(text: str) -> tuple[str, str]:
    """combined 텍스트를 (필수 구역, 선택 구역)으로 분리한다.

    mock_llm.py와 solar_llm.py가 공유한다 — 원래 각자 구현이 따로 있었는데,
    solar_llm.py 쪽이 이 분리 없이 전체 text를 그대로 검증에 써서 '선택
    요구사항'에만 적힌 업종(예: "공원")이 required_filters 존재-검증을
    통과해버리는 버그가 있었다(같은 단어가 텍스트 어딘가에 있기만 하면
    통과하는 explicitly_requested_categories의 특성상). 필수/선택 구역을
    먼저 나눠서 각 검증에 맞는 구역만 넘기면 이 오염이 원천 차단된다."""
    markers = [
        (idx, kind)
        for marker, kind in ((REQUIRED_MARKER, "required"), (OPTIONAL_MARKER, "optional"))
        for idx in [text.find(marker)]
        if idx != -1
    ]
    if not markers:
        return "", text
    markers.sort()
    sections = {"required": "", "optional": ""}
    for i, (idx, kind) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        sections[kind] = text[idx:end]
    return sections["required"], sections["optional"]


_FACILITY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "버거": ("버거", "햄버거"),
    "헬스장": ("헬스장", "헬스", "피트니스", "gym"),
    "카페": ("카페", "커피"),
    "수영장": ("수영장", "수영"),
    "종합 스포츠시설": ("종합 스포츠시설", "운동시설", "스포츠시설"),
    "동물병원": ("동물병원", "반려동물 병원", "반려견 병원", "반려묘 병원"),
    "치킨": ("치킨",),
    "피자": ("피자",),
}

_FACILITY_CONTEXT_WORDS = (
    "가깝", "근처", "주변", "있", "많", "인프라", "시설", "가기", "다니",
    "이용", "자주", "필요", "좋", "원해", "중요",
)

_CONCRETE_PREFERENCE_KEYWORDS = (
    "안전", "밤", "치안", "범죄", "cctv", "무서",
    "지하철", "버스", "교통", "대중교통", "출퇴근", "통근", "야근", "역",
    "병원", "대형병원", "종합병원", "마트", "편의점", "장보", "쇼핑",
    "공원", "산책", "녹지", "자연", "러닝", "헬스", "운동",
    "카페", "버거", "햄버거", "반려동물", "동물병원",
    "조용", "방음", "소음", "주거비", "예산", "저렴", "부담", "시세", "통근시간",
    "남향", "채광", "주차", "학군", "어린이집", "학교",
)

_VAGUE_PATTERNS = (
    "잘 맞는",
    "괜찮",
    "살기 좋은",
    "좋은 동네",
    "아무 데",
    "아무데",
    "마음이",
    "편해지는",
    "삭막하지",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def _category_terms(category: str) -> tuple[str, ...]:
    terms = [category]
    compact = category.replace(" ", "")
    if compact != category:
        terms.append(compact)
    terms.extend(_FACILITY_SYNONYMS.get(category, ()))
    return tuple(dict.fromkeys(term for term in terms if term))


def explicitly_requested_categories(text: str, categories: list[str]) -> list[str]:
    """Keep categories whose label/synonym is explicitly present in the text.

    Generic words such as "편의", occupation words such as "회계사", or inferred
    adjacent professions such as "세무사" must not become facility categories.
    """
    normalized_text = _normalize(text)
    kept: list[str] = []
    for category in categories:
        for term in _category_terms(category):
            if _normalize(term) in normalized_text:
                kept.append(category)
                break
    return kept


def has_explicit_facility_request(text: str, categories: list[str]) -> bool:
    if explicitly_requested_categories(text, categories):
        return True
    t = text.lower()
    return any(word in t for word in _FACILITY_CONTEXT_WORDS) and any(
        term in t for terms in _FACILITY_SYNONYMS.values() for term in terms
    )


def has_concrete_preference(text: str, categories: list[str] | None = None) -> bool:
    t = text.lower()
    if any(keyword in t for keyword in _CONCRETE_PREFERENCE_KEYWORDS):
        return True
    if categories and has_explicit_facility_request(text, categories):
        return True
    return False


def should_force_clarification(text: str, categories: list[str] | None = None) -> bool:
    t = text.lower()
    if not any(pattern in t for pattern in _VAGUE_PATTERNS):
        return False
    return not has_concrete_preference(text, categories)


def explicitly_requires_large_hospital(text: str) -> bool:
    t = text.lower()
    return any(term in t for term in ("대형병원", "종합병원", "큰 병원", "상급종합병원"))
