# 인수인계 노트 — 살래말래 (Live or Leave)

> Claude Code로 이어받는 개발자를 위한 문서. 이 대화의 히스토리 없이도
> 프로젝트를 정확히 이어받도록 현재 상태·설계 결정·다음 할 일·불변 원칙을 정리한다.

## 한 줄 요약

서울 행정동 424개를 대상으로, 사용자의 자연어 성향을 받아 살기 좋은 동네를
추천하는 서비스. 계산은 결정론적 백엔드가, 자연어 해석·설명은 LLM이 담당한다.

## 지금 어디까지 됐나 (완료)

- **데이터 파이프라인 완성**: `build_dong_metrics.py`가 원본 공공데이터 CSV들을
  행정동 지표 테이블(`dong_metrics.csv`, 425행)로 통합. 실행하면 재생성됨.
- **레이어드 아키텍처 골격 완성**: schemas → services → agent → data 계층 분리.
- **스코어링 로직 완성**: 분위수 정규화 + 가중 스코어링 + 순위. 순수 함수라 테스트 쉬움.
- **에이전트 흐름 완성**: 입구(의도 파싱) → 백엔드(스코어링) → 출구(근거 설명),
  모호하면 되묻기 1회. `demo.py`로 4개 시나리오 동작 확인됨.
- **실제 Upstage Solar API 연동 완성**: `app/agent/solar_llm.py`가 LiteLLM 경유로
  Solar API를 호출한다. `RecommendationAgent`(`loop.py`) 기본값이 이 클래스이며,
  `mock_llm.py`는 더 이상 프로덕션 경로에서 쓰이지 않고 테스트에서만
  `RecommendationAgent(llm=MockLLM())`로 명시적으로 주입해 사용한다.
- **`.env` 로딩 연결 완성**: 프로젝트 루트의 `.env`(gitignore됨)에 `UPSTAGE_API_KEY`를
  넣으면 `solar_llm.py`가 `python-dotenv`로 자동 로딩한다. 팀원마다 각자 자신의
  키를 넣으면 코드 변경 없이 동일하게 동작한다.
- **SSE 스트리밍 + FastAPI 컨트롤러 완성**: `main.py`의 `GET /recommend`가
  `RecommendationAgent.stream()`을 호출해 근거 설명을 토큰 단위로 SSE 전송한다.
  `uvicorn main:app --reload`로 실행, curl로 직접 확인 가능(아래 재현 방법 참고).
- **실패 케이스 처리 1차 완료**: `litellm.completion(..., num_retries=2)`로 일시적
  연결 실패를 자동 재시도. 그래도 실패하면(예: 잘못된 키) SSE로 이미 응답이
  시작된 상태이므로 HTTP 에러 대신 `{"type": "error", "message": ...}` 이벤트로
  실패를 알린다 (`RecommendationAgent.stream()`이 예외를 절대 밖으로 던지지 않음).
- **Streamlit 지도 UI + 필수조건 하드필터 완성**: `streamlit_app.py`가 서울 425개
  행정동을 지도에 5단계(상위/차상위/저점수/필수조건미충족/중립)로 색칠해 보여준다.
  "필수 요구사항"(하드 필터, `required_categories`)과 "선택 요구사항"(점수 반영,
  기존 흐름)을 분리 입력받는다. 입력이 바뀔 때마다 자동으로 다시 계산된다
  (Streamlit 기본 동작). `build_dong_boundaries.py`가 원본 shapefile을
  `dong_boundaries.geojson`(425개 동, 커밋됨)으로 미리 변환해둔다.
- **흐름 검증 테스트 통과**: `python -m pytest tests/` (128개, 전부 MockLLM 기반이라
  네트워크·API 키 없이 빠르게 실행됨).

## 파일 지도

