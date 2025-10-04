"""Service orchestrating remediation unit creation and Jira ticketing."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

from models.messages_kernel import (
    AgentType,
    CanonicalFinding,
    EnrichmentRecord,
    FindingLifecycleStatus,
    RemediationBucket,
    RemediationUnitRecord,
    RiskTier,
    RiskTreatmentTask,
    RiskTreatmentWorkflow,
    RunEventRecord,
    TicketRecord,
    TicketStatus,
    TriageRecord,
    TreatmentRecommendation,
)
from repositories.canonical_finding_repository import CanonicalFindingRepository
from repositories.enrichment_repository import EnrichmentRepository
from repositories.remediation_unit_repository import RemediationUnitRepository
from repositories.risk_treatment_repository import RiskTreatmentRepository
from repositories.run_event_repository import RunEventRepository
from repositories.ticket_repository import TicketRepository
from repositories.triage_repository import TriageRepository
from services.jira_assets_client import JiraAssetsClient
from services.jira_ticket_client import JiraTicketClient, JiraTicketData
from services.remediation_policy import RemediationPolicy, RemediationSLA

logger = logging.getLogger(__name__)


@dataclass
class FindingBundle:
    finding: CanonicalFinding
    triage: TriageRecord
    enrichment: EnrichmentRecord


@dataclass
class RemediationRunResult:
    created_units: List[str] = field(default_factory=list)
    created_tickets: List[str] = field(default_factory=list)
    skipped: Dict[str, str] = field(default_factory=dict)
    follow_up_tasks: Dict[str, str] = field(default_factory=dict)

    @property
    def unit_count(self) -> int:
        return len(self.created_units)

    @property
    def ticket_count(self) -> int:
        return len(self.created_tickets)


class RemediationService:
    """Group triaged findings into remediation units and create Jira tickets."""

    def __init__(
        self,
        canonical_repo: Optional[CanonicalFindingRepository] = None,
        triage_repo: Optional[TriageRepository] = None,
        enrichment_repo: Optional[EnrichmentRepository] = None,
        remediation_repo: Optional[RemediationUnitRepository] = None,
        ticket_repo: Optional[TicketRepository] = None,
        run_repo: Optional[RunEventRepository] = None,
        jira_ticket_client: Optional[JiraTicketClient] = None,
        jira_assets_client: Optional[JiraAssetsClient] = None,
        policy: Optional[RemediationPolicy] = None,
        treatment_repo: Optional[RiskTreatmentRepository] = None,
    ) -> None:
        self._canonical_repo = canonical_repo or CanonicalFindingRepository()
        self._triage_repo = triage_repo or TriageRepository()
        self._enrichment_repo = enrichment_repo or EnrichmentRepository()
        self._remediation_repo = remediation_repo or RemediationUnitRepository()
        self._ticket_repo = ticket_repo or TicketRepository()
        self._run_repo = run_repo or RunEventRepository()
        self._jira_ticket = jira_ticket_client or JiraTicketClient()
        self._jira_assets = jira_assets_client or JiraAssetsClient()
        self._policy = policy or RemediationPolicy()
        self._treatment_repo = treatment_repo or RiskTreatmentRepository()

    async def close(self) -> None:
        await self._jira_ticket.close()
        await self._jira_assets.close()

    async def plan_and_create(
        self,
        *,
        limit: int = 50,
        actor: str = AgentType.REMEDIATION.value,
    ) -> RemediationRunResult:
        pending = await self._canonical_repo.list_ready_for_remediation(limit=limit)
        if not pending:
            logger.info("No triaged findings pending remediation")
            return RemediationRunResult()

        correlation_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        metrics = {
            "processed": 0,
            "skipped": 0,
            "units": 0,
            "tickets": 0,
            "follow_up_accept": 0,
            "follow_up_transfer": 0,
            "skipped_missing_triage": 0,
            "skipped_missing_enrichment": 0,
        }

        await self._run_repo.upsert_event(
            self._build_run_event(
                correlation_id=correlation_id,
                status="started",
                started_at=started_at,
                metrics=metrics,
            )
        )

        bundles, skipped, follow_ups = await self._prepare_bundles(
            pending,
            metrics,
            actor=actor,
        )
        result = await self._create_units_and_tickets(bundles, metrics)
        result.skipped.update(skipped)
        result.follow_up_tasks.update(follow_ups)

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

        logger.info(
            "Remediation run complete: units=%d tickets=%d skipped=%d",
            result.unit_count,
            result.ticket_count,
            len(result.skipped),
        )
        return result

    async def _prepare_bundles(
        self,
        findings: Iterable[CanonicalFinding],
        metrics: Dict[str, int],
        *,
        actor: str,
    ) -> tuple[List[FindingBundle], Dict[str, str], Dict[str, str]]:
        bundles: List[FindingBundle] = []
        skipped: Dict[str, str] = {}
        follow_ups: Dict[str, str] = {}
        for finding in findings:
            metrics["processed"] += 1
            triage = await self._triage_repo.get_latest(finding.canonical_id)
            if not triage:
                metrics["skipped"] += 1
                metrics["skipped_missing_triage"] += 1
                skipped[finding.canonical_id] = "missing_triage"
                continue
            if triage.treatment not in {TreatmentRecommendation.MITIGATE, TreatmentRecommendation.AVOID}:
                followup = await self._route_treatment_follow_up(
                    finding=finding,
                    triage=triage,
                    actor=actor,
                )
                if followup:
                    follow_ups[finding.canonical_id] = followup
                    if triage.treatment == TreatmentRecommendation.ACCEPT:
                        metrics["follow_up_accept"] += 1
                    elif triage.treatment == TreatmentRecommendation.TRANSFER:
                        metrics["follow_up_transfer"] += 1
                else:
                    metrics["skipped"] += 1
                    skipped_key = f"treatment_{triage.treatment.value}"
                    skipped[finding.canonical_id] = skipped_key
                continue
            enrichment = await self._enrichment_repo.get_enrichment(finding.canonical_id, finding.asset_id)
            if not enrichment:
                metrics["skipped"] += 1
                metrics["skipped_missing_enrichment"] += 1
                skipped[finding.canonical_id] = "missing_enrichment"
                continue
            bundles.append(FindingBundle(finding=finding, triage=triage, enrichment=enrichment))
        return bundles, skipped, follow_ups

    async def _create_units_and_tickets(
        self,
        bundles: Iterable[FindingBundle],
        metrics: Dict[str, int],
    ) -> RemediationRunResult:
        grouped: Dict[tuple, List[FindingBundle]] = defaultdict(list)
        for bundle in bundles:
            key = self._group_key(bundle)
            grouped[key].append(bundle)

        result = RemediationRunResult()
        now = datetime.now(timezone.utc)

        for key, items in grouped.items():
            unit_id = f"ru-{uuid4()}"
            sla = self._policy.get_sla(
                bucket=key.bucket,
                risk_tier=key.risk_tier,
                environment=key.environment,
            )
            due_at = now + sla.due

            unit = RemediationUnitRecord(
                id=unit_id,
                remediation_unit_id=unit_id,
                name=self._unit_name(key, items),
                bucket=key.bucket,
                risk_tier=key.risk_tier,
                status=FindingLifecycleStatus.IN_REMEDIATION,
                canonical_ids=[bundle.finding.canonical_id for bundle in items],
                target_due_date=due_at,
                owner=key.owner,
                notes=None,
            )
            await self._remediation_repo.upsert_unit(unit)
            metrics["units"] += 1
            result.created_units.append(unit_id)

            ticket_payload = await self._build_ticket_payload(unit, items, sla, now)
            jira_result = await self._jira_ticket.create_remediation_ticket(ticket_payload)
            metrics["tickets"] += 1
            result.created_tickets.append(jira_result.issue_key)

            ticket_record = TicketRecord(
                id=jira_result.issue_id,
                ticket_id=jira_result.issue_id,
                remediation_unit_id=unit_id,
                external_key=jira_result.issue_key,
                url=jira_result.browse_url,
                status=TicketStatus.OPEN,
                opened_at=now,
                due_at=ticket_payload.sla_due,
                ack_due=ticket_payload.ack_due,
                verify_due=ticket_payload.verify_due,
                sla_breached=False,
            )
            await self._ticket_repo.upsert_ticket(ticket_record)

            for bundle in items:
                bundle.finding.status = FindingLifecycleStatus.IN_REMEDIATION
                bundle.finding.remediation_unit_id = unit_id
                bundle.finding.timestamp = now
                await self._canonical_repo.upsert_finding(bundle.finding)

        return result

    async def _route_treatment_follow_up(
        self,
        *,
        finding: CanonicalFinding,
        triage: TriageRecord,
        actor: str,
    ) -> Optional[str]:
        workflow: Optional[RiskTreatmentWorkflow] = None
        if triage.treatment == TreatmentRecommendation.ACCEPT:
            workflow = RiskTreatmentWorkflow.WAIVER
        elif triage.treatment == TreatmentRecommendation.TRANSFER:
            workflow = RiskTreatmentWorkflow.RISK_TRANSFER

        if workflow is None:
            return None

        enrichment = await self._enrichment_repo.get_enrichment(
            finding.canonical_id,
            finding.asset_id,
        )

        metadata: Dict[str, object] = {}
        if isinstance(triage.supporting_inputs, dict):
            meta_candidate = triage.supporting_inputs.get("treatment_metadata")
            if isinstance(meta_candidate, dict):
                metadata = meta_candidate

        controls: List[str] = []
        raw_controls = metadata.get("compensating_controls") if metadata else None
        if isinstance(raw_controls, list):
            controls = [str(item).strip() for item in raw_controls if isinstance(item, (str,)) and str(item).strip()]

        justification = None
        if metadata:
            justification = metadata.get("waiver_justification") or metadata.get("risk_transfer_notes")
            if isinstance(justification, str):
                justification = justification.strip() or None
        if not justification:
            justification = triage.rationale

        proposed_expiry = None
        if metadata:
            expiry_days = metadata.get("waiver_expiry_days")
            if isinstance(expiry_days, int) and expiry_days > 0:
                proposed_expiry = datetime.now(timezone.utc) + timedelta(days=expiry_days)

        task_id = f"rt-{uuid4()}"
        task = RiskTreatmentTask(
            id=task_id,
            task_id=task_id,
            canonical_id=finding.canonical_id,
            triage_id=triage.triage_id,
            asset_id=finding.asset_id,
            asset_owner=(enrichment.application_context.owner if enrichment else None),
            application=(enrichment.application_context.application if enrichment else None),
            workflow=workflow,
            treatment=triage.treatment,
            risk_tier=triage.risk_tier,
            residual_risk=triage.residual_risk,
            rationale=triage.rationale,
            requested_by=actor,
            justification=justification,
            compensating_controls=controls,
            proposed_expiry=proposed_expiry,
            triage_reference=triage.triage_id,
            notes=(
                "Route to waiver workflow" if workflow == RiskTreatmentWorkflow.WAIVER
                else "Route to risk transfer workflow"
            ),
        )

        await self._treatment_repo.upsert_task(task)

        finding.treatment_follow_up_id = task_id
        finding.timestamp = datetime.now(timezone.utc)
        await self._canonical_repo.upsert_finding(finding)

        logger.info(
            "Queued %s follow-up for %s (task_id=%s)",
            workflow.value,
            finding.canonical_id,
            task_id,
        )
        return task_id

    def _group_key(self, bundle: FindingBundle):  # type: ignore[override]
        triage = bundle.triage
        enrichment = bundle.enrichment
        owner = enrichment.application_context.owner
        environment = enrichment.application_context.environment or "default"
        recommendations = bundle.finding.recommendations or ""
        bucket = bundle.finding.remediation_bucket
        if isinstance(bucket, str):
            bucket = RemediationBucket(bucket)
        risk_tier = triage.risk_tier
        if isinstance(risk_tier, str):
            risk_tier = RiskTier(risk_tier)
        return _GroupKey(
            bucket=bucket,
            vuln_key=bundle.finding.vuln_key,
            recommendations=recommendations.strip().lower(),
            owner=owner or "",
            application=enrichment.application_context.application or "",
            environment=environment,
            risk_tier=risk_tier,
        )

    async def _build_ticket_payload(
        self,
        unit: RemediationUnitRecord,
        items: List[FindingBundle],
        sla: RemediationSLA,
        now: datetime,
    ) -> JiraTicketData:
        primary = items[0]
        triage = primary.triage
        enrichment = primary.enrichment
        bucket_enum = self._ensure_bucket_enum(unit.bucket)
        bucket_label = bucket_enum.name.upper()
        risk_enum = triage.risk_tier if isinstance(triage.risk_tier, RiskTier) else RiskTier(triage.risk_tier)
        risk_label = risk_enum.name.replace("_", " ").title()
        treatment_enum = (
            triage.treatment if isinstance(triage.treatment, TreatmentRecommendation) else TreatmentRecommendation(triage.treatment)
        )
        treatment_label = treatment_enum.name.title()

        summary = self._summary(unit, primary)
        ack_due = now + sla.ack if sla.ack else now
        due_at = now + sla.due
        verify_due = now + sla.verify if sla.verify else now
        description = self._description(unit, items, sla, ack_due, due_at, verify_due)

        application_ids: List[str] = []
        asset_ids: List[str] = []
        try:
            asset_ids, application_id = await self._jira_assets.resolve_asset_links(primary.finding.asset_identifiers)
        except Exception as exc:  # pragma: no cover - resilience
            logger.warning("Failed to resolve Jira asset links for %s: %s", primary.finding.canonical_id, exc)
            asset_ids, application_id = [], None
        if application_id:
            application_ids.append(application_id)

        kev_flag = self._has_kev_signal(enrichment)
        cves = self._collect_cves(items)

        payload = JiraTicketData(
            summary=summary,
            description=description,
            risk_tier=risk_label,
            risk_score=triage.risk_score,
            likelihood=triage.likelihood,
            impact=triage.impact,
            treatment=treatment_label,
            bucket=bucket_label,
            sla_due=due_at,
            ack_due=ack_due,
            verify_due=verify_due,
            residual_risk=(triage.residual_risk.rationale if triage.residual_risk else None),
            triage_link=triage.triage_id,
            kev=kev_flag,
            internet_exposed=enrichment.exposure.internet_facing,
            cves=cves,
            labels=["AI_VM", bucket_label, risk_enum.name.upper()],
            due_date=due_at,
            custom_fields={},
            application_ids=application_ids,
            asset_ids=asset_ids,
        )
        return payload

    def _summary(self, unit: RemediationUnitRecord, primary: FindingBundle) -> str:
        application = primary.enrichment.application_context.application
        bucket = self._ensure_bucket_enum(unit.bucket)
        if bucket == RemediationBucket.CONTROL:
            verb = "Implement control for"
        else:
            verb = "Remediate"
        if application:
            summary = f"{verb} {primary.finding.vuln_key} on {application}"
        else:
            summary = f"{verb} {primary.finding.vuln_key} ({primary.finding.asset_id})"
        return self._truncate(summary, 255)

    def _unit_name(self, key: "_GroupKey", items: List[FindingBundle]) -> str:
        if key.application:
            return f"{key.bucket.name.title()} {key.vuln_key} - {key.application}"
        return f"{key.bucket.name.title()} {key.vuln_key} - {items[0].finding.asset_id}"

    def _description(
        self,
        unit: RemediationUnitRecord,
        items: List[FindingBundle],
        sla: RemediationSLA,
        ack_due: datetime,
        due_at: datetime,
        verify_due: datetime,
    ) -> str:
        triage = items[0].triage
        risk_enum = triage.risk_tier if isinstance(triage.risk_tier, RiskTier) else RiskTier(triage.risk_tier)
        treatment_enum = (
            triage.treatment if isinstance(triage.treatment, TreatmentRecommendation) else TreatmentRecommendation(triage.treatment)
        )
        sections = []
        sections.append("*Risk Overview*\n")
        sections.append(
            f"- Risk tier: {risk_enum.name.title()} (score {triage.risk_score}, L={triage.likelihood} I={triage.impact})\n"
        )
        sections.append(f"- Treatment: {treatment_enum.name.title()}\n")
        bucket_enum = self._ensure_bucket_enum(items[0].finding.remediation_bucket)
        sections.append(f"- Bucket: {bucket_enum.name.title()}\n")

        sections.append("\n*Affected Assets*\n")
        for bundle in items:
            context = bundle.enrichment.application_context
            sections.append(
                f"- {bundle.finding.asset_id} — owner: {context.owner or 'unassigned'}; application: {context.application or 'n/a'}\n"
            )

        recommendation = items[0].finding.recommendations
        if recommendation:
            header = "*Recommended Action*" if bucket_enum != RemediationBucket.CONTROL else "*Control Implementation Guidance*"
            sections.append(f"\n{header}\n")
            sections.append(f"{recommendation}\n")
        elif bucket_enum == RemediationBucket.CONTROL:
            sections.append("\n*Control Implementation Guidance*\n")
            sections.append("Implement the approved compensating control, monitor its effectiveness, and document evidence for verification.\n")

        sections.append("\n*SLA Commitments*\n")
        sections.append(
            f"- Acknowledge by {ack_due.strftime('%Y-%m-%d %H:%M UTC')} (window {self._hours_repr(sla.ack)})\n"
        )
        sections.append(
            f"- Remediation due by {due_at.strftime('%Y-%m-%d %H:%M UTC')} (window {self._hours_repr(sla.due)})\n"
        )
        sections.append(
            f"- Verification evidence due by {verify_due.strftime('%Y-%m-%d %H:%M UTC')} (window {self._hours_repr(sla.verify)})\n"
        )
        if sla.emergency_ok:
            sections.append("- Emergency change window authorised for this risk tier/bucket.\n")

        return "".join(sections)

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[: limit - 3].rstrip() + "..."

    def _hours_repr(self, delta: timedelta) -> str:
        total_hours = delta.total_seconds() / 3600
        hours_int = int(total_hours)
        if total_hours <= 24:
            return f"{int(round(total_hours))} hours"
        days = total_hours / 24
        if abs(days - round(days)) < 0.01:
            return f"{int(round(days))} days"
        return f"{days:.1f} days"

    def _collect_cves(self, items: Iterable[FindingBundle]) -> List[str]:
        cves = []
        for bundle in items:
            if bundle.finding.vuln_key not in cves:
                cves.append(bundle.finding.vuln_key)
        return cves

    def _has_kev_signal(self, enrichment) -> bool:
        for signal in enrichment.threat_signals:
            if signal.source == "cisa_kev" or "known_exploited" in signal.signal_type.lower():
                return True
        return False

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
    ):
        record = RunEventRecord(
            id=correlation_id,
            correlation_id=correlation_id,
            agent_name=AgentType.REMEDIATION.value,
            run_type="remediation_batch",
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics or {},
        )
        record.timestamp = completed_at or started_at or datetime.now(timezone.utc)
        return record


@dataclass(frozen=True)
class _GroupKey:
    bucket: RemediationBucket
    vuln_key: str
    recommendations: str
    owner: str
    application: str
    environment: str
    risk_tier: RiskTier


__all__ = ["RemediationService", "RemediationRunResult"]
