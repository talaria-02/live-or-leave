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
- **필수/선택 요구사항 분리 완성**: `ParsedIntent`/`RecommendTool`에
  `required_filters`(하드 필터, AND 조건)와 `extra_categories`(점수화)가 분리돼
  있다. `mock_llm.py`는 `"필수 요구사항:"`/`"선택 요구사항:"` 마커로 텍스트를
  나눠 각각 다르게 처리(마커 없으면 전부 선택으로 취급, 하위호환). 하드필터에
  걸린 동은 각 필터 실행 함수가 "왜 떨어졌는지"(`missing` 목록)까지 함께
  반환 — UI가 이유를 보여줄 수 있음. (아래 "필수조건 필터 일반화" 항목이
  이 스키마를 category/near/gu 3종으로 확장한 최신 상태 — metric은 이후
  제거됨, "수치 지표 컷오프 필터 제거" 항목 참고.)
- **임의 업종 조회 완성**: `app/data/facility_repository.py`가
  `dataset/소상공인시장진흥공단_상가(상권)정보_서울.csv`(원본, gitignore됨)를
  (자치구,행정동,업종소분류) 카운트로 집계해 지연 로딩 싱글턴으로 캐시한다.
  "버거", "헬스장" 같은 247개 실제 업종소분류명 중에서만 매칭(닫힌 집합).
- **지도 GeoJSON 파이프라인 완성**: `build_dong_boundaries.py`가
  `space_info/BND_ADM_DONG_PG.shp`(전국 행정동 경계, gitignore됨, 원본은 팀
  드라이브에 있음)를 서울 425개로 필터링·Douglas-Peucker 단순화(15m 허용오차,
  205k→13.9k 좌표점)·재투영해 `dong_boundaries.geojson`(커밋됨, 0.4MB)을 만든다.
  이름 불일치 3종을 알고 처리함(자세한 근거는 스크립트 주석 참고):
  서울시 데이터 자체의 "·"→"?" 인코딩 손실 7건, 강동구 상일동(지도엔 1·2동으로
  분리), 강남구 일원2동(2023년 개편으로 개포3동에 편입).
- **필수조건 열린 키워드 확장 완성 (Kakao Local API)**: 상가 CSV의 닫힌 집합
  (247개 업종소분류)에 없는 필수 시설("클라이밍장", "도서관" 등)도 Kakao
  키워드 검색으로 좌표를 받아 처리한다. `app/data/kakao_facility_repository.py`:
  - `KakaoFacilityRepository` — 서울 bbox 검색(45건 초과 시 rect 4분할 재귀),
    shapely point-in-polygon으로 좌표→행정동 매핑, 키워드별 디스크 캐시(TTL 7일,
    원본 장소 좌표까지 함께 저장해 지도 핀·검증용으로 재사용).
  - "서울대 근처" 같은 거리 요구(현재는 `FilterClause(type="near", ...)`, 도입 당시
    이름은 `required_near`) — 업종 존재 필터와는 다른 의미론. 장소 좌표 1개만
    찾아 동 중심점과의 거리(`NEAR_RADIUS_KM`, 현재 3km)로 하드 필터한다. 이름
    매칭(예: "서울대" 상호 890곳 매칭)과 섞으면 엉뚱한 동이 통과하는 버그가
    났었음 — 그래서 분리(아래 "필수조건 필터 일반화" 항목에서 이 필드명 자체는
    `required_filters`로 다시 통합됨).
  - `HybridFacilityRepository` — CSV 보유 업종은 CSV 그대로(API 호출 0),
    미보유 키워드만 Kakao로 폴백. 해석 불가(CSV에도 없고 API 키도 없음)한
    필수조건은 조용히 전 지역을 실격시키는 대신 필터를 생략하고
    `unresolved_requirements`로 보고한다.
  - Kakao API 키 없어도 앱은 그대로 뜬다(그 기능만 비활성).
