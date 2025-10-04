"""Kernel tools exposing reporting export operations."""

from __future__ import annotations

import json
from datetime import datetime

from semantic_kernel.functions import kernel_function

from models.messages_kernel import AgentType
from services.reporting_export_service import ReportingExportService
from .generic_tools import GenericTools


class ReportingTools(GenericTools):
    agent_name = AgentType.REPORTING.value

    @staticmethod
    @kernel_function(description="Run the reporting export pipeline and return dataset metrics.")
    async def run_reporting_export(refresh_powerbi: bool = False) -> str:
        service = ReportingExportService()
        try:
            metrics = await service.export(refresh_powerbi=refresh_powerbi)
        finally:
            await service.close()
        payload = {
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metrics": metrics,
        }
        return json.dumps(payload)


__all__ = ["ReportingTools"]
