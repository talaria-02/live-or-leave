"""
Mock LLM — 실제 HCX 호출을 대체하는 결정론적 스텁.

목적: LLM 없이도 ReAct 루프의 흐름(관측→판단→도구호출→종합)을
      끝까지 검증한다. 실제 구현에서는 이 클래스만 HCX 호출로 교체하면 된다.

입구/출구 두 역할을 규칙 기반으로 흉내낸다:
  - parse_intent: 자연어에서 키워드를 보고 중요도 라벨을 채운다.
  - explain: 추천지의 실제 지표 수치를 인용해 근거 문장을 만든다.
"""
from __future__ import annotations

from app.schemas.domain import CATEGORY_CAVEATS
from app.schemas.tools import (
    CategoryPreference,
    Importance,
    ParsedIntent,
)

# 키워드 → 카테고리 매핑 (실제 LLM의 의미 이해를 규칙으로 근사)
_KW = {
    "safety": ["안전", "밤", "치안", "범죄", "cctv", "무서"],
    "convenience": ["편의", "편의점", "마트", "병원", "장보", "쇼핑"],
    "mobility": ["지하철", "교통", "출퇴근", "야근", "차 없", "대중교통", "역"],
    "environment": ["공원", "산책", "조용", "자연", "녹지", "한적"],
}

_CATEGORY_LABEL = {"safety": "안전", "convenience": "편의", "mobility": "이동", "environment": "환경"}

# 자유 텍스트 → 실제 상권업종소분류명 매핑 (닫힌 집합만 사용, LLM이 새 라벨을 지어내지 않게)
_FACILITY_SYNONYMS: dict[str, list[str]] = {
    "버거": ["버거"],
    "햄버거": ["버거"],
    "치킨": ["치킨"],
    "피자": ["피자"],
    "카페": ["카페"],
    "커피": ["카페"],
    "헬스장": ["헬스장"],
    "헬스": ["헬스장"],
    "운동": ["헬스장", "수영장", "종합 스포츠시설"],
    "수영": ["수영장"],
}


class MockLLM:
    def parse_intent(self, text: str) -> ParsedIntent:
        t = text.lower()
        labels: dict[str, Importance] = {}
        for cat, kws in _KW.items():
            hit = sum(1 for k in kws if k in t)
            if hit >= 2:
                labels[cat] = Importance.VERY_HIGH
            elif hit == 1:
                labels[cat] = Importance.HIGH
            else:
                labels[cat] = Importance.NONE

        pref = CategoryPreference(**labels)
        require_hosp = ("대형병원" in text) or ("종합병원" in text)

        extra: list[str] = []
        for kw, categories in _FACILITY_SYNONYMS.items():
            if kw in t:
                for c in categories:
                    if c not in extra:
                        extra.append(c)

        # 4개 카테고리도 모호하고 언급된 업종도 없으면 성향 모호 → 되묻기
        if all(v == Importance.NONE for v in labels.values()) and not extra:
            return ParsedIntent(
                preference=pref,
                needs_clarification=True,
                clarify_question="어떤 점을 가장 중요하게 보세요? (안전 / 편의 / 교통 / 환경)",
            )
        return ParsedIntent(
            preference=pref, require_large_hospital=require_hosp, extra_categories=extra
        )

    def explain(self, user_text: str, result: dict) -> str:
        """출구 역할: 실제 수치 + 선택 근거(가중치·카테고리별 기여도)를 근거로 설명 생성."""
        recs = result["recommendations"]
        if not recs:
            return "조건에 맞는 지역을 찾지 못했습니다."

        weights = result.get("weights", {})
        priorities = [c for c, w in sorted(weights.items(), key=lambda x: -x[1]) if w > 0]
        priority_label = "·".join(_CATEGORY_LABEL.get(c, c) for c in priorities) or "모든 항목 균등"
        has_extra_facility = any(r.get("extra_facilities") for r in recs)

        lines = []
        for r in recs:
            raw = r["scores"]["raw"]
            contrib = r.get("contributions", {})
            drivers = [c for c, v in sorted(contrib.items(), key=lambda x: -x[1]) if v > 0]
            driver_label = ", ".join(
                f"{_CATEGORY_LABEL.get(c, c)} {contrib[c]}점 기여" for c in drivers[:2]
            ) or "전 항목 균형 기여"

            head = f"{r['gu']} {r['dong']} (종합 {r['total_score']})"
            basis = f"  ▶ 선택 근거: 중요 항목({priority_label}) 중 {driver_label}로 상위권"
            parts = [
                head,
                basis,
                f"  · 안전: 자치구 범죄율 {raw['crime_rate']}/만명, 반경1km CCTV {raw['cctv_cnt']}대",
                f"  · 편의: 편의점 {raw['conv_cnt']}·마트 {raw['mart_cnt']}·병원 {raw['hosp_cnt']} (반경1km)",
                f"  · 이동: 버스 {raw['bus_cnt']}개, 지하철 접근성 {raw['subway_access']}",
                f"  · 환경: 반경1km 공원 {raw['park_cnt']}곳",
            ]
            if "대형병원" in user_text and raw["hosp_cnt"] == 0:
                parts.append("  ※ 요청하신 대형병원이 반경 내 없습니다.")

            for cat, cnt in r.get("extra_facilities", {}).items():
                if cnt > 0:
                    parts.append(f"  · {cat}: 해당 행정동에 {cnt}곳")
                else:
                    parts.append(f"  ※ 요청하신 '{cat}' 관련 시설이 이 행정동에는 없어 반영되지 않았습니다.")
            lines.append("\n".join(parts))

        caveats = [CATEGORY_CAVEATS[c] for c in priorities if c in CATEGORY_CAVEATS]
        if has_extra_facility:
            caveats.append("직접 요청하신 업종은 반경 1km가 아니라 해당 행정동에 등록된 업소 수 기준입니다.")
        if caveats:
            lines.append("[데이터 안내]\n" + "\n".join(f"※ {c}" for c in caveats))
        return "\n\n".join(lines)
