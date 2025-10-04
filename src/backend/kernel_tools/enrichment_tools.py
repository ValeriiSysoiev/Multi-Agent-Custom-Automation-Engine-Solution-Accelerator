"""Kernel tools exposing enrichment operations to agents."""

from __future__ import annotations

import json

from semantic_kernel.functions import kernel_function

from models.messages_kernel import AgentType
from repositories.canonical_finding_repository import CanonicalFindingRepository
from services.enrichment_service import EnrichmentService
from .generic_tools import GenericTools


class EnrichmentTools(GenericTools):
    """Tools for the Enrichment Agent."""

    agent_name = AgentType.ENRICHMENT.value

    @staticmethod
    @kernel_function(description="Run enrichment for pending canonical findings and return a summary.")
    async def enrich_pending_findings(limit: int = 100) -> str:
        repo = CanonicalFindingRepository()
        service = EnrichmentService()
        try:
            candidates = await repo.list_pending_triage(limit=limit)
            enriched = await service.enrich_findings(candidates)
        finally:
            await service.close()

        summary = {
            "processed": len(candidates),
            "enriched": len(enriched),
            "canonical_ids": [record.canonical_id for record in enriched],
        }
        return json.dumps(summary)


__all__ = ["EnrichmentTools"]
