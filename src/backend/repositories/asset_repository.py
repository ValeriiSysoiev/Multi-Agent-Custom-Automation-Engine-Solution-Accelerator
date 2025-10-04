"""Repository for asset records."""

from __future__ import annotations

from typing import Iterable, List, Optional

from models.messages_kernel import AssetRecord

from .cosmos_repository import CosmosRepository

ASSET_CONTAINER = "assets"
PARTITION_KEY = "/asset_id"


class AssetRepository(CosmosRepository[AssetRecord]):
    """Data access for asset inventory records."""

    def __init__(self) -> None:
        super().__init__(ASSET_CONTAINER, AssetRecord, PARTITION_KEY)

    async def upsert_asset(self, record: AssetRecord) -> AssetRecord:
        if not record.id:
            record.id = record.asset_id
        return await self.upsert(record)

    async def get_asset(self, asset_id: str) -> Optional[AssetRecord]:
        return await self.read(asset_id, asset_id)

    async def get_assets(self, asset_ids: Iterable[str]) -> List[AssetRecord]:
        records: List[AssetRecord] = []
        for asset_id in asset_ids:
            asset = await self.get_asset(asset_id)
            if asset is not None:
                records.append(asset)
        return records
