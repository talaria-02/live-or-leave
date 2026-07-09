# Day2 Quality Checklist

## 1. 오늘 놓치기 쉬운 구현 포인트

| 항목 | 반영 방식 | 현재 프로젝트 적용 |
|---|---|---|
| Controller / Service / Tool 레이어 분리 | API 요청 처리, 비즈니스 로직, Agent Tool 호출 책임을 처음부터 분리한다. | `app/api`, `app/services`, `app/tools`, `app/agents`, `app/repositories`, `app/schemas` 구조로 분리한다. |
| Tool Schema를 Pydantic으로 명확히 정의 | LLM 또는 Agent가 Tool 인자를 잘못 채우지 않도록 입력/출력 모델을 고정한다. | `RecommendRequest`, `UserPreference`, `RegionScore`, `RecommendResponse` 같은 모델을 Pydantic으로 관리한다. |
| Mock 응답을 실제 API 응답 형태와 동일하게 설계 | 실데이터/실제 LLM으로 교체해도 FE/API 계약이 깨지지 않게 한다. | Mock 추천 결과도 `preferences`, `recommendations`, `summary` 구조로 반환한다. |
| MVP 범위와 Out of Scope 명확화 | 구현 욕심으로 핵심 시나리오가 끝나지 않는 상황을 방지한다. | 오늘은 서울 25개 자치구, 공원/햄버거집 중심 추천만 처리한다. |

## 2. 한 걸음 더 완성도를 높이는 포인트

| 항목 | 판단 | 적용 방안 |
|---|---|---|
| 문서 처리 도구 반영 | 현재 핵심 데이터는 CSV/XLSX 구조화 데이터라 Upstage Document Parse / Information Extract가 필수는 아니다. | 추후 PDF, 비정형 문서, 공공데이터 설명서가 입력으로 들어오면 Document Parse / Information Extract를 별도 Tool로 설계한다. |
| 아키텍처 트레이드오프 한 줄 메모 | 기획서/README 설득력을 높이기 위해 필요하다. | "추천 로직이 원본 데이터 파일에 직접 의존하지 않도록 `processed/region_features.csv`를 표준 중간 테이블로 두었다."라고 명시한다. |
| Mock과 실제 데이터 교체 가능성 | Day2는 Mock이 있어도 되지만 교체 경로가 보여야 한다. | `docs/feature_schema.md`에서 실제값/Mock 여부와 추후 교체 원천 데이터를 명시한다. |
| 핵심 시나리오 테스트 | 말로만 되는 MVP가 아니라 재현 가능한 API 흐름이 필요하다. | 테스트 입력은 "나는 러닝을 좋아하는 20대 남자야. 근처에 공원과 햄버거집이 많은 동네를 추천해줘."로 고정한다. |

## 3. MVP Scope

오늘 MVP에 포함한다.

- 서울 25개 자치구 단위 추천
- 공원/러닝 관련 feature
- 햄버거집/패스트푸드/카페 관련 feature
- `processed/region_features.csv` 표준 스키마
- Pydantic 기반 요청/응답/Tool Schema
- Mock 또는 실제 feature를 같은 응답 shape로 반환

## 4. Out of Scope

오늘 MVP에서 제외한다.

- 행정동 단위 추천
- 좌표 기반 거리 계산
- 지도 히트맵 구현
- 실시간 공공 API 연동
- 실제 LLM/SSE 스트리밍 연동
- 전월세/교통/안전 feature 필수 반영
- Upstage Document Parse / Information Extract 실제 연동

## 5. 오늘 기준 완료 조건

- `docs/data_inventory.md`에서 오늘 사용할 데이터, Mock 대체 데이터, 보류 데이터를 구분한다.
- `docs/feature_schema.md`에서 `processed/region_features.csv` 표준 컬럼을 확정한다.
- 추천 로직은 원본 파일이 아니라 표준 feature table만 참조하도록 설계한다.
- Mock feature는 문서에 Mock임을 명확히 남긴다.
- API 응답 shape는 Mock과 실데이터가 동일하게 유지되도록 한다.

## 6. 아키텍처 트레이드오프 메모

원본 공공데이터 파일을 추천 로직에서 직접 읽으면 전처리 방식, 컬럼명, 파일 형식이 바뀔 때마다 추천 코드가 함께 흔들린다. 따라서 오늘 MVP는 원본 데이터별 전처리를 `data_pipeline` 또는 `adapter` 계층에 두고, 추천 로직은 `processed/region_features.csv`라는 표준 feature table만 참조하도록 설계한다. 이 방식은 초기 구현이 한 단계 늘어나지만, 이후 실제 데이터 교체와 feature 확장이 훨씬 안전하다.
