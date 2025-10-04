"""Kernel tools exposing triage functionality to agents."""

from __future__ import annotations

import json
from typing import Optional

from semantic_kernel.functions import kernel_function

from models.messages_kernel import AgentType
from repositories.canonical_finding_repository import CanonicalFindingRepository
from services.triage_service import TriageService
from .generic_tools import GenericTools


class TriageTools(GenericTools):
    agent_name = AgentType.TRIAGE.value

    @staticmethod
    @kernel_function(description="Run triage for open findings and return a JSON summary of results.")
    async def triage_open_findings(limit: int = 20) -> str:
        service = TriageService()
        try:
            records = await service.triage_findings(limit=limit)
        finally:
            await service.close()

        summary = {
            "triaged_count": len(records),
            "triage_ids": [record.triage_id for record in records],
        }
        return json.dumps(summary)

    @staticmethod
    @kernel_function(description="Triage a specific canonical finding using its canonical and asset identifiers.")
    async def triage_canonical_finding(canonical_id: str, asset_id: str) -> str:
        repository = CanonicalFindingRepository()
        finding = await repository.get_by_id(canonical_id, asset_id)
        if not finding:
            return json.dumps({"status": "not_found", "canonical_id": canonical_id})

        service = TriageService()
        try:
            record = await service.triage_single(finding)
        finally:
            await service.close()

        if not record:
            return json.dumps({"status": "skipped", "canonical_id": canonical_id})

        payload = {
            "status": "triaged",
            "triage_id": record.triage_id,
            "risk_tier": record.risk_tier.value,
            "risk_score": record.risk_score,
            "treatment": record.treatment.value,
        }
        return json.dumps(payload)


__all__ = ["TriageTools"]
