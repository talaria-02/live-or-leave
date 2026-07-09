# 살래말래 (Live or Leave) — 서울시 개인화 주거 지역 추천 MVP

사용자의 자연어 라이프스타일 조건을 바탕으로 서울 25개 자치구 중 적합한 주거 후보 지역을 추천하는 MVP입니다.

오늘 MVP의 핵심 시나리오는 다음입니다.

> 나는 러닝을 좋아하는 20대 남자야. 근처에 공원과 햄버거집이 많은 동네를 추천해줘.

이 질의에서 시스템은 아래 선호를 추출해 점수 계산에 반영합니다.

| 키워드 | 매핑되는 점수 |
|---|---|
| 러닝 | `running_score` |
| 공원 | `park_score` |
| 햄버거집 | `food_score` |
| 20대 생활 인프라 | `lifestyle_score` |

추천 단위는 **서울 25개 자치구**입니다 (행정동 단위는 오늘 범위 밖).

## 현재 구현된 MVP 범위

### 오늘 범위

- 서울 25개 자치구 단위 추천
- 공원 / 러닝 / 햄버거집 / 생활 인프라 중심 점수화
- 규칙 기반 자연어 키워드 추출 (LLM 미사용)
- 결정론적 점수 계산 (동일 입력 → 항상 동일 출력)
- FastAPI `POST /recommend` API
- pytest 기반 핵심 시나리오 테스트 ([tests/test_recommendation.py](tests/test_recommendation.py))

### 오늘 제외한 범위 (추후 확장 대상)

- 행정동 단위 추천
- 좌표 기반 거리 계산
- 지도 히트맵 시각화
- 실시간 매물 연동
- 주거비 / 교통 / 안전 점수 반영
- LLM 기반 복잡한 ReAct Agent
- Text-to-SQL
- 장기 사용자 선호 기억

## 프로젝트 구조

```
live-or-leave-team/
├── app/
│   ├── main.py                        # FastAPI 앱, GET / , POST /recommend
│   ├── schemas/
│   │   └── recommendation.py          # 요청/응답 Pydantic 모델
│   ├── services/
│   │   ├── recommendation_service.py  # 선호 추출·가중치·Top3 계산
│   │   └── score_adapter.py           # region_features.csv → region_scores.csv 변환
│   └── data_pipeline/
│       └── build_region_features.py   # 원천/Mock 데이터 → region_features.csv 생성
├── docs/
│   ├── data_inventory.md              # 원천 데이터 목록 및 출처
│   ├── feature_schema.md              # feature 컬럼별 정의·Mock 여부
│   └── mock_policy.md                 # Mock/파생 feature 정책
├── processed/
│   ├── region_features.csv            # 자치구별 원천 feature 테이블
│   └── region_scores.csv              # 추천 로직이 사용하는 최종 점수 테이블
├── tests/
│   └── test_recommendation.py         # 핵심 시나리오 API 테스트
├── requirements.txt
└── README.md
```

## 데이터 처리 흐름

```
수집 데이터 / 현실성 있는 Mock 데이터
        ↓
processed/region_features.csv   (app/data_pipeline/build_region_features.py)
        ↓
app/services/score_adapter.py
        ↓
processed/region_scores.csv
        ↓
app/services/recommendation_service.py
        ↓
FastAPI POST /recommend
```

추천 로직은 원본 공공데이터 파일을 직접 참조하지 않고, 최종적으로 `processed/region_scores.csv`만 사용합니다.

### 1. `region_features.csv`

자치구별 원천 feature 테이블입니다 ([app/data_pipeline/build_region_features.py](app/data_pipeline/build_region_features.py)에서 생성).

컬럼: `region_name`, `park_count`, `park_area_per_person`, `park_ratio`, `large_park_count`, `food_count`, `cafe_count`, `hamburger_count`, `fastfood_count`, `running_friendly_score`, `commercial_area_score`

### 2. `region_scores.csv`

추천 로직에서 실제로 사용하는 점수 테이블입니다 ([app/services/score_adapter.py](app/services/score_adapter.py)에서 생성).

핵심 컬럼: `region_name`, `park_score`, `food_score`, `running_score`, `lifestyle_score`, `final_score`, `grade`

