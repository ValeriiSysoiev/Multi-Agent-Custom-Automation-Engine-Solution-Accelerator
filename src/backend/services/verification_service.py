"""Service that evaluates remediation evidence and transitions tickets."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

from models.messages_kernel import (
    AgentType,
    CanonicalFinding,
    EvidenceRecord,
    EvidenceType,
    FindingLifecycleStatus,
    RemediationUnitRecord,
    RiskTier,
    RunEventRecord,
    TicketRecord,
    TicketStatus,
    VerificationStatus,
    RemediationBucket,
)
from repositories.canonical_finding_repository import CanonicalFindingRepository
from repositories.evidence_repository import EvidenceRepository
from repositories.remediation_unit_repository import RemediationUnitRepository
from repositories.run_event_repository import RunEventRepository
from repositories.ticket_repository import TicketRepository
from services.jira_ticket_client import JiraTicketClient
from services.verification_policy import VerificationPolicy

logger = logging.getLogger(__name__)


class VerificationService:
    """Evaluates evidence to verify remediation tickets."""

    def __init__(
        self,
        ticket_repo: Optional[TicketRepository] = None,
        evidence_repo: Optional[EvidenceRepository] = None,
        remediation_repo: Optional[RemediationUnitRepository] = None,
        canonical_repo: Optional[CanonicalFindingRepository] = None,
        run_repo: Optional[RunEventRepository] = None,
        policy: Optional[VerificationPolicy] = None,
        jira_client: Optional[JiraTicketClient] = None,
    ) -> None:
        self._ticket_repo = ticket_repo or TicketRepository()
        self._evidence_repo = evidence_repo or EvidenceRepository()
        self._remediation_repo = remediation_repo or RemediationUnitRepository()
        self._canonical_repo = canonical_repo or CanonicalFindingRepository()
        self._run_repo = run_repo or RunEventRepository()
        self._policy = policy or VerificationPolicy()
        self._jira = jira_client or JiraTicketClient()

    async def close(self) -> None:
        await self._jira.close()

    async def process_pending_tickets(self, limit: int = 50) -> Dict[str, int]:
        tickets = await self._ticket_repo.list_pending_verification(limit=limit)
        if not tickets:
            logger.info("No tickets pending verification")
            return {"processed": 0, "verified": 0, "reopened": 0}

        correlation_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        metrics = {"processed": 0, "verified": 0, "reopened": 0}

        await self._run_repo.upsert_event(
            self._build_run_event(
                correlation_id=correlation_id,
                status="started",
                started_at=started_at,
                metrics=metrics,
            )
        )

        for ticket in tickets:
            metrics["processed"] += 1
            try:
                verified = await self._evaluate_ticket(ticket)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Verification failed for ticket %s", ticket.ticket_id)
                continue
            if verified:
                metrics["verified"] += 1
            else:
                metrics["reopened"] += 1

        completed_at = datetime.now(timezone.utc)
        await self._run_repo.upsert_event(
            self._build_run_event(
                correlation_id=correlation_id,
                status="completed",
                started_at=started_at,
                completed_at=completed_at,
                metrics=metrics,
            )
        )
        return metrics

    async def _evaluate_ticket(self, ticket: TicketRecord) -> bool:
        evidence = await self._evidence_repo.list_for_ticket(ticket.ticket_id)
        unit = await self._remediation_repo.get_unit(ticket.remediation_unit_id)
        if unit is None:
            logger.warning("Missing remediation unit for ticket %s", ticket.ticket_id)
            return False

        # Determine risk tier/bucket
        risk_tier = unit.risk_tier if isinstance(unit.risk_tier, RiskTier) else RiskTier(unit.risk_tier)
        bucket = self._ensure_bucket_enum(unit.bucket)
        evidence_types: List[EvidenceType] = []
        for record in evidence:
            etype = record.evidence_type
            if not isinstance(etype, EvidenceType):
                try:
                    etype = EvidenceType(etype)
                except ValueError:
                    logger.debug("Unknown evidence type %s for ticket %s", etype, ticket.ticket_id)
                    continue
            evidence_types.append(etype)

        policy_entry = self._policy.get_policy(risk_tier, bucket)
        satisfied = self._policy.is_satisfied(policy_entry, evidence_types)
        within_window = self._within_window(policy_entry, ticket)

        if satisfied and within_window:
            summary = self._format_evidence_summary(evidence)
            await self._mark_verified(ticket, unit, evidence, summary)
            return True

        reason = self._build_reopen_reason(policy_entry, evidence_types, ticket, satisfied, within_window)
        await self._mark_reopened(ticket, evidence, reason)
        return False

    async def _mark_verified(
        self,
        ticket: TicketRecord,
        unit: RemediationUnitRecord,
        evidence: Iterable[EvidenceRecord],
        summary: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        ticket.status = TicketStatus.VERIFIED
        ticket.verified_at = now
        await self._ticket_repo.upsert_ticket(ticket)

        unit.status = FindingLifecycleStatus.VERIFIED
        unit.timestamp = now
        await self._remediation_repo.upsert_unit(unit)

        for canonical_id in unit.canonical_ids:
            finding = await self._canonical_repo.get_by_canonical_id(canonical_id)
            if not finding:
                continue
            finding.status = FindingLifecycleStatus.VERIFIED
            finding.timestamp = now
            await self._canonical_repo.upsert_finding(finding)

        await self._mark_evidence(evidence, accepted=True)
        await self._safe_mark_ticket_verified(ticket.external_key, summary)

    async def _mark_reopened(
        self,
        ticket: TicketRecord,
        evidence: Iterable[EvidenceRecord],
        reason: str,
    ) -> None:
        ticket.status = TicketStatus.REOPENED
        ticket.sla_breached = True
        await self._ticket_repo.upsert_ticket(ticket)
        await self._mark_evidence(evidence, accepted=False)
        await self._safe_reopen_ticket(ticket.external_key, reason)

    async def _mark_evidence(self, evidence: Iterable[EvidenceRecord], accepted: bool) -> None:
        for record in evidence:
            record.verification_status = (
                VerificationStatus.ACCEPTED if accepted else VerificationStatus.REJECTED
            )
            record.timestamp = datetime.now(timezone.utc)
            await self._evidence_repo.upsert_evidence(record)

    def _within_window(self, entry, ticket: TicketRecord) -> bool:
        if not ticket.resolved_at:
            return True
        deadline = ticket.resolved_at + entry.window
        return datetime.now(timezone.utc) <= deadline

    def _ensure_bucket_enum(self, bucket: RemediationBucket | str) -> RemediationBucket:
        if isinstance(bucket, RemediationBucket):
            return bucket
        return RemediationBucket(bucket)

    def _build_run_event(
        self,
        *,
        correlation_id: str,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        metrics: Optional[Dict[str, int]] = None,
    ) -> RunEventRecord:
        record = RunEventRecord(
            id=correlation_id,
            correlation_id=correlation_id,
            agent_name=AgentType.VERIFICATION.value,
            run_type="verification_batch",
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics or {},
        )
        record.timestamp = completed_at or started_at or datetime.now(timezone.utc)
        return record

    def _format_evidence_summary(self, evidence: Iterable[EvidenceRecord]) -> str:
        lines: List[str] = []
        for record in sorted(evidence, key=lambda item: item.captured_at):
            captured = record.captured_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
            etype = record.evidence_type
            if not isinstance(etype, EvidenceType):
                try:
                    etype = EvidenceType(etype)
                except ValueError:
                    pass
            type_label = etype.value if isinstance(etype, EvidenceType) else str(etype)
            detail_parts = [type_label, f"captured {captured}"]
            if record.source_uri:
                detail_parts.append(f"source: {record.source_uri}")
            if record.details:
                detail_parts.append(f"details: {record.details}")
            lines.append(" - " + ", ".join(detail_parts))
        if not lines:
            return "Verification satisfied; evidence recorded outside platform."
        return "Evidence accepted:\n" + "\n".join(lines)

    def _build_reopen_reason(
        self,
        entry,
        evidence_types: Iterable[EvidenceType],
        ticket: TicketRecord,
        satisfied: bool,
        within_window: bool,
    ) -> str:
        reasons: List[str] = []
        if not satisfied:
            provided = ", ".join(
                sorted({getattr(etype, "value", str(etype)) for etype in evidence_types})
            ) or "none"
            combos = [
                " + ".join(getattr(item, "value", str(item)) for item in group)
                for group in entry.rule.required_sets
            ]
            reasons.append(
                "Evidence requirements not met. Provided: "
                f"{provided}. Required combinations: {', '.join(combos)}."
            )
        if not within_window and ticket.resolved_at:
            deadline = ticket.resolved_at + entry.window
            reasons.append(f"Verification window expired at {deadline.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}")
        if not reasons:
            reasons.append("Verification requirements not satisfied.")
        return " ".join(reasons)

    async def _safe_mark_ticket_verified(self, issue_key: Optional[str], summary: str) -> None:
        if not issue_key:
            return
        try:
            await self._jira.mark_ticket_verified(issue_key, summary)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to transition ticket %s to Verified: %s", issue_key, exc)

    async def _safe_reopen_ticket(self, issue_key: Optional[str], reason: str) -> None:
        if not issue_key:
            return
        try:
            await self._jira.reopen_ticket(issue_key, reason=reason)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to reopen ticket %s: %s", issue_key, exc)


__all__ = ["VerificationService"]
