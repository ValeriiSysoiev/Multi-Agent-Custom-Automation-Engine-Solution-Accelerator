"""Kernel tools exposing verification functionality."""

from __future__ import annotations

import json
from typing import Optional

from semantic_kernel.functions import kernel_function

from models.messages_kernel import AgentType
from services.verification_service import VerificationService
from .generic_tools import GenericTools


class VerificationTools(GenericTools):
    agent_name = AgentType.VERIFICATION.value

    @staticmethod
    @kernel_function(description="Evaluate remediation tickets awaiting verification and return summary metrics.")
    async def run_verification_cycle(limit: int = 50) -> str:
        service = VerificationService()
        try:
            metrics = await service.process_pending_tickets(limit=limit)
        finally:
            await service.close()
        return json.dumps(metrics)


__all__ = ["VerificationTools"]
