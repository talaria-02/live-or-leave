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
- **Day4 배포 완료 (로컬 빌드 → GCE 실제 배포 → CI/CD)**: `Dockerfile`,
  `docker-compose.yml`, `.dockerignore`, `.env.example`, `docs/deploy-gce.md`를
  추가했다. FastAPI API(8000)와 Streamlit UI(8501)를 같은 Docker 이미지에서
  command만 다르게 실행한다. GCE VM(`us-central1-a`, e2-micro, 고정 IP)에 실제로
  clone·배포해 외부에서 `http://<VM_IP>:8000/health`, `http://<VM_IP>:8501`
  접속을 확인했다. GitHub Actions는 `.github/workflows/ci.yml`(테스트 +
  Docker 이미지 빌드)과 `.github/workflows/cd.yml`(CI 성공 시 `workflow_run`으로
  트리거돼 VM에 SSH로 재배포)로 분리돼 있다 — main에 push하면 테스트 통과 후
  자동으로 VM에 최신 코드가 반영된다.
- **Langfuse 기반 LLM 호출 추적 완료**: `solar_llm.py`의 `_configure_langfuse_tracing()`이
  `LANGFUSE_PUBLIC_KEY`가 설정된 경우에만 `litellm.success_callback`/`failure_callback`에
  `"langfuse"`를 등록한다. 키가 없으면 완전히 무시되고 평소처럼 동작한다(옵션 기능).
- **페르소나 기반 시나리오 샘플링 완료**: `QUTUMENT/nemotron-personas-korea-extended`
  (NVIDIA Nemotron-Personas-Korea 확장판 미러, CC BY 4.0)에서 전체 Parquet를
  내려받지 않고 Hugging Face 원격 Parquet row group을 읽어 서울 중심 샘플을 생성했다.
  `data/personas/persona_sample_probe.csv`(50행), `persona_sample_500.csv`(500행),
  `persona_sample_stratified.csv`(3,000행)가 있으며, `data/personas/README.md`에
  출처·라이선스·재현 명령·컬럼 정책을 적어두었다. 최종 발표 시 이 샘플을 기반으로
  "페르소나 기반 핵심 검증 시나리오 30개"를 만들 계획이다.
- **흐름 검증 테스트 통과**: `python -m pytest tests/` (128개, 전부 MockLLM 기반이라
  네트워크·API 키 없이 빠르게 실행됨).

## 파일 지도

```
main.py                  # FastAPI 컨트롤러. GET /health, GET /recommend(SSE)
scripts/
  sample_qutument_personas.py  # QUTUMENT Extended 원격 Parquet에서 서울 중심 샘플 생성
  build_persona_scenarios.py   # 샘플 → 후보 질문/커버리지 감사/최종 30개 생성
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
    unsupported_requirements.py  # 현재 데이터로 직접 검증 불가한 사용자 요구 감지
    intent_sanitizer.py          # LLM 의도 출력 후처리(업종 과잉 추론 방지, 모호 질의 보정)
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
tests/test_main.py        # FastAPI 컨트롤러 테스트 (TestClient, MockLLM으로 의존성 오버라이드)
tests/test_flow.py        # 흐름 검증 (MockLLM 명시 주입)
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

7. **도구를 남발하지 않는다.**
   흐름은 입구→백엔드→출구로 고정. LLM이 여러 도구를 자율 연쇄 호출하는
   구조는 의도적으로 배제(오버엔지니어링). 되묻기 1회만 agentic 분기.

## 다음 할 일 (우선순위 순)

1. **Docker 멀티스테이지 빌드 + docker compose — 완료.**
   - `Dockerfile`: Python 3.12 slim 기반 멀티스테이지 빌드.
   - `docker-compose.yml`: `api`(FastAPI, 8000)와 `ui`(Streamlit, 8501)를 같은 이미지에서
     command만 바꿔 실행.
   - `.env.example`: `UPSTAGE_API_KEY`, `SOLAR_MODEL`, `UPSTAGE_API_BASE`,
     `STREAMLIT_USE_MOCK_LLM`, `LANGFUSE_*` 분리.
   - `.dockerignore`: `.env`, 가상환경, 원본 `dataset/`, 페르소나 분석 산출물을 이미지에서 제외.
2. **GCE VM에 docker compose로 실제 배포 — 완료.**
   - VM에서 repo clone → `.env` 작성(Langfuse 키 포함) → `dataset/` 원본 CSV(런타임에
     필요한 파일 1개만) 배치 → `docker compose up -d --build`.
   - GCE 방화벽에서 TCP 8000(API), 8501(Streamlit UI) 개방, 고정 IP로 승격 완료.
   - 절차는 `docs/deploy-gce.md`에 정리됨.
3. **GitHub Actions CI/CD — 완료.**
   - `.github/workflows/ci.yml`: push/PR마다 `python -m pytest tests/`와
     `docker build -t live-or-leave:ci .`를 실행.
   - `.github/workflows/cd.yml`: CI가 main에서 성공으로 끝나면 `workflow_run`으로
     트리거돼 전용 SSH 배포키(`GCE_SSH_PRIVATE_KEY` GitHub Secret)로 VM에 접속,
     `git pull` + `docker compose up -d --build`를 실행한다. PR에서는 절대 배포되지 않는다.
4. **핵심 시나리오 30개 구성** — `QUTUMENT/nemotron-personas-korea-extended`
   서울 중심 샘플을 기반으로 현실적인 질문 후보를 만들고, 현재 스키마 커버리지
   (`answerable`/`partial`/`not_answerable`)를 태깅한 뒤 실제 Solar API 대상으로 검증.
5. **LLMOps 운영 안정성 개선 — Langfuse 추적 적용 중.** 이미 있던 재시도
   (`num_retries=2`)와 자체 가드레일(`intent_sanitizer.py`,
   `unsupported_requirements.py`)에 더해, Solar 호출 자체의 관측(Langfuse Tracing)을
   추가했다. 자세한 내용은 위 "Langfuse 기반 LLM 호출 추적 완료" 항목 참고.
6. **(여유 있으면)** 반경 1km 적절성 검증(큰 행정동에서 부족할 수 있음),
   스트리밍 도중 끊김 대응 등 실패 케이스 고도화.

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
같은 `.env`에 `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_HOST`까지
채우면 Solar 호출이 Langfuse Tracing 대시보드로 자동 전송된다(선택, 비워두면 무시됨).

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
