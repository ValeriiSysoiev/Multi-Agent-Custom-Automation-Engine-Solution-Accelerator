"""Monitor acknowledgement and verification SLA deadlines."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional, Sequence
from uuid import uuid4

from models.messages_kernel import AgentType, RunEventRecord
from repositories.run_event_repository import RunEventRepository
from repositories.ticket_repository import TicketRepository

logger = logging.getLogger(__name__)


class RemediationSlaMonitor:
    """Evaluates ticket SLA deadlines and records telemetry."""

    def __init__(
        self,
        ticket_repo: Optional[TicketRepository] = None,
        run_repo: Optional[RunEventRepository] = None,
        *,
        ack_statuses: Iterable[str] = ("open",),
        verify_statuses: Iterable[str] = ("resolved",),
    ) -> None:
        self._ticket_repo = ticket_repo or TicketRepository()
        self._run_repo = run_repo or RunEventRepository()
        self._ack_statuses = tuple(ack_statuses)
        self._verify_statuses = tuple(verify_statuses)

    async def evaluate(
        self,
        *,
        ack_windows: Sequence[int] = (1, 3),
        verify_windows: Sequence[int] = (3, 7),
    ) -> Dict[str, int]:
        now = datetime.now(timezone.utc)
        metrics: Dict[str, int] = {}

        metrics.update(
            await self._evaluate_ack(now=now, windows=ack_windows or ()),
        )
        metrics.update(
            await self._evaluate_verify(now=now, windows=verify_windows or ()),
        )

        correlation_id = str(uuid4())
        record = RunEventRecord(
            id=correlation_id,
            correlation_id=correlation_id,
            agent_name=AgentType.REMEDIATION.value,
            run_type="remediation_sla_monitor",
            status="completed",
            started_at=now,
            completed_at=now,
            metrics=metrics,
        )
        record.timestamp = now
        await self._run_repo.upsert_event(record)

        logger.info(
            "Remediation SLA monitor metrics: %s",
            {key: metrics[key] for key in sorted(metrics)},
        )
        return metrics

    async def _evaluate_ack(self, *, now: datetime, windows: Sequence[int]) -> Dict[str, int]:
        metrics: Dict[str, int] = {}
        ack_statuses = self._ack_statuses or ("open",)

        overdue = await self._ticket_repo.count_ack_overdue(now=now, statuses=ack_statuses)
        metrics["ack_overdue"] = overdue

        missing = await self._ticket_repo.count_ack_missing(statuses=ack_statuses)
        metrics["ack_missing"] = missing

        for window in sorted({int(w) for w in windows if w is not None and w >= 0}):
            horizon = now + timedelta(days=window)
            count = await self._ticket_repo.count_ack_between(
                start=now,
                end=horizon,
                statuses=ack_statuses,
            )
            metrics[f"ack_due_within_{window}d"] = count
        return metrics

    async def _evaluate_verify(self, *, now: datetime, windows: Sequence[int]) -> Dict[str, int]:
        metrics: Dict[str, int] = {}
        verify_statuses = self._verify_statuses or ("resolved",)

        overdue = await self._ticket_repo.count_verify_overdue(now=now, statuses=verify_statuses)
        metrics["verify_overdue"] = overdue

        missing = await self._ticket_repo.count_verify_missing(statuses=verify_statuses)
        metrics["verify_missing"] = missing

        for window in sorted({int(w) for w in windows if w is not None and w >= 0}):
            horizon = now + timedelta(days=window)
            count = await self._ticket_repo.count_verify_between(
                start=now,
                end=horizon,
                statuses=verify_statuses,
            )
            metrics[f"verify_due_within_{window}d"] = count
        return metrics

__all__ = ["RemediationSlaMonitor"]
