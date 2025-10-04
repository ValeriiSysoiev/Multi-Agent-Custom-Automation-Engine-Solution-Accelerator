"""Waiver workflow service for remediation exceptions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence
from uuid import uuid4

from models.messages_kernel import (
    AgentType,
    CompensatingControl,
    RemediationUnitRecord,
    ResidualRisk,
    RiskTier,
    RunEventRecord,
    WaiverApproval,
    WaiverRecord,
    WaiverStatus,
)
from repositories.remediation_unit_repository import RemediationUnitRepository
from repositories.run_event_repository import RunEventRepository
from repositories.waiver_repository import WaiverRepository
from services.jira_ticket_client import JiraTicketClient
from services.waiver_policy import WaiverPolicy

logger = logging.getLogger(__name__)


class WaiverService:
    """Handles waiver requests, approvals, and expiry management."""

    def __init__(
        self,
        waiver_repo: Optional[WaiverRepository] = None,
        remediation_repo: Optional[RemediationUnitRepository] = None,
        run_repo: Optional[RunEventRepository] = None,
        jira_client: Optional[JiraTicketClient] = None,
        policy: Optional[WaiverPolicy] = None,
    ) -> None:
        self._waiver_repo = waiver_repo or WaiverRepository()
        self._remediation_repo = remediation_repo or RemediationUnitRepository()
        self._run_repo = run_repo or RunEventRepository()
        self._jira = jira_client or JiraTicketClient()
        self._policy = policy or WaiverPolicy()

    async def close(self) -> None:
        await self._jira.close()

    async def request_waiver(
        self,
        remediation_unit: RemediationUnitRecord,
        requested_by: str,
        justification: str,
        controls: Iterable[CompensatingControl],
        residual_risk: ResidualRisk,
        expiry: datetime,
        verification_plan: Optional[str] = None,
    ) -> WaiverRecord:
        now = datetime.now(timezone.utc)
        waiver_id = f"wa-{uuid4()}"

        summary = f"Waiver for {remediation_unit.remediation_unit_id}"
        description = justification

        valid, message = self._policy.validate_controls(remediation_unit.risk_tier, controls)
        if not valid:
            raise ValueError(message or "Compensating controls do not satisfy policy requirements")

        jira_ticket = await self._jira.create_waiver_ticket(
            summary=summary,
            description=description,
            expiry=expiry,
            status="Requested",
        )

        record = WaiverRecord(
            id=waiver_id,
            waiver_id=waiver_id,
            remediation_unit_id=remediation_unit.remediation_unit_id,
            risk_tier=remediation_unit.risk_tier,
            status=WaiverStatus.REQUESTED,
            requested_by=requested_by,
            requested_at=now,
            justification=justification,
            compensating_controls=list(controls),
            residual_risk=residual_risk,
            ticket_id=jira_ticket.issue_id,
            ticket_key=jira_ticket.issue_key,
            ticket_url=jira_ticket.browse_url,
            approvals=[],
            approved_by=[],
            approved_at=None,
            expires_at=expiry,
            renewal_count=0,
            verification_plan=verification_plan,
        )
        record.timestamp = now
        await self._waiver_repo.upsert_waiver(record)
        return record

    async def approve_waiver(
        self,
        waiver_id: str,
        approver: str,
        role: str,
        notes: Optional[str] = None,
    ) -> WaiverRecord:
        waiver = await self._waiver_repo.get_by_id(waiver_id)
        if waiver is None:
            raise ValueError(f"Waiver {waiver_id} not found")

        role_valid, role_message = self._policy.validate_role(waiver.risk_tier, role)
        if not role_valid:
            raise ValueError(role_message or f"Role {role} not permitted for approval")

        now = datetime.now(timezone.utc)
        approvals = list(waiver.approvals or [])
        normalized_role = role.strip().lower()
        # Replace existing approval for the same role to avoid duplicates
        approvals = [approval for approval in approvals if approval.role != normalized_role]
        approvals.append(
            WaiverApproval(approver=approver, role=normalized_role, approved_at=now)
        )

        waiver.approvals = approvals
        waiver.approved_by = [approval.approver for approval in approvals]
        waiver.timestamp = now
        if notes:
            waiver.verification_plan = notes

        if self._policy.is_fully_approved(waiver.risk_tier, [approval.role for approval in approvals]):
            waiver.status = WaiverStatus.APPROVED
            waiver.approved_at = now
            await self._waiver_repo.upsert_waiver(waiver)
            await self._safe_update_waiver_status(waiver, "Approved")
        else:
            waiver.status = WaiverStatus.REQUESTED
            waiver.approved_at = None
            await self._waiver_repo.upsert_waiver(waiver)
        return waiver

    async def expire_waivers(self, limit: int = 200) -> int:
        now = datetime.now(timezone.utc)
        waivers = await self._waiver_repo.list_active(limit=limit)
        expired = 0
        for waiver in waivers:
            if waiver.expires_at and waiver.expires_at < now and waiver.status != WaiverStatus.EXPIRED:
                waiver.status = WaiverStatus.EXPIRED
                waiver.timestamp = now
                await self._waiver_repo.upsert_waiver(waiver)
                await self._safe_update_waiver_status(waiver, "Expired")
                expired += 1
        if expired:
            await self._run_repo.upsert_event(
                RunEventRecord(
                    id=str(uuid4()),
                    correlation_id=str(uuid4()),
                    agent_name=AgentType.REMEDIATION.value,
                    run_type="waiver_expiry",
                    status="completed",
                    started_at=now,
                    completed_at=now,
                    metrics={"expired": expired},
                )
            )
        return expired

    async def monitor_waivers(
        self,
        *,
        renewal_windows: Sequence[int] = (7, 3, 1),
        limit: int = 500,
    ) -> Dict[str, int]:
        """Assess waiver renewals and pending approvals, recording telemetry.

        Args:
            renewal_windows: Sorted (largest → smallest) days-before-expiry thresholds that
                should trigger escalation metrics.
            limit: Maximum number of active waivers to evaluate.

        Returns:
            Dictionary of metrics captured for telemetry/alerting.
        """

        now = datetime.now(timezone.utc)
        waivers = await self._waiver_repo.list_active(limit=limit)

        # Normalise thresholds and ensure descending order for predictable metrics.
        unique_windows = sorted({int(window) for window in renewal_windows if window >= 0}, reverse=True)

        metrics: Dict[str, int] = {
            "total_active": len(waivers),
            "missing_expiry": 0,
            "overdue": 0,
            "pending_decision": 0,
        }
        for window in unique_windows:
            metrics[f"due_within_{window}d"] = 0

        escalation_samples: List[Dict[str, object]] = []

        for waiver in waivers:
            if waiver.status == WaiverStatus.REQUESTED:
                metrics["pending_decision"] += 1
                pending_roles = self._policy.pending_roles(
                    waiver.risk_tier,
                    [approval.role for approval in waiver.approvals or []],
                )
            else:
                pending_roles = []

            if not waiver.expires_at:
                metrics["missing_expiry"] += 1
                if pending_roles:
                    escalation_samples.append(
                        {
                            "waiver_id": waiver.waiver_id,
                            "remediation_unit_id": waiver.remediation_unit_id,
                            "pending_roles": pending_roles,
                            "issue": "missing_expiry",
                        }
                    )
                continue

            delta = waiver.expires_at - now
            days_to_expiry = delta.total_seconds() / 86400

            if days_to_expiry < 0:
                metrics["overdue"] += 1
                escalation_samples.append(
                    {
                        "waiver_id": waiver.waiver_id,
                        "remediation_unit_id": waiver.remediation_unit_id,
                        "days_to_expiry": days_to_expiry,
                        "pending_roles": pending_roles,
                        "issue": "expired_pending_cleanup",
                    }
                )
                continue

            for window in unique_windows:
                if days_to_expiry <= window:
                    metrics[f"due_within_{window}d"] += 1

            escalate_due = bool(unique_windows) and days_to_expiry <= unique_windows[-1]
            if pending_roles or escalate_due:
                escalation_samples.append(
                    {
                        "waiver_id": waiver.waiver_id,
                        "remediation_unit_id": waiver.remediation_unit_id,
                        "days_to_expiry": days_to_expiry,
                        "pending_roles": pending_roles,
                    }
                )

        event_metrics: Dict[str, object] = {**metrics}
        if unique_windows:
            event_metrics["renewal_windows"] = list(unique_windows)
        if escalation_samples:
            # Keep payload bounded to avoid oversized run events.
            event_metrics["escalations"] = escalation_samples[:20]

        await self._run_repo.upsert_event(
            RunEventRecord(
                id=str(uuid4()),
                correlation_id=str(uuid4()),
                agent_name=AgentType.REMEDIATION.value,
                run_type="waiver_monitor",
                status="completed",
                started_at=now,
                completed_at=now,
                metrics=event_metrics,
            )
        )

        # The caller expects only numeric metrics back for quick checks; remove complex entries.
        return metrics

    async def _safe_update_waiver_status(self, waiver: WaiverRecord, status: str) -> None:
        if not waiver.ticket_key:
            return
        try:
            await self._jira.set_waiver_status(waiver.ticket_key, status, expiry=waiver.expires_at)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Failed to update waiver ticket %s status to %s: %s",
                waiver.ticket_key,
                status,
                exc,
            )


__all__ = ["WaiverService"]
