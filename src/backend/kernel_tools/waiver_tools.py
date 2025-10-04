"""Kernel tools exposing waiver management operations."""

from __future__ import annotations

import json
from typing import Sequence

from semantic_kernel.functions import kernel_function

from models.messages_kernel import AgentType
from services.waiver_service import WaiverService
from .generic_tools import GenericTools


class WaiverTools(GenericTools):
    agent_name = AgentType.WAIVER.value

    @staticmethod
    @kernel_function(description="Evaluate active waivers and return renewal metrics for escalation.")
    async def monitor_waivers(limit: int = 200, renewal_windows: Sequence[int] | None = None) -> str:
        service = WaiverService()
        try:
            metrics = await service.monitor_waivers(
                renewal_windows=tuple(renewal_windows) if renewal_windows else (7, 3, 1),
                limit=limit,
            )
        finally:
            await service.close()

        return json.dumps(metrics)


__all__ = ["WaiverTools"]
