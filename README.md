# 살래말래 (Live or Leave)

서울 행정동 424개 단위로, 사용자의 자연어 라이프스타일 선호를 받아 살기 좋은 동네를
추천하는 서비스입니다. 자연어 해석·근거 설명은 LLM이, 정규화·스코어링·순위 계산은
결정론적 백엔드가 맡습니다.

> "야근이 잦고 차가 없어서 지하철이 중요해. 밤에 안전한 동네였으면 좋겠어."
>
> → 이동·안전 가중치를 높게 파싱해 상위 3개 행정동을 추천하고, 실제 지표 수치를
> 근거로 왜 그 순서인지 설명합니다.

## 핵심 설계

- **분석 단위는 행정동(424개), 자치구가 아닙니다.** 자치구 단위로는 "강남구"로
  뭉뚱그려 대치동과 개포동을 구분하지 못합니다 (MAUP 문제).
- **LLM은 입구·출구에만 관여합니다.** 자연어 해석(`parse_intent`)과 근거 설명
  (`explain`)만 LLM이 하고, 정규화·스코어링·정렬은 전부 순수 함수(`scoring.py`)가
  결정론적으로 계산합니다.
- **LLM은 숫자를 만들지 않습니다.** 카테고리별 중요도는 4단계 라벨(매우중요/중요/
  보통/관계없음)만 고르고, 라벨 → 가중치 변환은 코드가 고정값으로 수행합니다.
- **데이터에 없는 걸 지어내지 않습니다.** 범죄율은 행정동 단위로 공개되지 않아
  자치구 값을 상속받는데, 이 사실을 추천 설명에 각주로 명시합니다.

설계 배경과 전체 원칙은 [HANDOFF.md](HANDOFF.md)에 정리돼 있습니다.

## 무엇을 하는가

사용자 문장 → 4개 핵심 카테고리(안전/편의/이동/환경) 가중치 산출 → 424개 행정동
스코어링·순위 → 실제 지표 수치로 근거 설명.

"버거집", "헬스장"처럼 4개 카테고리 밖의 업종을 언급하면, 실제 상권업종 데이터에서
해당 행정동의 업소 수를 조회해 점수에 반영하고, 없으면 없다고 솔직히 알려줍니다.

## 프로젝트 구조

```
app/
  schemas/
    domain.py       # DongRawMetrics, DongScores, Recommendation, 지표별 가공방식 각주
    tools.py         # Importance, CategoryPreference, ParsedIntent, 도구 스키마
  services/
    scoring.py       # 결정론적 계산: 분위수 정규화·스코어링·순위 (LLM 없음, 핵심 로직)
  agent/
    mock_llm.py      # 규칙 기반 스텁 LLM (개발/테스트용, 기본값)
    solar_llm.py     # Upstage Solar API 어댑터 (LiteLLM 경유, .env의 UPSTAGE_API_KEY 사용)
    tools.py         # ToolExecutor: 도구를 scoring 서비스에 위임
    loop.py          # ReAct 흐름 오케스트레이터 (입구→도구→출구, 되묻기 1회)
  data/
    csv_repository.py       # dong_metrics.csv 로더
    facility_repository.py  # 임의 업종(상가업소) 조회, 프로세스 수명 동안 캐시
build_dong_metrics.py  # 원본 공공데이터 → dong_metrics.csv 생성 파이프라인
dong_metrics.csv       # 행정동 424개 지표 테이블 (커밋됨, 앱 실행에 바로 필요)
demo.py                # 시나리오 데모 실행
tests/                 # pytest 103개 (알고리즘 단위 테스트 + 실데이터 시나리오 검증)
```

## 실행 방법

```bash
pip install -r requirements.txt
python demo.py                # 시나리오 데모
python -m pytest tests/       # 전체 테스트
```

`dong_metrics.csv`는 이미 커밋돼 있어 위 명령만으로 바로 동작합니다. 원본 공공데이터
(`dataset/`)는 용량이 커서(약 160MB) `.gitignore` 처리돼 있고, 재생성하려면 원본
CSV들을 별도로 확보해 `python build_dong_metrics.py`를 실행해야 합니다.

Python 3.9 이상이 필요합니다 (LiteLLM 의존성 때문).

### 실제 Upstage Solar API 연동 (선택)

프로젝트 루트에 `.env` 파일을 만들고 아래처럼 키를 넣으면, `RecommendationAgent`가
자동으로 mock 대신 실제 Solar API를 사용합니다 (`.env`는 `.gitignore`에 등록돼
있어 커밋되지 않습니다). 팀원마다 각자 자신의 키를 넣으면 동일하게 동작합니다.

```
UPSTAGE_API_KEY=본인의_Upstage_API_키
```

`.env`가 없거나 `UPSTAGE_API_KEY`가 비어 있으면 자동으로 `mock_llm.py`(키워드 기반
스텁)로 동작하므로, 키 없이도 개발·테스트가 가능합니다.

## 지금 상태 / 다음 할 일

- 완료: 데이터 파이프라인, 스코어링, ReAct 흐름, 임의 업종(버거·헬스장 등) 조회,
  실제 Upstage Solar API 연동(`solar_llm.py`, LiteLLM 경유, `.env`의
  `UPSTAGE_API_KEY` 유무로 mock과 자동 스위칭)
- 다음: FastAPI 컨트롤러 추가 (현재는 `demo.py`가 대신 실행)

## 데이터 출처

서울 열린데이터광장 공공데이터 — 상권분석서비스(행정동 경계), 생활인구, 5대 범죄
발생현황, CCTV 설치현황, 버스정류소 위치, 도시공원정보, 역사마스터 정보, 소상공인
상가업소 정보. 지표별 가공 방식(반경 1km 밀도화, 구 상속, 거리감쇠 등)은
[HANDOFF.md](HANDOFF.md)와 `app/schemas/domain.py`의 `CATEGORY_CAVEATS`를
참고하세요.
