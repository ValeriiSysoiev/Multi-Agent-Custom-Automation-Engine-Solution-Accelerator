"""Process risk treatment tasks for waiver and risk-transfer workflows."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

from models.messages_kernel import (
    AgentType,
    CanonicalFinding,
    EnrichmentRecord,
    RiskTier,
    RiskTreatmentStatus,
    RiskTreatmentTask,
    RiskTreatmentWorkflow,
    RunEventRecord,
    TriageRecord,
)
from repositories.canonical_finding_repository import CanonicalFindingRepository
from repositories.enrichment_repository import EnrichmentRepository
from repositories.risk_treatment_repository import RiskTreatmentRepository
from repositories.run_event_repository import RunEventRepository
from repositories.triage_repository import TriageRepository
from services.jira_assets_client import JiraAssetsClient
from services.jira_ticket_client import JiraTicketClient

logger = logging.getLogger(__name__)

DEFAULT_WAIVER_EXPIRY_DAYS = 30


class RiskTreatmentProcessor:
    """Creates Jira intake tickets for risk acceptance/transfer follow-ups."""

    def __init__(
        self,
        *,
        risk_repo: Optional[RiskTreatmentRepository] = None,
        canonical_repo: Optional[CanonicalFindingRepository] = None,
        triage_repo: Optional[TriageRepository] = None,
        enrichment_repo: Optional[EnrichmentRepository] = None,
        jira_ticket_client: Optional[JiraTicketClient] = None,
        jira_assets_client: Optional[JiraAssetsClient] = None,
        run_repo: Optional[RunEventRepository] = None,
    ) -> None:
        self._risk_repo = risk_repo or RiskTreatmentRepository()
        self._canonical_repo = canonical_repo or CanonicalFindingRepository()
        self._triage_repo = triage_repo or TriageRepository()
        self._enrichment_repo = enrichment_repo or EnrichmentRepository()
        self._jira_ticket = jira_ticket_client or JiraTicketClient()
        self._jira_assets = jira_assets_client or JiraAssetsClient()
        self._run_repo = run_repo or RunEventRepository()

    async def process(self, *, limit: int = 25) -> Dict[str, int]:
        tasks = await self._risk_repo.list_pending(limit=limit)
        if not tasks:
            logger.info("No pending risk treatment tasks")
            return {}

        metrics: Dict[str, int] = {
            "pending": len(tasks),
            "waiver_created": 0,
            "transfer_created": 0,
            "skipped_missing_context": 0,
            "failed": 0,
        }
        processed_ids: List[str] = []

        for task in tasks:
            try:
                if task.workflow == RiskTreatmentWorkflow.WAIVER:
                    created = await self._handle_waiver_task(task)
                    if created:
                        metrics["waiver_created"] += 1
                        processed_ids.append(task.task_id)
                    else:
                        metrics["skipped_missing_context"] += 1
                elif task.workflow == RiskTreatmentWorkflow.RISK_TRANSFER:
                    created = await self._handle_transfer_task(task)
                    if created:
                        metrics["transfer_created"] += 1
                        processed_ids.append(task.task_id)
                    else:
                        metrics["skipped_missing_context"] += 1
                else:
                    logger.warning("Unsupported risk treatment workflow: %s", task.workflow)
            except Exception as exc:  # pragma: no cover - defensive logging
                metrics["failed"] += 1
                logger.exception("Failed to process risk treatment task %s", task.task_id)

        correlation_id = str(uuid4())
        now = datetime.now(timezone.utc)
        record = RunEventRecord(
            id=correlation_id,
            correlation_id=correlation_id,
            agent_name=AgentType.WAIVER.value,
            run_type="risk_treatment_processor",
            status="completed",
            started_at=now,
            completed_at=now,
            metrics=metrics,
        )
        record.timestamp = now
        await self._run_repo.upsert_event(record)

        logger.info(
            "Processed risk treatment tasks: %s", metrics
        )
        return metrics

    async def _handle_waiver_task(self, task: RiskTreatmentTask) -> bool:
        context = await self._load_context(task)
        if not context:
            return False
        canonical, triage, enrichment = context

        expiry = task.proposed_expiry or (datetime.now(timezone.utc) + timedelta(days=DEFAULT_WAIVER_EXPIRY_DAYS))
        summary = f"Risk acceptance for {canonical.vuln_key or canonical.canonical_id}"
        description = self._build_description(task, triage, enrichment)

        jira_result = await self._jira_ticket.create_waiver_ticket(
            summary=summary,
            description=description,
            expiry=expiry,
            status="Requested",
        )

        await self._apply_context_fields(
            issue_key=jira_result.issue_key,
            canonical=canonical,
            triage=triage,
            enrichment=enrichment,
            task=task,
            expiry=expiry,
        )

        await self._mark_in_progress(task, jira_result.issue_key, jira_result.browse_url)
        return True

    async def _handle_transfer_task(self, task: RiskTreatmentTask) -> bool:
        context = await self._load_context(task)
        if not context:
            return False
        canonical, triage, enrichment = context

        expiry = task.proposed_expiry or (datetime.now(timezone.utc) + timedelta(days=DEFAULT_WAIVER_EXPIRY_DAYS))
        summary = f"Risk transfer for {canonical.vuln_key or canonical.canonical_id}"
        description = self._build_description(task, triage, enrichment, for_transfer=True)

        jira_result = await self._jira_ticket.create_waiver_ticket(
            summary=summary,
            description=description,
            expiry=expiry,
            status="Requested",
        )

        await self._apply_context_fields(
            issue_key=jira_result.issue_key,
            canonical=canonical,
            triage=triage,
            enrichment=enrichment,
            task=task,
            expiry=expiry,
            treatment_label="Transfer",
        )

        await self._mark_in_progress(task, jira_result.issue_key, jira_result.browse_url)
        return True

    async def _load_context(
        self,
        task: RiskTreatmentTask,
    ) -> Optional[tuple[CanonicalFinding, TriageRecord, EnrichmentRecord]]:
        canonical = await self._canonical_repo.get_by_id(task.canonical_id, task.asset_id)
        if not canonical:
            logger.warning("Canonical finding not found for task %s", task.task_id)
            return None

        triage_records = await self._triage_repo.list_for_canonical(task.canonical_id)
        triage = next((record for record in triage_records if record.triage_id == task.triage_id), None)
        if not triage:
            logger.warning("Triage record %s not found for task %s", task.triage_id, task.task_id)
            return None

        enrichment = await self._enrichment_repo.get_enrichment(task.canonical_id, task.asset_id)
        if not enrichment:
            logger.warning("Enrichment missing for task %s", task.task_id)
            return None

        return canonical, triage, enrichment

    async def _apply_context_fields(
        self,
        *,
        issue_key: str,
        canonical: CanonicalFinding,
        triage: TriageRecord,
        enrichment: EnrichmentRecord,
        task: RiskTreatmentTask,
        expiry: datetime,
        treatment_label: Optional[str] = None,
    ) -> None:
        host_refs, app_ref = await self._jira_assets.resolve_asset_links(canonical.asset_identifiers)

        keV_flag = "Yes" if self._has_kev_signal(enrichment) else "No"
        internet_flag = "Yes" if enrichment.exposure.internet_facing else "No"

        residual_text = task.residual_risk.rationale or ""
        residual_value = self._risk_tier_label(task.residual_risk.risk_tier)
        if residual_text:
            residual_value = f"{residual_value} ({residual_text})"
        controls_text = "\n".join(task.compensating_controls)

        triage_link = task.triage_reference or ("" if not hasattr(triage, "triage_id") else triage.triage_id)
        cve_value = canonical.vuln_key

        risk_label = self._risk_tier_label(triage.risk_tier)
        treatment_value = treatment_label or (
            triage.treatment.value if hasattr(triage.treatment, "value") else str(triage.treatment)
        )
        update_fields: Dict[str, object] = {
            "summary": f"Risk {treatment_label or 'Acceptance'} - {canonical.vuln_key or canonical.canonical_id}",
            "description": self._build_description(task, triage, enrichment, for_transfer=(treatment_label == "Transfer")),
            self._jira_ticket._asset_hosts_field: host_refs,
            self._jira_ticket._asset_apps_field: [app_ref] if app_ref else [],
            "customfield_10068": {"value": risk_label},
            "customfield_10069": triage.risk_score,
            "customfield_10070": triage.likelihood,
            "customfield_10071": triage.impact,
            "customfield_10072": {"value": treatment_value.title()},
            "customfield_10074": expiry.strftime("%Y-%m-%d"),
            "customfield_10076": residual_value,
            "customfield_10077": controls_text or "None",
            "customfield_10079": {"value": keV_flag},
            "customfield_10080": {"value": internet_flag},
            "customfield_10081": cve_value,
        }

        if isinstance(triage_link, str) and triage_link.startswith(("http://", "https://")):
            update_fields["customfield_10078"] = triage_link

        if task.justification:
            update_fields.setdefault("description", self._build_description(task, triage, enrichment, for_transfer=(treatment_label == "Transfer")))

        owner_field = await self._resolve_business_owner(enrichment)
        if owner_field:
            update_fields["customfield_10067"] = owner_field

        if task.compensating_controls:
            update_fields["customfield_10077"] = "\n".join(task.compensating_controls)

        await self._jira_ticket.update_issue_fields(issue_key, update_fields)

    async def _mark_in_progress(self, task: RiskTreatmentTask, issue_key: str, browse_url: str) -> None:
        task.status = RiskTreatmentStatus.IN_PROGRESS
        task.ticket_key = issue_key
        task.ticket_url = browse_url
        task.timestamp = datetime.now(timezone.utc)
        await self._risk_repo.upsert_task(task)

    async def _resolve_business_owner(self, enrichment: EnrichmentRecord) -> Optional[Dict[str, str]]:
        owner_email = enrichment.application_context.owner_email
        if not owner_email:
            return None
        account_id = await self._jira_ticket.find_user_account_id(owner_email)
        if not account_id:
            return None
        return {"accountId": account_id}

    def _build_description(
        self,
        task: RiskTreatmentTask,
        triage: TriageRecord,
        enrichment: EnrichmentRecord,
        *,
        for_transfer: bool = False,
    ) -> str:
        lines = [
            triage.rationale,
            "",
        ]
        if task.justification:
            lines.append(f"Justification: {task.justification}")
        if task.compensating_controls:
            lines.append("Compensating Controls:")
            lines.extend(f"- {item}" for item in task.compensating_controls)
        if for_transfer and task.notes:
            lines.append(f"Transfer Notes: {task.notes}")
        residual = task.residual_risk
        tier_label = self._risk_tier_label(residual.risk_tier)
        residual_line = f"Residual Risk: {tier_label}"
        if residual.rationale:
            residual_line = f"{residual_line} ({residual.rationale})"
        lines.append(residual_line)
        if enrichment.application_context.environment:
            lines.append(f"Environment: {enrichment.application_context.environment}")
        return "\n".join(line for line in lines if line is not None)

    def _has_kev_signal(self, enrichment: EnrichmentRecord) -> bool:
        for signal in enrichment.threat_signals:
            if signal.source == "cisa_kev" or (
                isinstance(signal.signal_type, str)
                and "known_exploited" in signal.signal_type.lower()
            ):
                return True
        return False

    def _risk_tier_label(self, value: object) -> str:
        if isinstance(value, RiskTier):
            return value.name.title()
        if isinstance(value, str):
            try:
                return RiskTier(value).name.title()
            except ValueError:
                return value.title()
        return str(value)

    async def close(self) -> None:
        await self._jira_ticket.close()
        await self._jira_assets.close()


__all__ = ["RiskTreatmentProcessor"]