```
main.py                  # FastAPI 컨트롤러. GET /health, GET /recommend(SSE)
app/
  schemas/
    domain.py      # DongRawMetrics, DongScores, Recommendation (데이터 구조)
    tools.py       # Importance(4단계 라벨), CategoryPreference, ParsedIntent, 도구 스키마
  services/
    scoring.py     # 결정론적 계산: 분위수 정규화·스코어링·순위 (LLM 없음, 핵심 로직)
  agent/
    solar_llm.py   # ★ 프로덕션 기본 LLM. Upstage Solar API를 LiteLLM 경유로 호출(스트리밍 지원) ★
    mock_llm.py    # 키워드 매칭 스텁. 이제는 테스트 전용(RecommendationAgent(llm=MockLLM()))
    tools.py       # ToolExecutor: 도구를 scoring 서비스에 위임
    loop.py        # ReAct 흐름 오케스트레이터. run()=완성된 결과, stream()=SSE용 제너레이터
  data/
    csv_repository.py       # dong_metrics.csv를 읽어 DongRawMetrics로 공급
    facility_repository.py  # 임의 업종(상가업소) 조회 — dataset/ 원본 CSV 필요
build_dong_metrics.py     # 원본 CSV → dong_metrics.csv 생성 (파이프라인)
build_dong_boundaries.py  # 원본 shapefile → dong_boundaries.geojson 생성 (지도용, 간략화 포함)
dong_metrics.csv          # 행정동 지표 테이블 (빌더 산출물)
dong_boundaries.geojson   # 행정동 425개 경계 (지도 UI용, 빌더 산출물, 커밋됨)
seoul_gu.geojson          # 자치구 경계 (참고용)
demo.py                   # 시나리오 데모 실행 (실제 Solar API 사용, .env 필요)
streamlit_app.py          # 지도 UI. 키 있으면 Solar, 없으면 자동 mock, STREAMLIT_USE_MOCK_LLM=1로 강제 mock
.env                      # UPSTAGE_API_KEY 등 (gitignore됨, 각자 로컬에 개별 생성)
tests/test_main.py        # FastAPI 컨트롤러 테스트 (TestClient, MockLLM으로 의존성 오버라이드)
tests/test_flow.py        # 흐름 검증 (MockLLM 명시 주입)
```

## 절대 바꾸면 안 되는 설계 원칙 (이유 포함)

이 원칙들은 오랜 논의 끝에 의도적으로 내린 결정이다. Claude Code가 "개선"하려다
되돌리기 쉬우니 주의.

1. **LLM은 입구·출구에만. 계산은 전부 백엔드.**
   정규화·스코어링·정렬은 `scoring.py`가 결정론적으로 한다. LLM에게 산수를
   시키지 않는다. 이유: 재현성·속도·정확성. "에이전트니까 LLM이 다 해야"는 오해다.

2. **LLM은 숫자를 만들지 않고 라벨만 고른다.**
   `parse_intent`는 카테고리별 중요도를 4단계 라벨(Importance)로만 출력.
   라벨→가중치(0.0~1.0) 변환은 `scoring.preference_to_weights`가 결정론적으로.
   이유: LLM이 매번 "0.8" 같은 숫자를 즉흥적으로 뽑으면 랭킹이 흔들린다.

3. **출구 LLM은 제공된 수치만 근거로 설명.**
   추천 행정동의 실제 지표를 프롬프트에 넣고, "수치에 없는 내용은 추측 금지"를
   강제한다. 이유: 할루시네이션 방지. 요구 미충족도 솔직히 명시한다.

4. **분석 단위는 행정동(424개). 구 단위 아님.**
   구 단위는 "강남구 전체 편의점 805개"로 뭉뚱그려 대치동·개포동을 구분 못 함.
   행정동으로 내려 같은 구 안 변별력을 확보했다. (MAUP 문제 해결)

5. **지표별 처리 방식이 다르다 (데이터 해상도를 정직하게 반영).**
   - 반경 1km 내 개수형: 편의점·마트·병원·버스·CCTV·공원 (인구로 나눠 밀도화)
   - 최근접 거리형: 지하철 (거리감쇠 exp(-d/500))
   - 구 상속: 범죄율 (행정동 범죄 데이터가 공개 안 됨 → 소속 구 값 물려받음)
   - 행정동 고유: 생활인구
   범죄를 억지로 행정동화하지 않는다. 없는 데이터를 지어내지 않는 게 원칙.

6. **분모는 생활인구(주민등록 아님).**
   LOCAL_PEOPLE 데이터를 씀. 유동인구 포함이라 "실제 그 지역을 이용하는 사람
   대비"로 평가됨. 발표 시 이 선택 이유를 설명 포인트로.

7. **도구를 남발하지 않는다.**
   흐름은 입구→백엔드→출구로 고정. LLM이 여러 도구를 자율 연쇄 호출하는
   구조는 의도적으로 배제(오버엔지니어링). 되묻기 1회만 agentic 분기.

