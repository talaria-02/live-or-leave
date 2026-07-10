"""
Upstage Solar API 어댑터 — RecommendationAgent(loop.py)의 기본 LLM 구현.

mock_llm.MockLLM과 동일한 인터페이스(parse_intent, explain)를 구현한다.
MockLLM은 프로덕션 경로에서는 더 이상 쓰이지 않고(실제 Solar API 검증 완료),
테스트에서 RecommendationAgent(llm=MockLLM())처럼 명시적으로 주입할 때만 쓰인다.

교체 원칙 (HANDOFF.md 설계원칙 2·3 준수):
  - parse_intent: LLM은 4단계 라벨만 출력. 숫자 생성 금지.
  - explain: 제공된 수치만 근거로. 수치에 없는 내용 추측 금지.
  - 파싱 실패 폴백·합=1 정규화는 서비스 계층(scoring)이 이미 처리.

Solar API는 OpenAI 호환 엔드포인트(https://api.upstage.ai/v1)라 LiteLLM의
openai-compatible 경유(model="openai/<모델명>", api_base 지정)로 호출한다.
litellm import는 _call 안에서 지연 로딩해, 패키지가 없어도 이 모듈을
import하는 데는 지장이 없게 한다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.data.facility_repository import get_facility_repository
from app.schemas.domain import CATEGORY_CAVEATS
from app.schemas.tools import (
    CategoryPreference,
    Importance,
    ParsedIntent,
)

# 프로젝트 루트의 .env (없으면 조용히 무시됨) — UPSTAGE_API_KEY 등을 여기서 읽는다.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DEFAULT_MODEL = "solar-pro2-251215"
DEFAULT_API_BASE = "https://api.upstage.ai/v1"

_PARSE_SYSTEM_BASE = """사용자의 동네 선호를 분석해 아래 4개 카테고리의 중요도를
각각 very_high / high / medium / none 중 하나로만 판단해 JSON으로 출력하라.
설명·마크다운 금지. 숫자 금지. 형식:
{"safety":"", "convenience":"", "mobility":"", "environment":"",
 "require_large_hospital": false, "extra_categories": [], "required_categories": [],
 "required_near": [], "needs_clarification": false, "clarify_question": null}
- safety: 안전(범죄 적음·CCTV 많음)
- convenience: 편의(편의점·마트·병원)
- mobility: 이동(지하철·버스 접근성)
- environment: 환경(공원·녹지)
- require_large_hospital: '대형병원 꼭 있어야' 류 요구가 있으면 true
- extra_categories: 4개 카테고리 밖에서 '선택'으로 언급된 업종(예: "버거집", "헬스장")이
  있으면 그 의미에 맞는 소분류명을 아래 목록에서만 골라 채운다 (목록 밖 문자열 생성 금지):
  __CATEGORIES__
- required_categories: '필수 요구사항' 구역에서 언급됐거나 '꼭 있어야'처럼 필수로
  요구된 업종·시설. 위 목록에 있으면 그 소분류명을 쓰고, 목록에 없는 시설은
  지도 앱에 검색하듯 가장 일반적인 핵심 명사로 넣는다 — "클라이밍장"→"클라이밍",
  "도서관"→"도서관"처럼 상호에 잘 안 쓰는 '~장'·'~시설' 접미사는 뗀다.
  대형병원은 require_large_hospital로만 표현하고 여기 넣지 않는다.
- required_near: "서울대 근처", "강남역 가까이"처럼 특정 장소 기준 거리 요구가
  있으면 그 장소명("서울대", "강남역")만 넣는다. 이건 업종 존재가 아니라
  거리 필터다 — required_categories에 중복해 넣지 않는다.
- needs_clarification: 4개 카테고리도 모호하고 업종 요구도 없으면 true,
  clarify_question에 질문"""

_EXPLAIN_SYSTEM = """아래 추천 동네들의 실제 지표 수치와 선택 근거(사용자 선호 가중치,
각 동네의 카테고리별 기여도)만 근거로 왜 이 순서로 추천됐는지 설명하라. 사용자가
중요하게 본 항목에 대해서는 함께 제공된 "지표 가공 방식" 안내도 간단히 언급해
숫자의 의미(예: 구 단위 상속값인지, 밀도로 정규화됐는지)를 오해하지 않게 하라.
사용자가 직접 요청한 업종(예: 버거, 헬스장)이 있으면 각 추천지에 실제로 몇 곳
있는지 말하고, 0곳이면 반영되지 않았음을 솔직히 명시하라.

각 지표의 방향성(반드시 이 방향으로만 서술, 헷갈리지 말 것):
- 범죄율(crime_rate): 낮을수록 좋음(안전)
- CCTV·편의점·마트·병원·버스·공원 개수: 많을수록/높을수록 좋음
- 지하철 접근성(subway_access, 0~1 값): 1에 가까울수록 좋음(역과 가까움),
  0에 가까울수록 나쁨(역과 멂). "0에 가까울수록 가깝다"처럼 반대로 말하지 말 것.