### 3. `recommendation_service.py`

사용자 query에서 선호 조건을 추출하고, query 기반 가중치로 `final_score`를 재계산해 Top 3를 반환합니다.

## 데이터 및 Mock 정책

현재 MVP는 **실제 수집 데이터**와 **일부 Mock/파생 feature**를 함께 사용합니다. 자세한 내용은 [docs/mock_policy.md](docs/mock_policy.md), [docs/feature_schema.md](docs/feature_schema.md)를 참고하세요.

**실제 데이터 기반 feature**

- `park_area_per_person`, `park_ratio` — 서울시 공원 통계
- `food_count`, `cafe_count`, `hamburger_count`, `fastfood_count` — 소상공인시장진흥공단 상가업소 데이터

**Mock 또는 파생 feature**

- `park_count`, `large_park_count` — 개별 공원 목록 데이터가 없어 공원 통계 기반으로 파생 생성
- `running_friendly_score` — 산책로/보행환경 데이터가 없어 공원 관련 feature의 가중합으로 대체
- `commercial_area_score` — 여러 상권 feature의 정규화 가중합으로 파생 생성

**투명성 원칙**

- Mock은 아무 값이나 넣은 것이 아니라, 핵심 시나리오 데모를 위해 실제 데이터 구조에 맞춰 부족한 feature를 보완한 값입니다.
- 추천 로직은 Mock 여부에 의존하지 않고 `region_scores.csv`의 점수만 사용합니다.
- 추후 실제 산책로, 운동시설, 공원 접근성, 상권 밀도 데이터가 확보되면 Mock feature를 값만 교체하면 됩니다 (컬럼 구조는 유지).

## 점수 계산 방식

Score Adapter([app/services/score_adapter.py](app/services/score_adapter.py))가 `region_features.csv`의 각 feature를 0~100 min-max 정규화한 뒤 아래 가중합으로 카테고리 점수를 만듭니다.

| 점수 | 구성 feature |
|---|---|
| `park_score` | `park_count`, `park_area_per_person`, `park_ratio`, `large_park_count` |
| `food_score` | `food_count`, `cafe_count`, `hamburger_count`, `fastfood_count` |
| `running_score` | `running_friendly_score`, `park_score` |
| `lifestyle_score` | `commercial_area_score`, `food_score`, `cafe_count_score` |

**final_score** (핵심 시나리오 기준 기본 가중치)

```python
final_score = (
    0.35 * running_score
    + 0.30 * park_score
    + 0.25 * food_score
    + 0.10 * lifestyle_score
)
```

`region_scores.csv`에 저장된 `final_score`는 이 기본 가중치 기준값입니다. 실제 API 호출 시에는 query에서 감지된 preference에 따라 가중치가 boost·재정규화되고, `final_score`도 그 가중치로 다시 계산됩니다 ([app/services/recommendation_service.py](app/services/recommendation_service.py)의 `build_weights`, `calculate_query_scores`).

## 자연어 조건 추출 방식

현재는 **LLM이 아니라 규칙 기반 키워드 매칭**을 사용합니다 ([app/services/recommendation_service.py](app/services/recommendation_service.py)의 `KEYWORD_GROUPS`).

| preference | 키워드 |
|---|---|
| `running` | 러닝, 달리기, 조깅, 운동, 산책 |
| `park` | 공원, 녹지, 한강, 산책로 |
| `food` | 햄버거, 버거, 맥도날드, 롯데리아, 버거킹, 맘스터치, KFC |
| `lifestyle` | 20대, 대학생, 사회초년생, 카페, 놀거리, 상권 |

## 설치

의존성(FastAPI, pandas 등)은 가상환경(`.venv`)에만 설치되어 있습니다. 아래 명령을 먼저 실행해 활성화하세요.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> venv를 활성화하지 않고 `pytest`, `uvicorn` 명령을 바로 실행하면 시스템 기본 python이 잡혀 `ModuleNotFoundError: No module named 'fastapi'` 또는 `command not found: uvicorn`이 발생합니다. 항상 `source .venv/bin/activate`를 먼저 실행하세요.

## API 사용법

### 서버 실행

