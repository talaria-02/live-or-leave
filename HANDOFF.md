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
  모호하면 되묻기 1회. `demo.py`로 3개 시나리오 동작 확인됨.
- **흐름 검증 테스트 통과**: `python -m tests.test_flow` (6개 검증).

## 지금 무엇이 가짜인가 (여기가 다음 작업)

- **`app/agent/mock_llm.py`가 진짜 LLM이 아님**. "안전" 같은 글자를 세는 키워드
  매칭으로 HCX를 흉내낸 스텁이다. 이걸 실제 HyperCLOVA X 호출로 교체하는 것이
  가장 우선순위 높은 다음 작업.
- 교체는 **이 파일 하나만** 바꾸면 된다. `parse_intent`와 `explain`의 시그니처를
  유지한 채 내부를 HCX 호출로 바꾸면 나머지 계층은 불변. (레이어 분리의 목적)

## 파일 지도

```
app/
  schemas/
    domain.py      # DongRawMetrics, DongScores, Recommendation (데이터 구조)
    tools.py       # Importance(4단계 라벨), CategoryPreference, ParsedIntent, 도구 스키마
  services/
    scoring.py     # 결정론적 계산: 분위수 정규화·스코어링·순위 (LLM 없음, 핵심 로직)
  agent/
    mock_llm.py    # ★ 가짜 LLM. 여기를 HCX로 교체 ★
    tools.py       # ToolExecutor: 도구를 scoring 서비스에 위임
    loop.py        # ReAct 흐름 오케스트레이터 (입구→백엔드→출구, 되묻기)
  data/
    csv_repository.py  # dong_metrics.csv를 읽어 DongRawMetrics로 공급
build_dong_metrics.py  # 원본 CSV → dong_metrics.csv 생성 (파이프라인)
dong_metrics.csv       # 행정동 지표 테이블 (빌더 산출물)
seoul_gu.geojson       # 자치구 경계 (참고용)
demo.py                # 시나리오 데모 실행
tests/test_flow.py     # 흐름 검증
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

1. **[최우선] mock_llm.py → HCX 교체.** LiteLLM 경유 HyperCLOVA X 호출.
   - parse_intent: 문장 → CategoryPreference 라벨 JSON (temperature 낮게, 스키마 강제)
   - explain: 추천지 수치 → 근거 설명 (제공 수치만 사용 제약)
   - 파싱 실패 시 폴백(균등분배)·합=1 정규화는 유지.
   - 키워드 매칭 mock과 스위칭 가능하게 두면 키 없을 때도 개발 가능.
2. **FastAPI 컨트롤러(main.py) 추가.** 지금 컨트롤러 계층이 없고 demo.py가 대신함.
   HTTP 요청 → RecommendationAgent 호출 → 응답. 레이어의 마지막 조각.
3. **반경 1km 적절성 검증.** 큰 행정동(진관동·상계동)에서 부족할 수 있음.
   시설별 다른 반경(편의점 500m, 병원 1.5km) 실험.
4. **최소 UI (Streamlit 등)** + **GCP 배포** ($300 크레딧). MVP 마무리.

## 실행 방법

```bash
pip install pydantic scipy numpy pyproj  # 의존성
python demo.py                # 시나리오 데모
python -m tests.test_flow     # 흐름 검증
python -m pytest tests/       # 전체 유닛테스트 (scoring/schemas/mock_llm/hcx_llm/agent/csv)
python build_dong_metrics.py  # 지표 테이블 재생성 (원본 CSV 필요)
```

주의: `build_dong_metrics.py`는 원본 공공데이터 CSV들이 `/mnt/user-data/uploads`
경로에 있어야 동작한다. 로컬에서 돌리려면 그 CSV들을 확보하고 경로를 수정할 것.
`dong_metrics.csv`는 이미 생성돼 있으므로, 앱만 돌릴 거면 빌더는 실행 불필요.

## 알려진 한계 / 주의

- 범죄는 구 단위 → 같은 구 안 행정동은 범죄율 동일 (데이터 한계, 정직한 처리).
- 행정동 크기 중앙값 0.97km²(반지름 ~557m)라 반경 1km면 대부분 커버되나,
  거대 행정동(최대 12.7km²)은 중심점 근사 오차가 큼.
- CCTV 좌표 컬럼명은 `WGS84위도`/`WGS84경도` (다른 파일과 다름, 빌더에 반영됨).
- 좌표계: 시설은 위경도(4326), 행정동 중심점은 TM(5181). 빌더가 5181로 통일.
