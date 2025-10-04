"""Kernel tools exposing deduplication operations to agents."""

from __future__ import annotations

import json
from typing import Optional

from semantic_kernel.functions import kernel_function

from models.messages_kernel import AgentType, CanonicalFinding
from repositories.canonical_finding_repository import CanonicalFindingRepository
from services.dedup_service import DeduplicationService
from .generic_tools import GenericTools


class DeduplicationTools(GenericTools):
    """Tools for the Deduplication Agent."""

    agent_name = AgentType.DEDUPLICATION.value

    @staticmethod
    @kernel_function(description="Re-run deduplication on recent canonical findings and return a summary.")
    async def reconcile_recent_duplicates(limit: int = 200) -> str:
        repo = CanonicalFindingRepository()
        service = DeduplicationService(repository=repo)
        candidates = await repo.list_pending_triage(limit=limit)
        reconciled = 0
        canonical_ids = []
        for finding in candidates:
            merged = await service.merge(finding)
            reconciled += 1
            canonical_ids.append(merged.canonical_id)
        payload = {
            "processed": len(candidates),
            "reconciled": reconciled,
            "canonical_ids": canonical_ids,
        }
        return json.dumps(payload)

    @staticmethod
    @kernel_function(description="Merge a supplied canonical finding payload to ensure duplicates are reconciled.")
    async def merge_candidate(canonical_finding_json: str) -> str:
        repo = CanonicalFindingRepository()
        service = DeduplicationService(repository=repo)
        finding = CanonicalFinding.model_validate_json(canonical_finding_json)
        merged = await service.merge(finding)
        payload = {
            "status": "merged",
            "canonical_id": merged.canonical_id,
            "asset_id": merged.asset_id,
        }
        return json.dumps(payload)


__all__ = ["DeduplicationTools"]