```bash
uvicorn app.main:app --reload
```

또는 uv를 사용하는 경우:

```bash
uv run uvicorn app.main:app --reload
```

### Swagger UI

```
http://127.0.0.1:8000/docs
```

### Health Check

`GET /`

```json
{
  "status": "ok",
  "message": "Recommendation API is running"
}
```

### 추천 API

`POST /recommend`

Request:

```json
{
  "query": "나는 러닝을 좋아하는 20대 남자야. 근처에 공원과 햄버거집이 많은 동네를 추천해줘."
}
```

Response 예시:

```json
{
  "query": "나는 러닝을 좋아하는 20대 남자야. 근처에 공원과 햄버거집이 많은 동네를 추천해줘.",
  "matched_preferences": ["running", "park", "food", "lifestyle"],
  "weights": {
    "running_score": 0.37,
    "park_score": 0.29,
    "food_score": 0.25,
    "lifestyle_score": 0.09
  },
  "recommendations": [
    {
      "rank": 1,
      "region_name": "송파구",
      "final_score": 84.2,
      "grade": "green",
      "reason": "송파구는 데이터 기준 러닝 친화도와 공원 관련 점수가 높고, 햄버거/외식 인프라도 좋은 편입니다.",
      "score_breakdown": {
        "running_score": 86.0,
        "park_score": 82.5,
        "food_score": 79.2,
        "lifestyle_score": 72.1
      },
      "matched_preferences": ["running", "park", "food", "lifestyle"]
    }
  ]
}
```

> 특정 자치구 순위는 `region_features.csv`/Mock 값이 바뀌면 달라질 수 있습니다. 위 예시는 응답 구조 참고용입니다.

## 테스트 방법

`.venv`를 활성화한 상태에서 실행합니다 (`source .venv/bin/activate`).

```bash
pytest
```

특정 테스트 파일만 실행:

```bash
pytest tests/test_recommendation.py -v
```

> 프로젝트 루트의 `pytest.ini`(`pythonpath = .`)가 `app` 모듈을 찾도록 경로를 설정해줍니다. 이 파일이 없으면 `ModuleNotFoundError: No module named 'app'`이 발생합니다.

`uv`를 사용하는 경우 (uv가 `.venv`를 자동으로 인식합니다):

```bash
uv run pytest
uv run pytest tests/test_recommendation.py -v
```

[tests/test_recommendation.py](tests/test_recommendation.py)에서 확인하는 내용:

- `GET /` health check
- `POST /recommend` 핵심 시나리오 응답 구조
- `matched_preferences` 추출
- `weights` 합이 1인지
- Top 3 추천 결과 반환
- `final_score` 0~100 범위
- `grade` 값 검증 (`green`/`orange`/`red`)
- 추천 결과 `final_score` 내림차순 정렬
- 빈 query validation (422)
- 부분 조건 query 동작 (예: "공원이 많은 동네를 추천해줘.")

## 개발 순서 요약

1. `docs/data_inventory.md` 작성
2. `docs/feature_schema.md` 작성
3. `processed/region_features.csv` 생성
4. `app/services/score_adapter.py` 작성
5. `processed/region_scores.csv` 생성
6. `app/services/recommendation_service.py` 작성
7. `app/schemas/recommendation.py` 작성
8. `app/main.py`에서 `/recommend` API 연결
9. `tests/test_recommendation.py` 작성
10. README.md 업데이트

## 추후 확장 방향

1. **주거비 데이터 반영** — 서울시 부동산 전월세가 정보 기반 `rent_score` 추가
2. **교통 접근성 반영** — 지하철역/버스정류소 위치 데이터 기반 `transport_score` 추가
3. **안전 지표 반영** — 범죄 발생 현황, CCTV 설치 현황 기반 `safety_score` 추가
4. **행정동 단위 추천** — 공간조인과 행정경계 데이터 적용
5. **지도 히트맵 시각화** — Streamlit 또는 지도 라이브러리 활용
6. **LLM 기반 조건 추출** — 현재 규칙 기반 키워드 추출을 LLM parser로 교체
7. **설명 생성 고도화** — 실제 지표 수치를 포함한 더 자연스러운 추천 근거 생성
