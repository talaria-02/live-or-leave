"""도구 실행기 — 행정동 단위. 서비스 계층에 위임."""
from __future__ import annotations

from app.data.csv_repository import CsvDongRepository
from app.data.facility_repository import get_facility_repository
from app.schemas.tools import CompareTool, RecommendTool
from app.services import scoring


class ToolExecutor:
    def __init__(self, repo: CsvDongRepository):
        self.repo = repo

    def recommend(self, args: RecommendTool) -> dict:
        raws = self.repo.all_metrics()
        scores = scoring.score_dongs(raws)

        extra_counts: dict[str, dict[str, int]] = {}
        if args.extra_categories:
            facility_repo = get_facility_repository()
            for cat in args.extra_categories:
                extra_counts[cat] = {
                    r.code: facility_repo.count(r.gu, r.dong, cat) for r in raws
                }
        extra_scores = scoring.score_extra_categories(raws, extra_counts)

        weights = scoring.preference_to_weights(args.preference, args.extra_categories)
        recs = scoring.rank(scores, weights, top_n=args.top_n,
                            require_large_hospital=args.require_large_hospital,
                            extra_scores=extra_scores)

        rec_dicts = [r.model_dump() for r in recs]
        if extra_counts:
            for rec_dict, rec in zip(rec_dicts, recs):
                rec_dict["extra_facilities"] = {
                    cat: extra_counts[cat].get(rec.scores.code, 0) for cat in extra_counts
                }
        return {"weights": weights, "recommendations": rec_dicts}

    def compare(self, args: CompareTool) -> dict:
        a, b = self.repo.get(args.gu_a), self.repo.get(args.gu_b)
        if not a or not b:
            return {"error": "존재하지 않는 행정동"}
        return {"a": a.model_dump(), "b": b.model_dump()}
