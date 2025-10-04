import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from models.messages_kernel import AgentType, RunEventRecord
from services.remediation_sla_monitor import RemediationSlaMonitor


class FakeTicketRepository:
    def __init__(self):
        self._counts = {}

    def set_count(self, key: str, value: int) -> None:
        self._counts[key] = value

    async def count_ack_overdue(self, *, now, statuses):
        return self._counts.get("ack_overdue", 0)

    async def count_ack_missing(self, *, statuses):
        return self._counts.get("ack_missing", 0)

    async def count_ack_between(self, *, start, end, statuses):
        window_days = int((end - start).days)
        return self._counts.get(f"ack_within_{window_days}", 0)

    async def count_verify_overdue(self, *, now, statuses):
        return self._counts.get("verify_overdue", 0)

    async def count_verify_missing(self, *, statuses):
        return self._counts.get("verify_missing", 0)

    async def count_verify_between(self, *, start, end, statuses):
        window_days = int((end - start).days)
        return self._counts.get(f"verify_within_{window_days}", 0)


class MemoryRunEventRepository:
    def __init__(self):
        self.events: list[RunEventRecord] = []

    async def upsert_event(self, record: RunEventRecord):
        self.events.append(record)
        return record


@pytest.mark.asyncio
async def test_monitor_records_metrics_and_run_event():
    ticket_repo = FakeTicketRepository()
    ticket_repo.set_count("ack_overdue", 2)
    ticket_repo.set_count("ack_missing", 1)
    ticket_repo.set_count("ack_within_1", 3)
    ticket_repo.set_count("ack_within_3", 5)
    ticket_repo.set_count("verify_overdue", 4)
    ticket_repo.set_count("verify_missing", 2)
    ticket_repo.set_count("verify_within_3", 6)
    ticket_repo.set_count("verify_within_7", 8)

    run_repo = MemoryRunEventRepository()
    monitor = RemediationSlaMonitor(
        ticket_repo=ticket_repo,
        run_repo=run_repo,
        ack_statuses=("open",),
        verify_statuses=("resolved",),
    )

    metrics = await monitor.evaluate(ack_windows=(1, 3), verify_windows=(3, 7))

    assert metrics == {
        "ack_overdue": 2,
        "ack_missing": 1,
        "ack_due_within_1d": 3,
        "ack_due_within_3d": 5,
        "verify_overdue": 4,
        "verify_missing": 2,
        "verify_due_within_3d": 6,
        "verify_due_within_7d": 8,
    }

    assert len(run_repo.events) == 1
    event = run_repo.events[0]
    assert event.agent_name == AgentType.REMEDIATION.value
    assert event.run_type == "remediation_sla_monitor"
    assert event.metrics == metrics
    assert event.status == "completed"


@pytest.mark.asyncio
async def test_monitor_handles_empty_windows():
    ticket_repo = FakeTicketRepository()
    run_repo = MemoryRunEventRepository()
    monitor = RemediationSlaMonitor(ticket_repo=ticket_repo, run_repo=run_repo)

    metrics = await monitor.evaluate(ack_windows=(), verify_windows=())

    assert metrics == {
        "ack_overdue": 0,
        "ack_missing": 0,
        "verify_overdue": 0,
        "verify_missing": 0,
    }

    assert run_repo.events[0].metrics == metrics