- **Streamlit UI 전면 개편**: 화면 전체를 지도로 채우고(`px.choropleth_map`,
  MapLibre 타일), 입력창은 우측에 반투명 오버레이 패널로 띄운다
  (`position: fixed` + Streamlit 내부 DOM에 CSS로 직접 개입 — 아래 "알려진
  한계" 참고). 지도 스타일은 위성사진/일반/어두움(기본값) 중 선택 가능.
  서울 바깥은 전체를 어둡게 깔아(shapely로 "서울 아님" 마스크 폴리곤 계산)
  서울만 도드라져 보이게 하는 스포트라이트 효과. 서울역·강남역·대형병원·
  대학교 등 핵심시설 20곳을 고정 마커로 표시하고, Kakao로 찾은 필수 업종
  위치·"근처" 기준 장소도 지도 위에 핀으로 찍어 필터 근거를 눈으로 검증할
  수 있게 했다. 위젯(지도 스타일 변경 등) 하나 누를 때마다 스크립트
  전체가 재실행되던 걸 `@st.fragment`로 앱 본문 전체를 감싸 해결 — 단,
  지도가 확대·이동해둔 카메라 위치까지 지켜주진 못한다(Plotly가 지도
  내용이 바뀔 때마다 컴포넌트를 완전히 새로 마운트하는 동작이라, `uirevision`을
  걸어도 이 조합에선 카메라가 리셋됨 — 직접 확인한 프레임워크 한계).
- **`main.py`/`streamlit_app.py` 구조 통합**: 자세한 내용은 아래 "다음 할 일"
  1번(해결됨) 참고. 요지는 `app/agent/factory.py`로 mock 폴백 판단과
  `top_n` 처리를 공유해 두 앱이 같은 입력에 항상 같은 결정을 내리게 한 것.
- **필수조건 필터 일반화 완성**: `required_categories`(업종)/`required_near`(거리)
  낱개 필드를 계속 늘리는 대신 `required_filters: list[FilterClause]`(타입:
  category/near/gu/metric) 하나로 통합했다. `app/agent/tools.py`가 type별로
  디스패치:
  - `near`는 `group`으로 OR 그룹 지원(예: "강남역이나 홍대입구역 중 아무데나").
  - `gu`(행정구역 포함/제외, "강남3구" 같은 통칭은 `GU_ALIASES`로 해석)와
    `metric`(지표 백분위 임계값, `METRIC_DIRECTIONS`로 방향성 등록)이 신규 —
    둘 다 로컬 데이터만으로 되는 필터라 API 호출 0회.
  - Kakao Local의 표준 카테고리(14종, `PM9`=약국·`SW8`=지하철역 등) 검색도
    지원 — 키워드가 매칭되면 추측성 키워드 검색 대신 정확한 카테고리 검색으로
    자동 전환.
- **의도 파싱 안티할루시네이션 가드 통합**: 팀원이 작업한
  `app/agent/intent_sanitizer.py`(배경 정보로 업종·대형병원을 지어내는 것
  방지, 모호한 질의 되묻기 강제)와 `app/agent/unsupported_requirements.py`
  (월세·학군·소음·채광·반려동물·주차처럼 현재 스키마로 아예 검증 불가능한
  요구를 감지해 설명에 한계로 명시)를 위 `required_filters`의 category 타입에도
  동일하게 적용(`explicitly_requested_categories`가 `extra_categories`뿐 아니라
  category 절도 텍스트-존재 검증). 애매함 강제 되묻기는 gu/near/metric처럼
  구체적 필터가 이미 하나라도 파싱됐으면 걸지 않도록 조건 추가(안 그러면 그
  휴리스틱이 새 필터 타입을 몰라 정상 요청도 되묻기로 튕길 수 있었음).
- **Day4 배포 완료 (로컬 빌드 → GCE 실제 배포 → CI/CD)**: `Dockerfile`,
  `docker-compose.yml`, `.dockerignore`, `.env.example`, `docs/deploy-gce.md`를
  추가했다. FastAPI API(8000)와 Streamlit UI(8501)를 같은 Docker 이미지에서
  command만 다르게 실행한다. GCE VM(`asia-northeast3-a`, e2-standard-4, 고정 IP)에 실제로
  clone·배포해 외부에서 `http://<VM_IP>:8000/health`, `http://<VM_IP>:8501`
  접속을 확인했다. GitHub Actions는 `.github/workflows/ci.yml`(테스트 +
  Docker 이미지 빌드)과 `.github/workflows/cd.yml`(CI 성공 시 `workflow_run`으로
  트리거돼 VM에 SSH로 재배포)로 분리돼 있다 — main에 push하면 테스트 통과 후
  자동으로 VM에 최신 코드가 반영된다. 접속 대상 IP·계정명도 코드에 하드코딩하지
  않고 `GCE_HOST`/`GCE_USER` GitHub Secret으로 관리한다.
- **Langfuse 기반 LLM 호출 추적 완료**: `solar_llm.py`의 `_configure_langfuse_tracing()`이
  `LANGFUSE_PUBLIC_KEY`가 설정된 경우에만 `litellm.success_callback`/`failure_callback`에
  `"langfuse"`를 등록한다. 키가 없으면 완전히 무시되고 평소처럼 동작한다(옵션 기능).
- **페르소나 기반 시나리오 샘플링 완료**: `QUTUMENT/nemotron-personas-korea-extended`
  (NVIDIA Nemotron-Personas-Korea 확장판 미러, CC BY 4.0)에서 전체 Parquet를
  내려받지 않고 Hugging Face 원격 Parquet row group을 읽어 서울 중심 샘플을 생성했다.
  `data/personas/persona_sample_probe.csv`(50행), `persona_sample_500.csv`(500행),
  `persona_sample_stratified.csv`(3,000행)가 있으며, `data/personas/README.md`에
  출처·라이선스·재현 명령·컬럼 정책을 적어두었다. 이 샘플을 기반으로 만든
  "핵심 검증 시나리오 30개"까지 완료(아래 "페르소나 시나리오 설계 기준" 절 참고).
- **흐름 검증 테스트 통과**: `python -m pytest tests/` (206개, 전부 MockLLM
  기반 + Kakao/네트워크는 monkeypatch로 격리라 API 키·네트워크 없이도 빠르게 실행됨).
- **Streamlit UX 개선 (제출 버튼 + 자연어 응답) 완료**: 두 가지를 바꿨다.
  1. 입력창 blur만으로 자동 실행되던 걸 "동네 추천하기" `st.button()`으로
     게이트했다 — 버튼을 누른 rerun에서만 `run_agent_cached`(LLM 호출)가
     실행된다. 마지막 결과는 `st.session_state["last_result"]`에 저장해,
     버튼을 안 누른 rerun(지도 스타일 변경 등)에서도 이전 지도/메시지를
     그대로 보여준다(빈 입력으로 누르면 `st.info` 안내만 뜨고 기존 결과는
     안 지워짐). `_app_body()`가 이미 `@st.fragment`라 버튼 클릭도 이
     함수만 재실행시킨다.
  2. 응답 문장에서 가중치·기여도·raw 지표 개수 노출을 제거하고 자연어로
     바꿨다(위 "절대 바꾸면 안 되는 설계 원칙" 7번 참고). 실제 Solar API로
     검증하는 과정에서 "가중치/기여도 숫자만 금지"로는 부족하고 "공원 24곳"
     같은 raw 개수도 별도로 금지해야 한다는 걸 확인했다 — 프롬프트에
     "일반 스코어링 지표는 숫자 자체를 쓰지 말 것" + 출력 직전 자가점검
     지시를 추가해서야 안정적으로 지켜졌다(사용자가 직접 요청한 업종
     개수는 예외로 계속 노출). LLM 프롬프트 지시라 100% 기계적 보장은
     아니라서, hover/expander라는 raw 데이터 노출 경로를 안전망으로 남겨뒀다.
  - 지도 클릭으로 선택한 동의 추천/비추천 이유를 카드로 보여주는 인터랙션은
    설계 검토까지만 완료(`st.plotly_chart(..., on_select="rerun",
    selection_mode="points")`로 실제 가능함을 확인함) — 구현은 다음 세션에서.
- **수치 지표 상위권 컷오프 필터(metric) 제거**: `FilterClause(type="metric")`가
  하던 "이 동네 지표가 서울 상위 N% 안에 들어야 함"(백분위 컷오프, moderate=
  상위50%/strict=30%/very_strict=15%) 하드 필터를 프롬프트·백엔드 양쪽에서
  완전히 뺐다 — 대부분의 지역을 실격(보라색)으로 만드는 주범이었다. 스키마
  (`MetricLevel` enum, `FilterClause.field`/`level`), 실행 로직
  (`scoring.partition_by_metric`, `tools.py`의 `METRIC_DIRECTIONS`/
  `METRIC_LEVEL_CUTOFF`와 metric 디스패치 분기), 파싱 프롬프트의 4번째
  타입 설명·`_METRIC_FIELDS` 치환을 모두 제거했다. `required_filters`는
  이제 category/near/gu 3종만 남는다 — 필요하면 선택 요구사항(가중치
  기반 점수화)으로 대체할 것.

## 파일 지도

```
main.py                  # FastAPI 컨트롤러. GET /health, GET /recommend(SSE, top_n=)
scripts/
  sample_qutument_personas.py  # QUTUMENT Extended 원격 Parquet에서 서울 중심 샘플 생성
  build_persona_scenarios.py   # 샘플 → 후보 질문/커버리지 감사/최종 30개 생성
app/
  schemas/
    domain.py      # DongRawMetrics, DongScores, Recommendation, CATEGORY_CAVEATS(가공방식 각주)
    tools.py       # Importance(4단계 라벨), CategoryPreference, ParsedIntent,
                   # FilterClause 등 도구 스키마 (extra_categories=점수화, required_filters=하드필터)
  services/
    scoring.py     # 결정론적 계산: 분위수 정규화·스코어링·순위·필수조건 필터(+탈락사유)
  agent/
    solar_llm.py   # ★ 프로덕션 기본 LLM. Upstage Solar API를 LiteLLM 경유로 호출(스트리밍 지원) ★
    mock_llm.py    # 키워드 매칭 스텁. 이제는 테스트 전용(RecommendationAgent(llm=MockLLM()))
    tools.py       # ToolExecutor: 도구를 scoring 서비스에 위임, FilterClause type별 디스패치
    loop.py        # ReAct 흐름 오케스트레이터. run(top_n=)=완성된 결과, stream(top_n=)=SSE용 제너레이터
    factory.py     # main.py/streamlit_app.py가 공유하는 mock 판단·에이전트 생성
    unsupported_requirements.py  # 현재 데이터로 직접 검증 불가한 사용자 요구 감지
    intent_sanitizer.py          # LLM 의도 출력 후처리(업종 과잉 추론 방지, 모호 질의 보정)
  data/
    csv_repository.py            # dong_metrics.csv를 읽어 DongRawMetrics로 공급
    facility_repository.py       # 임의/필수 업종(상가업소) 조회 — dataset/ 원본 CSV 필요, 지연 캐시
    kakao_facility_repository.py # CSV 밖 열린 키워드·"근처" 거리 필터용 Kakao Local API 어댑터 (신규)
build_dong_metrics.py     # 원본 CSV → dong_metrics.csv 생성 (파이프라인)
build_dong_boundaries.py  # space_info/ 전국 shapefile → dong_boundaries.geojson (지도용, 서울 425개)
dong_metrics.csv          # 행정동 지표 테이블 (빌더 산출물, 커밋됨)
dong_boundaries.geojson   # 행정동 경계 (지도 UI용, 커밋됨, 0.4MB)
seoul_gu.geojson          # 자치구 경계 (참고용, 미사용)
demo.py                   # 시나리오 데모 실행 (실제 Solar API 사용, .env 필요)
streamlit_app.py          # 지도 UI. 키 있으면 Solar, 없으면 자동 mock, USE_MOCK_LLM=1로 강제 mock
                          # (화면 전체 지도+우측 오버레이 패널, 아래 "지도 UI 직접 확인하기" 참고)
data/personas/
  README.md                         # 페르소나 샘플 출처·라이선스·재현 명령
  persona_schema_notes.md           # 51개 원본 컬럼 확인 및 probe 요약
  persona_sample_probe.csv          # 50행 schema/품질 probe
  persona_sample_500.csv            # 빠른 검토용 서울 중심 500행 샘플
  persona_sample_stratified.csv     # 시나리오 생성용 서울 중심 3,000행 샘플
  persona_relevant_pool.csv         # 주거 추천 신호가 강한 페르소나 500개
  persona_scenario_candidates.csv   # 후보 질문 84개
  data_coverage_audit.csv           # 후보별 현재 스키마 커버리지 태깅
  persona_scenarios_30.csv          # 발표/검증용 최종 30개
.env                      # UPSTAGE_API_KEY 등 (gitignore됨, 각자 로컬에 개별 생성)
dataset/                  # 원본 공공데이터 (gitignore됨, ~160MB, data.seoul.go.kr 등에서 재확보)
space_info/               # 원본 행정동 shapefile+코드표 (gitignore됨, 지도 재생성용)
tests/test_main.py               # FastAPI 컨트롤러 테스트 (TestClient, MockLLM으로 의존성 오버라이드)
tests/test_flow.py               # 흐름 검증 (MockLLM 명시 주입)
tests/test_agent_factory.py      # app/agent/factory.py 공유 로직 테스트
tests/test_kakao_facility_repository.py  # Kakao 저장소 + '근처' 거리 필터 테스트 (네트워크 없이, monkeypatch)
tests/test_streamlit_app.py      # streamlit_app.py 고유 로직(캐싱·지도 완전성) 테스트
```

## 페르소나 시나리오 설계 기준 (발표 검증용)

멘토링 피드백의 핵심은 "서비스가 기존 서비스와 어떻게 다르고, 실제 사용자 요구를
현재 데이터 스키마가 얼마나 커버하는지"를 보여주는 것이다. 그래서 시나리오 30개는
임의 예시가 아니라, QUTUMENT Extended 샘플에서 뽑은 합성 페르소나를 바탕으로
만든 **대표 사용자 요구 검증셋**이어야 한다.

### 현재 샘플링 상태

- 원본: `QUTUMENT/nemotron-personas-korea-extended`
  - NVIDIA `Nemotron-Personas-Korea` 기반 확장판 미러.
  - CC BY 4.0. 발표/README에 출처와 라이선스를 반드시 표기한다.
  - 합성 페르소나이며 실제 개인 데이터가 아니다.
- 원본 데이터셋은 51개 컬럼, 1,000,000행이다.
- 현재 CSV 샘플은 51개 전체 컬럼을 모두 저장하지 않고, 시나리오 생성에 필요한
  원본 컬럼 36개만 읽었다. 컬럼명은 바꾸지 않았다.
- 분석 편의를 위해 파생 컬럼 5개를 추가했다:
  `age_group`, `occupation_group`, `housing_group`, `income_group`, `is_seoulish`.
- 지역 필터는 `district` 값의 `서울-노원구` 같은 문자열을 기준으로 했다.
  원본에 `province` 컬럼은 없으므로 summary에서 `province=unknown`으로 나오는 것은 정상이다.
- `persona_sample_stratified.csv`는 서울 관련 행 3,000개이며, 샘플 전체 크기는
  `data/personas/` 기준 약 23MB라 팀 시연 재현을 위해 git에 포함하기로 했다.

### 샘플링/선별 논리

**1. 3,000개 샘플은 서울 사람 중 단순 랜덤인가?**

아니다. 정확히는 **서울 필터 + 재현 가능한 셔플 + 약한 층화 샘플링**이다.

- `district`에 `서울-...`이 들어간 행만 `is_seoulish=True`로 보고 필터링했다.
- 전체 Parquet를 내려받지 않고 Hugging Face 원격 Parquet row group을 읽었다.
- row group 순서와 row 순서를 `seed=42`로 섞어 매번 같은 결과가 나오게 했다.
- `age_group`, `family_type`, `occupation_group`, `housing_group`, `income_group`
  조합을 층화 키로 사용해 특정 조합이 너무 빨리 샘플을 독점하지 않게 했다.

따라서 이 샘플은 통계 추정을 위한 완전무작위 표본이라기보다, 발표/시나리오 생성을 위한
**서울 중심 재현 가능 층화 샘플**이다.

**2. 500개 relevant pool은 무엇을 주거 추천 신호로 봤는가?**

`scripts/build_persona_scenarios.py`가 페르소나 텍스트(`persona`, `detailed_persona`,
`family_persona`, `finance_persona`, `healthcare_persona`, 취미/직업 텍스트 등)를 보고
아래 신호를 태깅한다.

- `runner_active`: 러닝, 산책, 등산, 헬스, 운동, 배드민턴, 요가 등
- `pet`: 반려견, 반려동물, 강아지, 고양이 등
- `creative_freelance`: 화가, 작가, 디자이너, 프리랜서, 사진, 음악, 예술, 창작 등
- `mobility`: 출퇴근, 야근, 지하철, 버스, 대중교통, 통근, 퇴근 등
- `night_safety`: 야근, 밤, 안전, 늦은 귀가 등
- `health_hospital`: 병원, 건강, 혈압, 혈당, 당뇨, 고혈압, 보건소, 무릎 등
- `parent_care`: 부모, 어머니, 아버지, 조모, 고령, 돌봄 등
- `quiet_focus`: 조용함, 방음, 재택, 집에서 집중, 소음, 작업 등
- `rent_budget`: 월세, 전세, 대출, 내 집 마련, 생활비, 경제적 부담, 수입 등
- `convenience`: 마트, 편의점, 배달, 카페, 식당, 외식, 장보기 등
- `family_school`: 자녀, 학교, 보육, 아이, 학원, 어린이 등

이 신호를 쓴 이유는 두 가지다.

- 현재 서비스가 가진 지표(`안전`, `편의`, `이동`, `환경`, 상권 업종 추가)에 자연스럽게
  매핑되는 사용자 요구를 찾기 위해서.
- 동시에 현재 부족한 데이터(`월세/전세`, 실제 통근시간, 소음/방음, 남향/채광,
  반려동물 인프라, 학교/어린이집)를 드러내는 질문도 의도적으로 확보하기 위해서.

즉 500개는 "주거 추천 질문으로 전환했을 때 데이터 스키마를 검증할 가치가 큰
페르소나"를 추린 것이다.

**3. 84개 후보와 최종 30개는 어떻게 만들었는가?**

흐름은 다음과 같다.

1. `persona_sample_stratified.csv`의 3,000개 서울 샘플을 읽는다.
2. 각 페르소나에 주거 추천 신호를 태깅하고 점수를 매긴다.
3. 점수가 높은 500개를 `persona_relevant_pool.csv`로 저장한다.
4. 라이프스타일/부족 데이터/되묻기 유형을 반영한 템플릿으로 질문 후보 84개를 만든다.
   이때 질문마다 원본 페르소나의 연령대, 직업, 거주 구, 가족 형태, 주거 점유를
   앞부분에 붙여 실제 사용자 맥락처럼 보이게 했다.
5. 각 질문에 필요한 데이터 필드와 현재 서비스 카테고리를 붙인다.
   예: 야근+밤길 → `crime_rate`, `cctv_cnt`, `bus_cnt`, `subway_access`.
6. 각 질문을 `answerable`, `partial`, `not_answerable`, `clarify`로 태깅한다.
7. 최종 30개는 발표 검증 목적에 맞춰 아래 비율로 선별한다.
   - `answerable`: 18개
   - `partial`: 8개
   - `not_answerable`: 1개
   - `clarify`: 3개

이 과정의 핵심은 "데이터셋에서 자동으로 떨어진 질문 30개"가 아니라
**데이터셋 근거가 있는 질문 후보를 만들고, 현재 서비스의 데이터 커버리지 검증 목적에 맞게
큐레이션한 30개**라는 점이다.

### 최종 30개 시나리오의 우선순위

사용자가 최종 발표에서 강조하고 싶은 대상은 단순 "평균적인 이사 수요자"가 아니라,
**집값에는 잘 반영되지 않지만 자기 생활에서 중요한 세부 조건이 뚜렷한 사람들**이다.
따라서 시나리오 생성 시 아래 유형을 우선한다.

1. **라이프스타일이 확고한 MZ/1인 직장인 계열**
   - 러너, 헬스장 이용자, 공원·산책 루틴이 강한 사람
   - 반려동물 양육자
   - 프리랜서, 창작자, 화가, 재택근무자
   - 이동성 중시자(차 없음, 야근, 대중교통 의존)
2. **1인 가구가 아니어도 세부 주거 요구가 선명한 사람**
   - 남향·채광을 중요하게 보는 사람
   - 방음·조용함을 중요하게 보는 사람
   - 밤길 안정감, 생활 동선, 병원 접근성을 중요하게 보는 사람
3. **발표 데모에 쓰기 좋은 생활 편의형**
   - 부모님 병원 접근성
   - 헬스장/공원 가까운 동네
   - 카페·마트·편의점·배달 등 일상 루틴이 뚜렷한 동네 선호

### 30개 구성 비율

최종 30개는 원본 분포를 그대로 따르는 것이 아니라, 발표와 데이터 스키마 검증 목적에
맞게 후보군에서 큐레이션한다. 권장 비율은 다음과 같다.

- **현재 스키마로 답변 가능**: 18개
  - 안전, 편의, 이동, 환경, 병원, 공원, 헬스장/카페/버거집 같은 상권 업종으로
    현재 코드가 처리할 수 있는 질문.
- **부분 가능/부족 데이터 발견**: 9개
  - 월세·전세 시세, 실제 통근시간, 소음, 반려동물 인프라, 남향·채광, 방음 등
    지금 스키마에 없거나 약한 요구.
- **되묻기 필요**: 3개
  - "그냥 살기 좋은 데", "너무 복잡하지 않은 곳"처럼 의도가 모호해
    `needs_clarification=True`가 자연스러운 질문.

이 비율은 충분히 컨트롤 가능하다. 방법은 3,000개 샘플에서 후보 질문 60~100개를 먼저
만들고, 각 후보를 `answerable` / `partial` / `not_answerable`로 태깅한 뒤 위 비율에
맞춰 최종 30개를 고르는 것이다. 즉 "데이터셋에서 자동으로 떨어진 30개"가 아니라,
"데이터셋 근거가 있는 후보를 서비스 검증 목적에 맞게 선별한 30개"로 설명한다.

### 부족 데이터 처리 방침

부족 데이터는 지금 바로 전부 mock으로 넣지 않는다. 먼저 시나리오 후보를 만들고,
실제로 자주 등장하거나 발표 설득력이 큰 부족 항목만 골라 처리한다.

- 월세·전세 시세: 당장은 정밀 실거래가가 아니라 행정동/자치구별 중위값 또는
  경향 정도의 mock/보조 지표로 가볍게 반영하는 방향.
- 실제 통근시간: 중요도가 높지만 API/교통망 계산이 필요하므로 mock 또는 향후 확장 후보.
- 소음/방음: 집값에 잘 드러나지 않는 중요한 요구라 발표 설득력은 높다.
  데이터가 없으면 mock 또는 "현재 스키마 부족" 사례로 남긴다.
- 반려동물 인프라: 동물병원, 반려동물 카페/미용 등 상권 데이터로 일부 가능할 수 있어
  우선 후보를 확인한다.
- 남향·채광: 공공 행정동 지표로는 직접 답하기 어렵다. 현재 MVP 범위를 넘는
  세부 매물/건물 데이터 필요 항목으로 분류한다.

### 다음 산출물

시나리오 작업의 1차 산출물은 생성 완료됐다. 재생성 명령은 다음과 같다.

```bash
.venv/bin/python scripts/build_persona_scenarios.py
```

생성된 파일은 아래 4개다.

- `data/personas/persona_relevant_pool.csv`: 3,000개 중 주거 추천에 강한 후보 페르소나.
- `data/personas/persona_scenario_candidates.csv`: 질문 후보 84개.
- `data/personas/data_coverage_audit.csv`: 각 질문의 요구 데이터와 현재 스키마 커버리지.
- `data/personas/persona_scenarios_30.csv`: 발표/검증용 최종 30개.

현재 `persona_scenarios_30.csv`는 다음 비율로 구성되어 있다.

- `answerable`: 18개
- `partial`: 8개
- `not_answerable`: 1개
- `clarify`: 3개

즉 부족 데이터 계열은 총 9개(`partial`+`not_answerable`)로 맞춰져 있다. 최종 발표 전에는
이 30개 중 데모에 쓸 3~5개를 직접 실행해 보고, Solar 응답이 약한 문장은 질문 문장이나
mock 데이터 계획을 조정해야 한다.

### 시나리오 테스트 1차 결과와 수정 사항

`F01`, `F03`, `F04`, `F19`, `F28`을 실제 Solar 경로로 수동 테스트했다.

- `F03`(헬스장+공원), `F04`(부모님 병원 접근성)는 데모 후보로 적합했다.
- `F01`(안전+이동)은 대체로 맞지만, 별도 업종 추출이 과한 경우가 있어 추후
  extra category 프롬프트 개선 여지가 있다.
- `F19`(조용함/방음+공원)는 공원은 반영했지만, 방음/소음 데이터가 없다는 한계를
  설명하지 않아 수정이 필요했다.
- `F28`(모호한 질문)은 되묻기 대신 추천으로 흘러가서, 추후 clarify 기준 개선이 필요하다.

이번 수정에서는 먼저 **unsupported 조건 처리**를 강화했다.

- 새 모듈: `app/agent/unsupported_requirements.py`
- 감지 대상:
  - 조용함/소음/방음
  - 월세/전세/주거비(단, "현재 주거는 전·월세" 같은 배경 설명은 제외)
  - 실제 목적지 기반 통근시간
  - 남향/채광/일조
  - 반려동물 친화도
  - 학군/학교/어린이집
  - 주차 편의
- `SolarLLM._build_explain_prompt()`가 감지된 항목을
  "현재 데이터로 직접 평가할 수 없는 사용자 요구"로 프롬프트에 넣는다.
- `_EXPLAIN_SYSTEM`에 해당 항목은 추천 근거로 추정하지 말고, 별도 한계/보완 데이터로
  반드시 설명하라고 명시했다.
- `MockLLM.explain()`도 같은 감지 로직을 사용해 `[현재 데이터 한계]` 블록을 붙인다.

수정 이유: 발표/멘토링 대응에서 중요한 포인트는 "없는 데이터를 지어내지 않는다"는 점이다.
방음, 소음, 남향, 실제 통근시간처럼 행정동 공공지표로 직접 검증할 수 없는 요구는
추천 자체를 막지는 않되, 설명에서 현재 데이터 한계와 추가/mock 데이터 필요성을 분리해
말해야 한다.

검증:

```bash
.venv/bin/python -m pytest tests/test_solar_llm.py tests/test_mock_llm.py
```

현재 결과: 52 passed.

이후 추가로 **extra category 과잉 추출과 모호 질의 보정**을 적용했다.

문제:

- `F01`처럼 안전+이동만 요청한 질문에서 Solar가 `편의점`을 extra category로 넣었다.
- `F28`처럼 "회계사"라는 직업 배경이 들어간 모호한 질문에서 Solar가 `세무사` 업종을
  추론해 추천으로 진행했다.
- `F04`처럼 단순히 병원 접근성을 말한 질문에서 `대형병원 필수`로 과하게 해석될 수 있었다.

수정:

- 새 모듈: `app/agent/intent_sanitizer.py`
- `SolarLLM.parse_intent()` 후처리에서 LLM이 반환한 `extra_categories`와
  `required_categories`를 다시 검증한다.
- 업종은 사용자가 텍스트에 실제로 말한 경우만 남긴다.
  - 유지 예: "헬스장", "카페", "버거집", "동물병원"
  - 제거 예: "회계사" → `세무사`, "편의가 좋다" → `편의점`
- `require_large_hospital`은 "대형병원", "종합병원", "큰 병원", "상급종합병원" 같은
  표현이 있을 때만 유지한다. 단순 "병원 접근성"은 편의/병원 지표로 처리한다.
- "잘 맞는", "괜찮은", "살기 좋은", "삭막하지 않은"처럼 모호한 표현만 있고
  안전/교통/편의/환경/시설/예산 같은 구체 요구가 없으면 `needs_clarification=True`로 강제한다.
- "현재 주거는 전·월세" 같은 배경 설명은 월세/전세 시세 요구로 보지 않는다.

수정 이유: LLM이 사용자 배경(직업, 가족 형태, 현재 주거)에서 시설 요구를 추론하면,
결정론적 스코어링에 엉뚱한 가중치가 들어가 추천이 흔들린다. 시설 업종은 사용자가
명시적으로 말한 경우에만 도구 입력으로 넘기고, 모호한 질문은 추천보다 되묻기를 우선해야 한다.

검증:

```bash
.venv/bin/python -m pytest tests/
```

현재 결과: 136 passed, 1 warning.

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

7. **출구 LLM 문장에는 가중치·기여도·raw 지표 개수를 노출하지 않는다.**
   `scoring.py`/`tools.py`가 계산한 가중치·기여도·raw 수치(범죄율, CCTV·공원
   개수 등)는 `explain`이 "판단"할 근거로는 계속 쓰지만, 사용자에게 보여줄
   문장에는 그 숫자를 그대로 인용하지 않고 자연어로 풀어 쓴다("mobility 가중치
   0.526" 대신 "대중교통 접근성이 좋아 이동 부담이 적습니다"). 사용자가 직접
   요청한 업종의 실제 개수(예: "헬스장 3곳")는 예외 — 이건 내부 스코어링
   지표가 아니라 사용자가 물어본 사실이라 그대로 알려준다. raw 수치 자체는
   지도 hover 툴팁과 "🔍 적용된 필터 검증" expander(`streamlit_app.py`)에
   여전히 노출되므로 완전히 숨겨지는 건 아니고, "메인 응답 문장"에서만
   걷어낸 것이다. 이유: 사용자는 계산 근거보다 "왜 내 생활에 맞는지"를
   알고 싶어 한다 — 단, 스코어링/하드필터 로직 자체는 이 원칙과 무관하게
   그대로 유지한다(1번 원칙 참고). 강제하는 곳: `app/agent/solar_llm.py`의
   `_EXPLAIN_SYSTEM`, `app/agent/mock_llm.py`의 `MockLLM.explain()`.

7. **도구를 남발하지 않는다.**
   흐름은 입구→백엔드→출구로 고정. LLM이 여러 도구를 자율 연쇄 호출하는
   구조는 의도적으로 배제(오버엔지니어링). 되묻기 1회만 agentic 분기.

## 다음 할 일 (우선순위 순)

1. ~~**`main.py`(FastAPI/SSE)와 `streamlit_app.py`가 완전히 분리돼 있음.**~~ **해결됨.**
   두 앱을 각각 별도 프로세스로 유지하기로 결정(HTTP로 합치지 않음 — 네트워크
   왕복 없이 빠르고 로컬 개발도 간단해서). 대신 실제로 갈라져 있던 부분을
   `app/agent/factory.py`로 합쳤다:
   - mock 폴백 판단(`using_mock_llm`/`mock_llm_reason`)이 Streamlit에만 있고
     FastAPI는 키 없으면 그냥 죽던 것 → 팩토리 공유로 둘 다 동일하게 안전 폴백.
   - `top_n`이 `stream()`(FastAPI가 씀)엔 3으로 하드코딩, `run()`(Streamlit이 씀)엔
     파라미터였던 것 → `stream()`도 `top_n` 파라미터로 열림(`GET /recommend?top_n=`),
     `main.py` 기본값은 3 유지. 단, 근거 설명(`explain`/`explain_stream`)은 `top_n`과
     무관하게 항상 상위 3개만 근거로 삼는다(안 그러면 top_n=500일 때 프롬프트에
     500개 동네 수치를 통째로 실어보내게 됨) — `run()`은 원래 이렇게 했고 `stream()`도
     이제 맞춤.
   - 환경변수 `STREAMLIT_USE_MOCK_LLM` → `USE_MOCK_LLM`으로 개명(더 이상
     Streamlit 전용이 아니므로 — `.env.example`도 이 이름으로 맞출 것).
   - 각자 `RecommendationAgent()`를 새로 생성하던 것은 그대로 둠(프로세스별
     독립 인스턴스가 맞는 설계라 판단 — `factory.get_recommendation_agent()`가
     `main.py`용 프로세스 싱글턴, `factory.build_recommendation_agent()`가
     Streamlit의 `@st.cache_resource`가 감싸는 순수 생성 함수).
   - 테스트: `tests/test_agent_factory.py`(공유 로직), `tests/test_main.py`/
     `tests/test_loop.py`에 `top_n` 케이스 추가.
2. **Docker 멀티스테이지 빌드 + docker compose — 완료.**
   - `Dockerfile`: Python 3.12 slim 기반 멀티스테이지 빌드.
   - `docker-compose.yml`: `api`(FastAPI, 8000)와 `ui`(Streamlit, 8501)를 같은 이미지에서
     command만 바꿔 실행.
   - `.env.example`: `UPSTAGE_API_KEY`, `SOLAR_MODEL`, `UPSTAGE_API_BASE`,
     `USE_MOCK_LLM`, `KAKAO_REST_API_KEY`, `LANGFUSE_*` 분리.
   - `.dockerignore`: `.env`, 가상환경, 원본 `dataset/`, 페르소나 분석 산출물을 이미지에서 제외.
3. **GCE VM에 docker compose로 실제 배포 + GitHub Actions CI/CD — 완료.**
   - VM에서 repo clone → `.env` 작성(Langfuse 키 포함) → `dataset/` 원본 CSV(런타임에
     필요한 파일 1개만) 배치 → `docker compose up -d --build`.
   - GCE 방화벽에서 TCP 8000(API), 8501(Streamlit UI) 개방, 고정 IP로 승격 완료.
     절차는 `docs/deploy-gce.md`에 정리됨.
   - `.github/workflows/ci.yml`: push/PR마다 `python -m pytest tests/`와
     `docker build -t live-or-leave:ci .`를 실행.
   - `.github/workflows/cd.yml`(별도 분리): CI가 main에서 성공으로 끝나면
     `workflow_run`으로 트리거돼 전용 SSH 배포키(`GCE_SSH_PRIVATE_KEY` GitHub
     Secret)로 VM에 접속, `git pull` + `docker compose up -d --build`를 실행한다.
     PR에서는 절대 배포되지 않는다. 접속 대상 IP·계정명도 코드에 하드코딩하지
     않고 `GCE_HOST`/`GCE_USER` GitHub Secret으로 관리한다 — VM을 새로 만들어
     IP가 바뀌어도 `cd.yml`을 고칠 필요 없이 Secret 값만 갱신하면 된다.
   - **주의**: 이번 병합으로 `main.py`의 `GET /recommend`가 `top_n` 쿼리 파라미터를
     새로 받고 `/health`가 `mock_llm` 필드를 추가로 반환하게 됐다 — 배포된 API를
     쓰는 프론트가 있다면 하위호환 확인할 것(둘 다 기존 필드는 그대로 유지되는
     추가라 문제 없을 것으로 예상되지만, 실제 배포 후 확인 필요).
4. **핵심 시나리오 30개 구성** — `QUTUMENT/nemotron-personas-korea-extended`
   서울 중심 샘플을 기반으로 현실적인 질문 후보를 만들고, 현재 스키마 커버리지
   (`answerable`/`partial`/`not_answerable`)를 태깅한 뒤 실제 Solar API 대상으로 검증.
   (자세한 방법론은 위 "페르소나 시나리오 설계 기준" 절 참고.)
5. **LLMOps 운영 안정성 개선 — Langfuse 추적 적용 완료.** 이미 있던 재시도
   (`num_retries=2`)와 자체 가드레일(`intent_sanitizer.py`,
   `unsupported_requirements.py`)에 더해, Solar 호출 자체의 관측(Langfuse Tracing)을
   추가했다. 자세한 내용은 위 "Langfuse 기반 LLM 호출 추적 완료" 항목 참고.
6. **반경 1km 적절성 검증.** 큰 행정동(진관동·상계동)에서 부족할 수 있음.
   시설별 다른 반경(편의점 500m, 병원 1.5km) 실험. (Kakao "근처" 필터의
   `NEAR_RADIUS_KM`도 같은 종류의 근사 오차를 안고 있음 — 아래 "알려진 한계" 참고.)
7. **(사소함, 언제든) `dong_metrics.csv`의 병합행정동 7개 이름 인코딩 수정.**
   "상계3·4동" 같은 이름이 "상계3?4동"으로 깨져 있음 — 서울시 상권분석서비스
   원본 자체의 배포 시점 손실(우리 버그 아님, 자세한 근거는 세션 기록 참고).
   `build_dong_boundaries.py`의 `NAME_FIXES` 딕셔너리에 이미 정답이 있으니,
   그걸로 `dong_metrics.csv`도 고치면 다른 곳(explain 등)에서도 깨진 이름이
   안 보임. 지금은 지도 생성 시에만 보정되고 원본 CSV는 그대로.
8. **(보류 중, 메모리에 기록됨) "내 동네 진단" + `CompareTool` 버그 수정.**
   현재 주소를 채점해 다른 동네와 비교하는 기능. `agent/tools.py`의
   `CompareTool`이 `gu_a`/`gu_b`를 실제로는 dong 이름으로만 조회하는
   버그가 있음(죽은 코드라 지금은 무해). 착수 시 이것부터 고칠 것.
9. **(여유 있으면) 실패 케이스 처리 고도화.** 지금은 `num_retries=2`로 초기
   연결 실패만 자동 재시도한다. 스트리밍 도중 끊기는 경우(청크 일부만 받고
   중단)에 대한 재개 로직은 아직 없음 — MVP 범위에선 우선순위 낮음.

## 실행 방법

```bash
pip install -r requirements.txt   # litellm/fastapi/streamlit 등 포함, Python 3.9+ 필요
python demo.py                    # 시나리오 데모 (실제 Solar API, .env 필요)
uvicorn main:app --reload         # FastAPI 서버 (http://127.0.0.1:8000)
streamlit run streamlit_app.py    # 지도 UI (http://localhost:8501)
python -m pytest tests/           # 전체 유닛테스트 (206개, MockLLM 기반, 키 없이도 실행됨)
python build_dong_metrics.py      # 지표 테이블 재생성 (dataset/ 원본 CSV 필요)
python build_dong_boundaries.py   # 지도 GeoJSON 재생성 (space_info/ 원본 shapefile 필요)
```

`demo.py`/`main.py`가 실제 Solar API로 동작한다. 없으면 `solar_llm.py`의
`_call()`이 `RuntimeError`로 바로 실패한다 (mock으로 돌리려면
`RecommendationAgent(llm=MockLLM())`로 직접 교체). **`streamlit_app.py`는
예외** — 키가 없으면 스스로 감지해서 자동으로 `MockLLM`으로 폴백하고
화면에 "Mock LLM으로 동작 중"이라고 표시하므로, 지도 UI만 볼 거면 키 없이도
바로 된다. 같은 `.env`에 `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_HOST`까지
채우면 Solar 호출이 Langfuse Tracing 대시보드로 자동 전송된다(선택, 비워두면 무시됨).

`dong_metrics.csv`/`dong_boundaries.geojson`은 이미 커밋돼 있으므로, 원본
데이터(`dataset/`, `space_info/`, 둘 다 gitignore, 용량 커서 별도 확보 필요)
없이도 `demo.py`/`main.py`/`streamlit_app.py` 전부 바로 실행된다. 원본은
data.seoul.go.kr 등 서울 열린데이터광장에서 재다운로드하거나 팀 드라이브에서
받을 것.

주의: `build_dong_metrics.py`는 원본 공공데이터 CSV들이 `dataset/` 아래 있어야
동작한다. `dong_metrics.csv`는 이미 생성돼 있으므로, 앱만 돌릴 거면 빌더는 실행 불필요.

Docker Compose 실행:

```bash
cp .env.example .env
# .env에 UPSTAGE_API_KEY 입력
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

`http://127.0.0.1:8000`은 FastAPI, `http://127.0.0.1:8501`은 Streamlit 지도 UI다.
실제 Solar 경로에서 임의 업종 조회까지 보여주려면 VM/로컬 프로젝트 루트의 `dataset/`
원본 CSV가 docker compose volume으로 `/app/dataset`에 마운트되어야 한다.

## 알려진 한계 / 주의

- 범죄는 구 단위 → 같은 구 안 행정동은 범죄율 동일 (데이터 한계, 정직한 처리).
- 행정동 크기 중앙값 0.97km²(반지름 ~557m)라 반경 1km면 대부분 커버되나,
  거대 행정동(최대 12.7km²)은 중심점 근사 오차가 큼.
- CCTV 좌표 컬럼명은 `WGS84위도`/`WGS84경도` (다른 파일과 다름, 빌더에 반영됨).
- 좌표계: 시설은 위경도(4326), 행정동 중심점은 TM(5181). 빌더가 5181로 통일.
- **기관마다 행정구역 데이터 버전이 다르다.** 서울시 자체 시스템(상권분석서비스,
  생활인구)과 통계청 SGIS는 행정구역 개편 반영 시점이 다르다 — 예: 강남구
  일원2동은 2023년에 개포3동으로 편입됐는데, 서울시 쪽 데이터는 아직도 일원2동을
  별개로 취급한다. `dong_metrics.csv`는 서울시 쪽(구 경계) 기준이고,
  `dong_boundaries.geojson`은 통계청 SGIS(신 경계) 기준이라 지도 생성 시
  이름 매핑 보정이 필요했다 (`build_dong_boundaries.py`의 `NAME_FIXES`/
  `NAME_OVERRIDES` 참고). 새 공공데이터를 붙일 땐 이 버전 차이를 항상 의심할 것.
- **Streamlit 풀스크린 CSS가 내부 구현(비공개 API)에 의존한다.** `streamlit_app.py`의
  `FULLSCREEN_CSS`가 `data-testid`, 자동 생성된 emotion 클래스명(`.st-emotion-cache-*`)을
  직접 겨냥한다 — Streamlit이 공식 지원하는 게 아니라서 버전을 올리면 조용히
  깨질 수 있다. 실제로 지도 높이가 안 늘어나는 버그(flex-basis가 height보다
  우선 적용됨)를 한 번 겪었다. Streamlit 업그레이드 후 지도가 화면을 안
  채우면 여기부터 볼 것.
- **지도 카메라 위치(확대/이동)가 위젯 조작 시 초기화된다.** Plotly가 지도
  내용(색·핀)이 바뀔 때마다 컴포넌트를 완전히 새로 마운트하는 동작이라
  (`uirevision`을 걸어도 이 조합에선 안 먹힘, 직접 relayout 테스트로 확인),
  커스텀 JS 브릿지 없이는 못 고치는 것으로 판단해 받아들였다.
- **Kakao "근처" 반경(`NEAR_RADIUS_KM`, `app/agent/tools.py`)은 동 중심점
  기준이다.** 큰 행정동은 실제 경계까지의 거리가 반경보다 훨씬 멀 수 있음 —
  위 "반경 1km 적절성 검증" 항목과 같은 종류의 근사 오차.

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
streamlit run streamlit_app.py                  # .env에 키 있으면 실제 Solar API
USE_MOCK_LLM=1 streamlit run streamlit_app.py    # 빠른 반복 작업용: 강제 mock
```

화면 전체가 지도(기본 스타일: 어두움, 사이드바에서 위성사진 등으로 전환 가능)고
우측에 반투명 입력 패널이 뜬다. "필수 요구사항"/"선택 요구사항" 칸에 입력하고
**"동네 추천하기" 버튼을 눌러야** 추천이 실행된다(텍스트만 고치는 동안은
LLM 호출 없이 지도가 그대로 유지됨). 예:

- 필수: `헬스장 있어야 함` / 선택: `안전하고 무서운 밤길 없는 조용한 동네`
  → 헬스장 없는 동은 보라색(비추천·필수미충족)으로, 나머지는 안전+환경
  가중치로 초록(추천)/빨강(비추천·저점수)/회색(그 외)으로 티어링된다.
  상단 메시지에는 "mobility 가중치 0.526" 같은 내부 수치 대신 "대중교통
  접근성이 좋아..." 식 자연어 설명이 뜬다(raw 수치는 hover/"🔍 적용된 필터
  검증" expander에서 확인).

`.env`에 `UPSTAGE_API_KEY`가 없으면 `load_agent()`가 자동으로 mock으로 낮추고
화면 상단에 "⚠ Mock LLM으로 동작 중 (UPSTAGE_API_KEY 없음)" 캡션이 뜬다 — 앱이
죽지 않고 항상 실행은 된다(결정론적이라 위 예시 그대로 재현 가능). 키가 있어도
색깔·레이아웃만 반복 확인할 땐 `USE_MOCK_LLM=1`로 강제 전환하는 게 빠르다(이땐
캡션에 "USE_MOCK_LLM 설정됨"으로 표시). 버튼을 누를 때만 `parse_intent`+`explain`
2회가 호출되므로(같은 텍스트로 다시 누르면 캐시로 재호출 없이 즉시 응답),
실제 시연 때만 키를 넣고 Solar로 돌리는 걸 권장한다.
