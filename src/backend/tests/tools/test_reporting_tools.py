import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from kernel_tools.reporting_tools import ReportingTools


@pytest.mark.asyncio
async def test_run_reporting_export_invokes_service_and_closes() -> None:
    service_mock = AsyncMock()
    service_mock.export.return_value = {"uploaded_facts": 42}

    with patch("kernel_tools.reporting_tools.ReportingExportService", return_value=service_mock):
        payload = await ReportingTools.run_reporting_export(refresh_powerbi=True)

    body = json.loads(payload)
    assert body["status"] == "completed"
    assert body["metrics"] == {"uploaded_facts": 42}
    service_mock.export.assert_awaited_once_with(refresh_powerbi=True)
    service_mock.close.assert_awaited_once_with()
