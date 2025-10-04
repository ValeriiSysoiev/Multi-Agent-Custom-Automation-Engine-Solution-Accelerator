"""Synchronize risk treatment tasks with Jira ticket status."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence
from uuid import uuid4

from models.messages_kernel import (
    AgentType,
    CanonicalFinding,
    FindingLifecycleStatus,
    RiskTreatmentStatus,
    RiskTreatmentTask,
    RiskTreatmentWorkflow,
    RunEventRecord,
)
from repositories.canonical_finding_repository import CanonicalFindingRepository
from repositories.risk_treatment_repository import RiskTreatmentRepository
from repositories.run_event_repository import RunEventRepository
from services.jira_ticket_client import JiraTicketClient

logger = logging.getLogger(__name__)

DEFAULT_APPROVED_VALUES = {"approved", "completed", "closed"}
DEFAULT_REJECTED_VALUES = {"rejected", "cancelled", "denied"}


class RiskTreatmentSync:
    """Pull Jira status for in-progress risk treatment tasks and update state."""

    def __init__(
        self,
        *,
        risk_repo: Optional[RiskTreatmentRepository] = None,
        canonical_repo: Optional[CanonicalFindingRepository] = None,
        jira_ticket_client: Optional[JiraTicketClient] = None,
        run_repo: Optional[RunEventRepository] = None,
        approved_values: Optional[Iterable[str]] = None,
        rejected_values: Optional[Iterable[str]] = None,
    ) -> None:
        self._risk_repo = risk_repo or RiskTreatmentRepository()
        self._canonical_repo = canonical_repo or CanonicalFindingRepository()
        self._jira = jira_ticket_client or JiraTicketClient()
        self._run_repo = run_repo or RunEventRepository()

        self._waiver_status_field = os.getenv("JIRA_WAIVER_STATUS_FIELD", "customfield_10084")
        self._waiver_expiry_field = os.getenv("JIRA_WAIVER_EXPIRY_FIELD", "customfield_10083")

        self._approved = {
            value.strip().lower()
            for value in (approved_values or DEFAULT_APPROVED_VALUES)
            if value is not None
        }
        self._rejected = {
            value.strip().lower()
            for value in (rejected_values or DEFAULT_REJECTED_VALUES)
            if value is not None
        }

    async def sync(self, *, limit: int = 50) -> Dict[str, int]:
        tasks = await self._risk_repo.list_by_status(RiskTreatmentStatus.IN_PROGRESS, limit=limit)
        if not tasks:
            logger.info("No in-progress risk treatment tasks to synchronize")
            return {}

        metrics: Dict[str, int] = {
            "evaluated": len(tasks),
            "completed": 0,
            "cancelled": 0,
            "failed": 0,
            "no_change": 0,
            "waiver_completed": 0,
            "transfer_completed": 0,
            "waiver_cancelled": 0,
            "transfer_cancelled": 0,
        }

        for task in tasks:
            try:
                await self._sync_task(task, metrics)
            except Exception:  # pragma: no cover - defensive logging
                metrics["failed"] += 1
                logger.exception("Failed to sync risk treatment task %s", task.task_id)

        correlation_id = str(uuid4())
        now = datetime.now(timezone.utc)
        record = RunEventRecord(
            id=correlation_id,
            correlation_id=correlation_id,
            agent_name=AgentType.WAIVER.value,
            run_type="risk_treatment_sync",
            status="completed",
            started_at=now,
            completed_at=now,
            metrics=metrics,
        )
        record.timestamp = now
        await self._run_repo.upsert_event(record)
        logger.info("Risk treatment sync metrics: %s", metrics)
        return metrics

    async def _sync_task(self, task: RiskTreatmentTask, metrics: Dict[str, int]) -> None:
        if not task.ticket_key:
            logger.warning("Skipping task %s without ticket key", task.task_id)
            metrics["no_change"] += 1
            return

        try:
            issue = await self._jira.get_issue_fields(
                task.ticket_key,
                fields=[
                    "status",
                    self._waiver_status_field,
                    self._waiver_expiry_field,
                ],
            )
        except Exception as exc:
            metrics["failed"] += 1
            task.last_error = f"Jira fetch failed: {exc}"
            task.last_synced_at = datetime.now(timezone.utc)
            await self._risk_repo.upsert_task(task)
            logger.warning("Failed to fetch Jira issue %s: %s", task.ticket_key, exc)
            return

        fields = issue.get("fields", {}) if isinstance(issue, dict) else {}
        status_field = fields.get("status")
        status_name = None
        if isinstance(status_field, dict):
            status_name = status_field.get("name")
        waiver_status = fields.get(self._waiver_status_field)
        waiver_value = None
        if isinstance(waiver_status, dict):
            waiver_value = waiver_status.get("value")
        elif isinstance(waiver_status, str):
            waiver_value = waiver_status

        normalized = (waiver_value or status_name or "").strip().lower()
        now = datetime.now(timezone.utc)

        if normalized in self._approved:
            await self._complete_task(task, fields, now, metrics)
            metrics["completed"] += 1
        elif normalized in self._rejected:
            await self._cancel_task(task, fields, now, metrics)
            metrics["cancelled"] += 1
        else:
            task.ticket_status = status_name
            task.last_error = None
            task.last_synced_at = now
            await self._risk_repo.upsert_task(task)
            metrics["no_change"] += 1

    async def _complete_task(
        self,
        task: RiskTreatmentTask,
        fields: Dict[str, object],
        now: datetime,
        metrics: Dict[str, int],
    ) -> None:
        canonical = await self._canonical_repo.get_by_id(task.canonical_id, task.asset_id)
        if not canonical:
            logger.warning("Canonical finding missing for task %s", task.task_id)
            return

        expiry_value = fields.get(self._waiver_expiry_field)
        if isinstance(expiry_value, str):
            try:
                task.proposed_expiry = datetime.fromisoformat(expiry_value)
            except ValueError:
                pass

        task.status = RiskTreatmentStatus.COMPLETED
        task.ticket_status = fields.get("status", {}).get("name") if isinstance(fields.get("status"), dict) else None
        task.last_error = None
        task.last_synced_at = now
        task.timestamp = now
        await self._risk_repo.upsert_task(task)

        workflow_key = (
            task.workflow.value
            if isinstance(task.workflow, RiskTreatmentWorkflow)
            else str(task.workflow)
        ).replace("risk_", "")
        metrics_key = f"{workflow_key}_completed"
        if metrics_key in metrics:
            metrics[metrics_key] += 1
        else:
            metrics[metrics_key] = 1

        canonical.treatment_follow_up_id = None
        canonical.status = FindingLifecycleStatus.WAIVED
        canonical.timestamp = now
        await self._canonical_repo.upsert_finding(canonical)

    async def _cancel_task(
        self,
        task: RiskTreatmentTask,
        fields: Dict[str, object],
        now: datetime,
        metrics: Dict[str, int],
    ) -> None:
        canonical = await self._canonical_repo.get_by_id(task.canonical_id, task.asset_id)
        if not canonical:
            logger.warning("Canonical finding missing for task %s", task.task_id)
            return

        task.status = RiskTreatmentStatus.CANCELLED
        task.ticket_status = fields.get("status", {}).get("name") if isinstance(fields.get("status"), dict) else None
        task.last_error = None
        task.last_synced_at = now
        task.timestamp = now
        await self._risk_repo.upsert_task(task)

        workflow_key = (
            task.workflow.value
            if isinstance(task.workflow, RiskTreatmentWorkflow)
            else str(task.workflow)
        ).replace("risk_", "")
        metrics_key = f"{workflow_key}_cancelled"
        if metrics_key in metrics:
            metrics[metrics_key] += 1
        else:
            metrics[metrics_key] = 1

        canonical.treatment_follow_up_id = None
        canonical.status = FindingLifecycleStatus.TRIAGED
        canonical.timestamp = now
        await self._canonical_repo.upsert_finding(canonical)

    async def close(self) -> None:
        await self._jira.close()


__all__ = ["RiskTreatmentSync"]
