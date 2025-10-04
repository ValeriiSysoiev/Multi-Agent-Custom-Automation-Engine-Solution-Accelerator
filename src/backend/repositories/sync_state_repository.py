"""Repository for scanner sync state tracking."""

from __future__ import annotations

from typing import Optional

from models.messages_kernel import SyncStateRecord

from .cosmos_repository import CosmosRepository

SYNC_STATE_CONTAINER = "sync_state"
PARTITION_KEY = "/scanner_id"


class SyncStateRepository(CosmosRepository[SyncStateRecord]):
    def __init__(self) -> None:
        super().__init__(SYNC_STATE_CONTAINER, SyncStateRecord, PARTITION_KEY)

    async def get_state(self, scanner_id: str) -> Optional[SyncStateRecord]:
        return await self.read(scanner_id, scanner_id)

    async def upsert_state(self, record: SyncStateRecord) -> SyncStateRecord:
        return await self.upsert(record)
