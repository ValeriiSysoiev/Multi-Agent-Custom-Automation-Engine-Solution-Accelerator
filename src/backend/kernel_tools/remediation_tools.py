"""Kernel tools exposing remediation functionality."""

from __future__ import annotations

import json
from typing import Optional

from semantic_kernel.functions import kernel_function

from models.messages_kernel import AgentType
from services.remediation_service import RemediationService
from .generic_tools import GenericTools


class RemediationTools(GenericTools):
    agent_name = AgentType.REMEDIATION.value

    @staticmethod
    @kernel_function(description="Create remediation units and Jira tickets for triaged findings.")
    async def run_remediation_cycle(limit: int = 50) -> str:
        service = RemediationService()
        try:
            result = await service.plan_and_create(limit=limit)
        finally:
            await service.close()

        summary = {
            "units_created": result.unit_count,
            "tickets_created": result.ticket_count,
            "skipped": result.skipped,
        }
        return json.dumps(summary)


__all__ = ["RemediationTools"]