## 다음 할 일 (우선순위 순)

1. **반경 1km 적절성 검증.** 큰 행정동(진관동·상계동)에서 부족할 수 있음.
   시설별 다른 반경(편의점 500m, 병원 1.5km) 실험.
2. **GCP 배포** ($300 크레딧). MVP 마무리. `main.py`(FastAPI+SSE)와
   `streamlit_app.py`(지도 UI) 둘 다 완성된 상태 — 뭘 배포할지/둘 다 배포할지 결정 필요.
3. **(여유 있으면) 실패 케이스 처리 고도화.** 지금은 `num_retries=2`로 초기
   연결 실패만 자동 재시도한다. 스트리밍 도중 끊기는 경우(청크 일부만 받고
   중단)에 대한 재개 로직은 아직 없음 — MVP 범위에선 우선순위 낮음.

## 실행 방법

```bash
pip install -r requirements.txt   # litellm/fastapi 포함, Python 3.9+ 필요
python demo.py                    # 시나리오 데모 (실제 Solar API, .env 필요)
uvicorn main:app --reload         # FastAPI 서버 (http://127.0.0.1:8000)
python -m pytest tests/           # 전체 유닛테스트 (MockLLM 기반, 키 없이도 실행됨)
python build_dong_metrics.py      # 지표 테이블 재생성 (원본 CSV 필요)
```

`.env`(프로젝트 루트, gitignore됨)에 `UPSTAGE_API_KEY=본인의_키`를 넣어야
`demo.py`가 동작한다. 없으면 `solar_llm.py`의 `_call()`이 `RuntimeError`로
바로 실패한다 (mock으로 돌리려면 `RecommendationAgent(llm=MockLLM())`로 직접 교체).

주의: `build_dong_metrics.py`는 원본 공공데이터 CSV들이 `dataset/` 아래 있어야
동작한다. `dong_metrics.csv`는 이미 생성돼 있으므로, 앱만 돌릴 거면 빌더는 실행 불필요.

## 알려진 한계 / 주의

- 범죄는 구 단위 → 같은 구 안 행정동은 범죄율 동일 (데이터 한계, 정직한 처리).
- 행정동 크기 중앙값 0.97km²(반지름 ~557m)라 반경 1km면 대부분 커버되나,
  거대 행정동(최대 12.7km²)은 중심점 근사 오차가 큼.
- CCTV 좌표 컬럼명은 `WGS84위도`/`WGS84경도` (다른 파일과 다름, 빌더에 반영됨).
- 좌표계: 시설은 위경도(4326), 행정동 중심점은 TM(5181). 빌더가 5181로 통일.

## 트러블슈팅 (Solar API 연동 작업 중 실제로 겪은 것들)

- **`pip install litellm`이 안 됨 (Python 3.8 환경)**: litellm의 의존 패키지가
  Python 3.9+를 요구한다. `.venv`를 3.9 이상으로 재생성해야 한다.
- **`parse_intent` 호출 시 `FileNotFoundError` (dataset 관련)**: `solar_llm.py`의
  `_build_parse_system()`이 `extra_categories` 후보 목록을 만들려고 매번
  `get_facility_repository()`를 호출하는데, 이건 `dataset/소상공인시장진흥공단_상가(상권)정보_서울.csv`
  (원본, 용량 커서 gitignore)가 있어야 한다. **mock과 달리 Solar API는 이 파일 없이는
  parse_intent 자체가 안 된다** — 서울 열린데이터광장에서 받아 `dataset/`에 넣을 것.
- **지표 방향성을 LLM이 헷갈림 (발견 후 수정 완료)**: 초기 프롬프트에선 `explain`이
  실제 순위는 맞게 계산하면서도, 부연 설명에서 "지하철 접근성은 0에 가까울수록
  가깝다"처럼 **방향을 반대로 서술**하는 경우가 있었다(`subway_access`는 1에
  가까울수록 좋음). `_EXPLAIN_SYSTEM`에 지표별 방향성(범죄율은 낮을수록,
  개수형은 많을수록, `subway_access`는 1에 가까울수록 좋음)을 명시적으로 못박아
  해결함. 비슷한 지표를 추가할 땐 방향성을 프롬프트에 같이 못박을 것.
