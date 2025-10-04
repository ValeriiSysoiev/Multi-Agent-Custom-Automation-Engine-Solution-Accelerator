"""Repository for remediation unit records."""

from __future__ import annotations

from typing import Iterable, List, Optional

from models.messages_kernel import RemediationUnitRecord

from .cosmos_repository import CosmosRepository

REMEDIATION_CONTAINER = "remediation_units"
PARTITION_KEY = "/remediation_unit_id"


class RemediationUnitRepository(CosmosRepository[RemediationUnitRecord]):
    def __init__(self) -> None:
        super().__init__(REMEDIATION_CONTAINER, RemediationUnitRecord, PARTITION_KEY)

    async def upsert_unit(self, record: RemediationUnitRecord) -> RemediationUnitRecord:
        return await self.upsert(record)

    async def get_unit(self, remediation_unit_id: str) -> Optional[RemediationUnitRecord]:
        return await self.read(remediation_unit_id, remediation_unit_id)

    async def list_units(self, limit: int = 100) -> List[RemediationUnitRecord]:
        query = "SELECT * FROM c ORDER BY c.timestamp DESC"
        results = await self.query(query)
        return results[:limit]

    async def get_units(self, remediation_unit_ids: Iterable[str]) -> List[RemediationUnitRecord]:
        records: List[RemediationUnitRecord] = []
        for remediation_unit_id in remediation_unit_ids:
            unit = await self.get_unit(remediation_unit_id)
            if unit is not None:
                records.append(unit)
        return records
