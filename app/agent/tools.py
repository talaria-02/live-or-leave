"""도구 실행기 — 행정동 단위. 서비스 계층에 위임."""
from __future__ import annotations

from app.data.csv_repository import CsvDongRepository
from app.data.kakao_facility_repository import get_hybrid_facility_repository
from app.schemas.tools import CompareTool, RecommendTool
from app.services import scoring

# '근처'의 반경 기준 (동 중심점 기준).
NEAR_RADIUS_KM = 3.0


class ToolExecutor:
    def __init__(self, repo: CsvDongRepository):
        self.repo = repo

    def recommend(self, args: RecommendTool) -> dict:
        raws = self.repo.all_metrics()
        scores = scoring.score_dongs(raws)

        # CSV 우선, CSV에 없는 열린 키워드(예: "클라이밍장")만 Kakao 좌표검색 폴백.
        facility_repo = (
            get_hybrid_facility_repository()
            if args.extra_categories or args.required_categories or args.required_near
            else None
        )

        extra_counts: dict[str, dict[str, int]] = {
            cat: {r.code: facility_repo.count(r.gu, r.dong, cat) for r in raws}
            for cat in args.extra_categories
        }
        extra_scores = scoring.score_extra_categories(raws, extra_counts)

        # 해석 불가한 필수 업종(CSV에 없고 API 키도 없음)은 필터에서 제외하고
        # 결과에 표시한다 — 카운트 전부 0으로 두면 전 지역이 조용히 실격되기 때문.
        resolvable_required = [c for c in args.required_categories
                               if facility_repo.resolvable(c)]
        unresolved_required = [c for c in args.required_categories
                               if c not in resolvable_required]

        required_counts: dict[str, dict[str, int]] = {
            cat: {r.code: facility_repo.count(r.gu, r.dong, cat) for r in raws}
            for cat in resolvable_required
        }
        pool, disqualified = (
            scoring.partition_by_required_categories(scores, required_counts)
            if required_counts else (scores, [])
        )

        # '~근처' 거리 필수조건: 랜드마크 좌표 1개를 찾아 동 중심점과의 거리로
        # 필터한다. 업종 존재 필터와 달리 이름 매칭 노이즈(예: '서울대' 상호
        # 890곳)가 없다. 좌표를 못 찾거나 API 키가 없으면 해석 불가로 보고.
        landmarks: dict[str, tuple[float, float]] = {}
        for name in args.required_near:
            coord = (facility_repo.locate_place(name)
                     if facility_repo.near_resolvable() else None)
            if coord:
                landmarks[name] = coord
            else:
                unresolved_required.append(f"{name} 근처")
        if landmarks:
            pool, near_disqualified = scoring.partition_by_proximity(
                pool, landmarks, facility_repo.dong_centroids(), NEAR_RADIUS_KM)
            disqualified.extend(near_disqualified)

        # 대형병원 필수도 같은 실격 메커니즘으로 처리한다 — rank() 내부 필터로
        # 조용히 떨어뜨리면 그 동들이 recommendations에도 disqualified에도 없어
        # 지도에서 통째로 사라진다. 전부 미달이면 기존 rank() 폴백과 동일하게
        # 필터를 생략한다.
        if args.require_large_hospital:
            with_hosp = [s for s in pool if s.raw.hosp_cnt >= 1]
            if with_hosp:
                disqualified.extend(
                    {"scores": s, "missing": ["대형병원"]}
                    for s in pool if s.raw.hosp_cnt < 1
                )
                pool = with_hosp

        weights = scoring.preference_to_weights(args.preference, args.extra_categories)
        recs = scoring.rank(pool, weights, top_n=args.top_n,
                            extra_scores=extra_scores)

        rec_dicts = [r.model_dump() for r in recs]
        if extra_counts:
            for rec_dict, rec in zip(rec_dicts, recs):
                rec_dict["extra_facilities"] = {
                    cat: extra_counts[cat].get(rec.scores.code, 0) for cat in extra_counts
                }

        result = {"weights": weights, "recommendations": rec_dicts}

        # 지도 핀용 좌표 — 개발자/사용자가 필터 근거를 눈으로 검증할 수 있게.
        # 랜드마크(근처 기준점) + Kakao로 해석된 필수 업종의 실제 위치.
        # CSV 출처 업종은 좌표가 없어 핀 없음.
        map_points = [
            {"label": name, "lon": lon, "lat": lat, "kind": "landmark"}
            for name, (lon, lat) in landmarks.items()
        ]
        for cat in resolvable_required:
            places = facility_repo.places_for(cat)
            if places:
                map_points.extend(
                    {"label": f"{cat}: {name}", "lon": lon, "lat": lat, "kind": "facility"}
                    for name, lon, lat in places
                )
        if map_points:
            result["map_points"] = map_points

        if unresolved_required:
            result["unresolved_requirements"] = unresolved_required
        if disqualified:
            result["disqualified"] = [
                {"code": d["scores"].code, "gu": d["scores"].gu,
                 "dong": d["scores"].dong, "missing": d["missing"]}
                for d in disqualified
            ]
        return result

    def compare(self, args: CompareTool) -> dict:
        a, b = self.repo.get(args.gu_a), self.repo.get(args.gu_b)
        if not a or not b:
            return {"error": "존재하지 않는 행정동"}
        return {"a": a.model_dump(), "b": b.model_dump()}