제공된 수치·안내에 없는 내용은 추측하지 말 것.
요구를 충족하지 못하는 부분은 솔직히 명시할 것."""


def _build_parse_system() -> str:
    categories = ", ".join(sorted(get_facility_repository().categories()))
    return _PARSE_SYSTEM_BASE.replace("__CATEGORIES__", categories)


class SolarLLM:
    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("SOLAR_MODEL", DEFAULT_MODEL)
        self.api_base = os.environ.get("UPSTAGE_API_BASE", DEFAULT_API_BASE)
        self.api_key = os.environ.get("UPSTAGE_API_KEY")

    def _call(self, system: str, user: str) -> str:
        if not self.api_key:
            raise RuntimeError("UPSTAGE_API_KEY 환경변수가 설정되지 않았습니다.")

        import litellm  # 지연 로딩: mock만 쓰는 환경에서는 패키지가 없어도 무방

        resp = litellm.completion(
            model=f"openai/{self.model}",
            api_base=self.api_base,
            api_key=self.api_key,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.1,  # 재현성 위해 낮게
            num_retries=2,  # 일시적 connection error 대비 (HANDOFF.md 트러블슈팅 참고)
        )
        return resp.choices[0].message.content

    def _call_stream(self, system: str, user: str):
        """explain_stream()용 토큰 스트리밍 호출. 제너레이터라 첫 next() 호출 전까지는
        본문이 실행되지 않으므로, api_key 누락 에러도 실제 반복(iterate) 시점에 발생한다."""
        if not self.api_key:
            raise RuntimeError("UPSTAGE_API_KEY 환경변수가 설정되지 않았습니다.")

        import litellm  # 지연 로딩: mock만 쓰는 환경에서는 패키지가 없어도 무방

        response = litellm.completion(
            model=f"openai/{self.model}",
            api_base=self.api_base,
            api_key=self.api_key,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.1,
            num_retries=2,
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def parse_intent(self, text: str) -> ParsedIntent:
        raw = self._call(_build_parse_system(), text)
        try:
            data = json.loads(raw.strip().strip("`").lstrip("json").strip())
            pref = CategoryPreference(
                safety=Importance(data["safety"]),
                convenience=Importance(data["convenience"]),
                mobility=Importance(data["mobility"]),
                environment=Importance(data["environment"]),
            )
            extra = [c for c in data.get("extra_categories", [])
                     if c in get_facility_repository().categories()]
            # 필수 업종은 열린 키워드 허용 (CSV 밖 시설은 Kakao 좌표검색으로 해석).
            # 빈 문자열 제거·중복 제거·최대 5개 — LLM이 과생성해도 필터 폭주 방지.
            def _clean(key: str, cap: int) -> list[str]:
                return list(dict.fromkeys(
                    str(c).strip() for c in data.get(key, []) if str(c).strip()
                ))[:cap]

            near = _clean("required_near", 3)
            # 프롬프트가 중복 금지를 지시하지만 LLM이 어길 수 있음 — 거리 필터가
            # 우선이고 업종 존재 필터에 같은 이름이 남으면 노이즈 필터가 된다.
            required = [c for c in _clean("required_categories", 5) if c not in near]
            return ParsedIntent(
                preference=pref,
                require_large_hospital=bool(data.get("require_large_hospital", False)),
                extra_categories=extra,
                required_categories=required,
                required_near=near,
                needs_clarification=bool(data.get("needs_clarification", False)),
                clarify_question=data.get("clarify_question"),
            )
        except Exception:
            # 폴백: 파싱 실패 시 되묻기 (scoring이 균등분배도 처리 가능)
            return ParsedIntent(
                preference=CategoryPreference(
                    safety=Importance.NONE, convenience=Importance.NONE,
                    mobility=Importance.NONE, environment=Importance.NONE),
                needs_clarification=True,
                clarify_question="어떤 점을 가장 중요하게 보세요? (안전/편의/교통/환경)",
            )

    def _build_explain_prompt(self, user_text: str, result: dict) -> tuple[str, str] | None:
        """explain/explain_stream 공용 프롬프트 빌더. 추천이 없으면 None(고정 문구로 대체)."""
        recs = result["recommendations"]
        if not recs:
            return None
        # 추천지 실제 수치 + 선택 근거(가중치·기여도)를 프롬프트에 담아 근거 강제
        weights = result.get("weights", {})
        priorities = [c for c, w in sorted(weights.items(), key=lambda x: -x[1]) if w > 0]
        facts = [f"사용자 선호 가중치: {weights}"]
        caveats = [CATEGORY_CAVEATS[c] for c in priorities if c in CATEGORY_CAVEATS]
        if any(r.get("extra_facilities") for r in recs):
            caveats.append("직접 요청하신 업종은 반경 1km가 아니라 해당 행정동에 등록된 업소 수 기준입니다.")
        if caveats:
            facts.append("지표 가공 방식 안내: " + " / ".join(caveats))
        for r in recs:
            raw = r["scores"]["raw"]
            facts.append(
                f"{r['gu']} {r['dong']} (종합 {r['total_score']}, "
                f"카테고리별 기여도 {r.get('contributions', {})}, "
                f"요청 업종 현황 {r.get('extra_facilities', {})}): "
                f"범죄율 {raw['crime_rate']}/만명, "
                f"CCTV {raw['cctv_cnt']}, 편의점 {raw['conv_cnt']}, 마트 {raw['mart_cnt']}, "
                f"병원 {raw['hosp_cnt']}, 버스 {raw['bus_cnt']}, "
                f"지하철접근성 {raw['subway_access']}, 공원 {raw['park_cnt']}")
        user = f"사용자 요구: {user_text}\n추천지 지표:\n" + "\n".join(facts)
        return _EXPLAIN_SYSTEM, user

    def explain(self, user_text: str, result: dict) -> str:
        prompt = self._build_explain_prompt(user_text, result)
        if prompt is None:
            return "조건에 맞는 지역을 찾지 못했습니다."
        return self._call(*prompt)

    def explain_stream(self, user_text: str, result: dict):
        """SSE 컨트롤러용 토큰 스트리밍 버전. 청크(str)를 순서대로 yield한다."""
        prompt = self._build_explain_prompt(user_text, result)
        if prompt is None:
            yield "조건에 맞는 지역을 찾지 못했습니다."
            return
        yield from self._call_stream(*prompt)
