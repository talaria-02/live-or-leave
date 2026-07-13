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
  `required_categories`(하드 필터, AND 조건)와 `extra_categories`(점수화)가 분리돼
  있다. `mock_llm.py`는 `"필수 요구사항:"`/`"선택 요구사항:"` 마커로 텍스트를
  나눠 각각 다르게 처리(마커 없으면 전부 선택으로 취급, 하위호환). 하드필터에
  걸린 동은 `scoring.partition_by_required_categories()`가 "왜 떨어졌는지"
  (`missing` 목록)까지 함께 반환 — UI가 이유를 보여줄 수 있음.
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
  - `required_near`(예: "서울대 근처") — 업종 존재 필터와는 다른 의미론. 장소
    좌표 1개만 찾아 동 중심점과의 거리(`NEAR_RADIUS_KM`, 현재 3km)로 하드
    필터한다. 이름 매칭(예: "서울대" 상호 890곳 매칭)과 섞으면 엉뚱한 동이
    통과하는 버그가 났었음 — 그래서 분리.
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
- **흐름 검증 테스트 통과**: `python -m pytest tests/` (180개, 전부 MockLLM
  기반 + Kakao/네트워크는 monkeypatch로 격리라 API 키 없이도 빠르게 실행됨).

## 파일 지도

