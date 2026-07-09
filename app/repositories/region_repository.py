import json
from pathlib import Path

from app.core.config import MOCK_REGION_DATA_PATH
from app.schemas.recommendation import RegionFeature


class RegionRepository:
    def __init__(self, data_path: Path = MOCK_REGION_DATA_PATH) -> None:
        self.data_path = data_path

    def list_regions(self) -> list[RegionFeature]:
        with self.data_path.open(encoding="utf-8") as file:
            raw_regions = json.load(file)
        return [RegionFeature.model_validate(region) for region in raw_regions]