- **LiteLLM 경유 호출이 가끔 `InternalServerError: Connection error`**: 재시도하면
  바로 성공하는 일시적 현상이었다 (재현 안 됨, 원인 미확정 — 네트워크 hiccup 추정).
  `litellm.completion(..., num_retries=2)`로 해결(자동 재시도).
- **`num_retries`를 썼더니 `tenacity import failed` 에러**: LiteLLM의 재시도
  기능이 내부적으로 `tenacity` 패키지를 쓰는데, `litellm` 설치만으로는 같이
  안 딸려온다. `requirements.txt`에 `tenacity`를 명시적으로 추가해서 해결.
  (이 에러 자체도 SSE로는 `{"type": "error"}` 이벤트로 깔끔하게 전달되는 것까지
  확인함 — 서버가 죽거나 커넥션이 뻗지 않는다.)
- **모델 매핑 경고 로그**: `solar-pro2-251215`가 LiteLLM의
  `model_prices_and_context_window.json`에 없어 `Error getting model info: This
  model isn't mapped yet` 경고가 뜬다. 비용 계산용 메타데이터가 없다는 뜻일 뿐
  실제 호출·응답에는 영향 없음 (무시해도 됨).

## 시나리오 재현 방법 (직접 확인하고 싶을 때)

```bash
source .venv/bin/activate
python demo.py
```

`demo.py`가 아래 4개 시나리오를 실제 Solar API로 순서대로 실행하고, 각 시나리오의
`[ReAct trace]`(parse_intent 결과·가중치·top 후보)까지 함께 출력한다:

1. 메인 — 이동·안전 중시 ("야근이 잦고 차가 없어서...")
2. 필수조건 — 대형병원
3. 되묻기 — 성향 모호
4. 임의 업종 — 버거·헬스장 (extra_categories 반영 확인용)

특정 문장 하나만 빠르게 찍어보고 싶다면:

```bash
python -c "
from app.agent.loop import RecommendationAgent
res = RecommendationAgent().run('여기에 테스트할 문장')
print(res.message)
"
```

mock으로 실행하고 싶으면(키 없이, 결정론적으로):

```bash
python -c "
from app.agent.loop import RecommendationAgent
from app.agent.mock_llm import MockLLM
res = RecommendationAgent(llm=MockLLM()).run('여기에 테스트할 문장')
print(res.message)
"
```

### SSE 스트리밍(main.py) 직접 확인하기

```bash
uvicorn main:app --reload &
curl -N --get "http://127.0.0.1:8000/recommend" \
  --data-urlencode "text=야근이 잦고 차가 없어서 지하철이 중요해. 밤에 안전한 동네였으면 좋겠어."
```

`data: {"type": "meta", ...}` (가중치·추천 데이터) → `data: {"type": "delta", "text": "토큰"}`가
여러 번 → `data: {"type": "done"}` 순서로 찍히면 정상. 모호한 문장을 넣으면
`meta.kind`가 `"clarify"`로 바뀌고 delta 1개 + done만 온다. `.env`의 키를 일부러
틀리게 바꿔서 테스트하면 `{"type": "error", "message": "..."}`가 오는 것도 확인 가능
(서버가 죽지 않고 SSE로 에러를 전달함).

### 지도 UI(streamlit_app.py) 직접 확인하기

```bash
streamlit run streamlit_app.py                          # .env에 키 있으면 실제 Solar API
STREAMLIT_USE_MOCK_LLM=1 streamlit run streamlit_app.py  # 빠른 반복 작업용: 강제 mock
```

`.env`에 `UPSTAGE_API_KEY`가 없으면 `load_agent()`가 자동으로 mock으로 낮추고
화면 상단에 "⚠ Mock LLM으로 동작 중 (UPSTAGE_API_KEY 없음)" 캡션이 뜬다 — 앱이
죽지 않고 항상 실행은 된다. 키가 있어도 색깔·레이아웃만 반복 확인할 땐
`STREAMLIT_USE_MOCK_LLM=1`로 강제 전환하는 게 빠르다 (이땐 캡션에 "STREAMLIT_USE_MOCK_LLM
설정됨"으로 표시). 이 UI는 입력창 값이 바뀔 때마다(포커스 아웃/Ctrl+Enter)
`parse_intent`+`explain` 2회를 다시 호출하는 구조라, 실제 시연 때만 키를 넣고
Solar로 돌리는 걸 권장한다.
