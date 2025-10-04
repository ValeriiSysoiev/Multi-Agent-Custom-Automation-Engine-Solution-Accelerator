"""Repository helpers for verification evidence."""

from __future__ import annotations

from typing import List

from models.messages_kernel import EvidenceRecord

from .cosmos_repository import CosmosRepository

EVIDENCE_CONTAINER = "evidence"
PARTITION_KEY = "/canonical_id"


class EvidenceRepository(CosmosRepository[EvidenceRecord]):
    def __init__(self) -> None:
        super().__init__(EVIDENCE_CONTAINER, EvidenceRecord, PARTITION_KEY)

    async def list_for_canonical(self, canonical_id: str, limit: int = 50) -> List[EvidenceRecord]:
        return await self.list_partition(canonical_id, limit=limit)

    async def list_for_ticket(self, ticket_id: str) -> List[EvidenceRecord]:
        query = "SELECT * FROM c WHERE c.ticket_id=@ticket"
        return await self.query(query, parameters=[{"name": "@ticket", "value": ticket_id}])

    async def upsert_evidence(self, record: EvidenceRecord) -> EvidenceRecord:
        return await self.upsert(record)