```
main.py                  # FastAPI 컨트롤러. GET /health, GET /recommend(SSE)
streamlit_app.py         # Streamlit UI — 지도+필수/선택 입력 (아래 "Streamlit UI 직접 확인하기" 참고)
app/
  schemas/
    domain.py      # DongRawMetrics, DongScores, Recommendation, CATEGORY_CAVEATS(가공방식 각주)
    tools.py       # Importance(4단계 라벨), CategoryPreference, ParsedIntent, 도구 스키마
                   # (extra_categories=점수화, required_categories=하드필터)
  services/
    scoring.py     # 결정론적 계산: 분위수 정규화·스코어링·순위·필수업종 필터(+탈락사유)
  agent/
    solar_llm.py   # ★ 프로덕션 기본 LLM. Upstage Solar API를 LiteLLM 경유로 호출(스트리밍 지원) ★
    mock_llm.py    # 키워드 매칭 스텁. 이제는 테스트 전용(RecommendationAgent(llm=MockLLM()))
    tools.py       # ToolExecutor: 도구를 scoring 서비스에 위임, 임의/필수 업종 카운트 조회
    loop.py        # ReAct 흐름 오케스트레이터. run(top_n=)=완성된 결과, stream(top_n=)=SSE용 제너레이터
    factory.py     # main.py/streamlit_app.py가 공유하는 mock 판단·에이전트 생성 (신규)
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
.env                      # UPSTAGE_API_KEY 등 (gitignore됨, 각자 로컬에 개별 생성)
dataset/                  # 원본 공공데이터 (gitignore됨, ~160MB, data.seoul.go.kr 등에서 재확보)
space_info/               # 원본 행정동 shapefile+코드표 (gitignore됨, 지도 재생성용)
tests/test_main.py               # FastAPI 컨트롤러 테스트 (TestClient, MockLLM으로 의존성 오버라이드)
tests/test_flow.py               # 흐름 검증 (MockLLM 명시 주입)
tests/test_agent_factory.py      # app/agent/factory.py 공유 로직 테스트
tests/test_kakao_facility_repository.py  # Kakao 저장소 + '근처' 거리 필터 테스트 (네트워크 없이, monkeypatch)
tests/test_streamlit_app.py      # streamlit_app.py 고유 로직(캐싱·지도 완전성) 테스트
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
     Streamlit 전용이 아니므로).
   - 각자 `RecommendationAgent()`를 새로 생성하던 것은 그대로 둠(프로세스별
     독립 인스턴스가 맞는 설계라 판단 — `factory.get_recommendation_agent()`가
     `main.py`용 프로세스 싱글턴, `factory.build_recommendation_agent()`가
     Streamlit의 `@st.cache_resource`가 감싸는 순수 생성 함수).
   - 테스트: `tests/test_agent_factory.py`(공유 로직), `tests/test_main.py`/
     `tests/test_loop.py`에 `top_n` 케이스 추가.
2. **GCP 배포** ($300 크레딧). MVP 마무리. `dong_boundaries.geojson`/`dong_metrics.csv`는
   이미 커밋돼 있어 `dataset/`·`space_info/`(원본, gitignore) 없이도 두 앱 다 바로 뜬다.
3. **반경 1km 적절성 검증.** 큰 행정동(진관동·상계동)에서 부족할 수 있음.
   시설별 다른 반경(편의점 500m, 병원 1.5km) 실험.
4. **(사소함, 언제든) `dong_metrics.csv`의 병합행정동 7개 이름 인코딩 수정.**
   "상계3·4동" 같은 이름이 "상계3?4동"으로 깨져 있음 — 서울시 상권분석서비스
   원본 자체의 배포 시점 손실(우리 버그 아님, 자세한 근거는 세션 기록 참고).
   `build_dong_boundaries.py`의 `NAME_FIXES` 딕셔너리에 이미 정답이 있으니,
   그걸로 `dong_metrics.csv`도 고치면 다른 곳(explain 등)에서도 깨진 이름이
   안 보임. 지금은 지도 생성 시에만 보정되고 원본 CSV는 그대로.
5. **(보류 중, 메모리에 기록됨) "내 동네 진단" + `CompareTool` 버그 수정.**
   현재 주소를 채점해 다른 동네와 비교하는 기능. `agent/tools.py`의
   `CompareTool`이 `gu_a`/`gu_b`를 실제로는 dong 이름으로만 조회하는
   버그가 있음(죽은 코드라 지금은 무해). 착수 시 이것부터 고칠 것.
6. **(여유 있으면) 실패 케이스 처리 고도화.** 지금은 `num_retries=2`로 초기
   연결 실패만 자동 재시도한다. 스트리밍 도중 끊기는 경우(청크 일부만 받고
   중단)에 대한 재개 로직은 아직 없음 — MVP 범위에선 우선순위 낮음.

## 실행 방법

```bash
pip install -r requirements.txt   # litellm/fastapi/streamlit 등 포함, Python 3.9+ 필요
python demo.py                    # 시나리오 데모 (실제 Solar API, .env 필요)
uvicorn main:app --reload         # FastAPI 서버 (http://127.0.0.1:8000)
streamlit run streamlit_app.py    # 지도 UI (http://localhost:8501)
python -m pytest tests/           # 전체 유닛테스트 (180개, MockLLM 기반, 키 없이도 실행됨)
python build_dong_metrics.py      # 지표 테이블 재생성 (dataset/ 원본 CSV 필요)
python build_dong_boundaries.py   # 지도 GeoJSON 재생성 (space_info/ 원본 shapefile 필요)
```

`.env`(프로젝트 루트, gitignore됨)에 `UPSTAGE_API_KEY=본인의_키`를 넣어야
`demo.py`/`main.py`가 실제 Solar API로 동작한다. 없으면 `solar_llm.py`의
`_call()`이 `RuntimeError`로 바로 실패한다 (mock으로 돌리려면
`RecommendationAgent(llm=MockLLM())`로 직접 교체). **`streamlit_app.py`는
예외** — 키가 없으면 스스로 감지해서 자동으로 `MockLLM`으로 폴백하고
화면에 "Mock LLM으로 동작 중"이라고 표시하므로, 지도 UI만 볼 거면 키 없이도
바로 된다.

`dong_metrics.csv`/`dong_boundaries.geojson`은 이미 커밋돼 있으므로, 원본
데이터(`dataset/`, `space_info/`, 둘 다 gitignore, 용량 커서 별도 확보 필요)
없이도 `demo.py`/`main.py`/`streamlit_app.py` 전부 바로 실행된다. 원본은
data.seoul.go.kr 등 서울 열린데이터광장에서 재다운로드하거나 팀 드라이브에서
받을 것.

주의: `build_dong_metrics.py`는 원본 공공데이터 CSV들이 `dataset/` 아래 있어야
동작한다. `dong_metrics.csv`는 이미 생성돼 있으므로, 앱만 돌릴 거면 빌더는 실행 불필요.

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
**포커스를 벗어나면**(다른 곳 클릭 또는 Ctrl+Enter) 자동으로 재계산된다 — 버튼 없음. 예:

- 필수: `헬스장 있어야 함` / 선택: `안전하고 무서운 밤길 없는 조용한 동네`
  → 헬스장 없는 동은 보라색(비추천·필수미충족)으로, 나머지는 안전+환경
  가중치로 초록(추천)/빨강(비추천·저점수)/회색(그 외)으로 티어링된다.

`.env`에 `UPSTAGE_API_KEY`가 없으면 `load_agent()`가 자동으로 mock으로 낮추고
화면 상단에 "⚠ Mock LLM으로 동작 중 (UPSTAGE_API_KEY 없음)" 캡션이 뜬다 — 앱이
죽지 않고 항상 실행은 된다(결정론적이라 위 예시 그대로 재현 가능). 키가 있어도
색깔·레이아웃만 반복 확인할 땐 `USE_MOCK_LLM=1`로 강제 전환하는 게 빠르다(이땐
캡션에 "USE_MOCK_LLM 설정됨"으로 표시). 이 UI는 입력창 값이 바뀔 때마다
(포커스 아웃/Ctrl+Enter) `parse_intent`+`explain` 2회를 다시 호출하는 구조라,
실제 시연 때만 키를 넣고 Solar로 돌리는 걸 권장한다.
