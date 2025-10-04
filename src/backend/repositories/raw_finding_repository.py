"""Repository for raw scanner findings."""

from __future__ import annotations

from typing import Optional

from models.messages_kernel import RawFinding

from .cosmos_repository import CosmosRepository

RAW_FINDINGS_CONTAINER = "findings_raw"
PARTITION_KEY = "/scanner_id"


class RawFindingRepository(CosmosRepository[RawFinding]):
    def __init__(self) -> None:
        super().__init__(RAW_FINDINGS_CONTAINER, RawFinding, PARTITION_KEY)

    async def upsert_finding(self, finding: RawFinding) -> RawFinding:
        return await self.upsert(finding)

    async def get_finding(self, finding_id: str, scanner_id: str) -> Optional[RawFinding]:
        return await self.read(finding_id, scanner_id)
