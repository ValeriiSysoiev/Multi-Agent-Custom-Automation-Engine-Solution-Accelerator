"""Repository for enrichment records."""

from __future__ import annotations

from typing import Optional

from models.messages_kernel import EnrichmentRecord

from .cosmos_repository import CosmosRepository

ENRICHMENT_CONTAINER = "enrichments"
PARTITION_KEY = "/asset_id"


class EnrichmentRepository(CosmosRepository[EnrichmentRecord]):
    """Data access layer for enrichment records in Cosmos DB."""

    def __init__(self) -> None:
        super().__init__(ENRICHMENT_CONTAINER, EnrichmentRecord, PARTITION_KEY)

    async def upsert_enrichment(self, record: EnrichmentRecord) -> EnrichmentRecord:
        if not record.id:
            record.id = record.canonical_id
        return await self.upsert(record)

    async def get_enrichment(self, canonical_id: str, asset_id: str) -> Optional[EnrichmentRecord]:
        return await self.read(canonical_id, asset_id)
