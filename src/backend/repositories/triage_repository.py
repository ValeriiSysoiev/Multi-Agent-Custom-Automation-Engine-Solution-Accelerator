"""Repository helpers for triage records."""

from __future__ import annotations

from typing import List, Optional

from models.messages_kernel import TriageRecord

from .cosmos_repository import CosmosRepository

TRIAGE_CONTAINER = "triage_items"
PARTITION_KEY = "/canonical_id"


class TriageRepository(CosmosRepository[TriageRecord]):
    """Persistence helpers for triage records."""

    def __init__(self) -> None:
        super().__init__(TRIAGE_CONTAINER, TriageRecord, PARTITION_KEY)

    async def upsert_record(self, record: TriageRecord) -> TriageRecord:
        return await self.upsert(record)

    async def list_for_canonical(self, canonical_id: str, limit: int = 50) -> List[TriageRecord]:
        return await self.list_partition(canonical_id, limit=limit)

    async def get_latest(self, canonical_id: str) -> Optional[TriageRecord]:
        query = (
            "SELECT TOP 1 * FROM c WHERE c.canonical_id=@cid ORDER BY c.timestamp DESC"
        )
        results = await self.query(query, parameters=[{"name": "@cid", "value": canonical_id}])
        return results[0] if results else None
