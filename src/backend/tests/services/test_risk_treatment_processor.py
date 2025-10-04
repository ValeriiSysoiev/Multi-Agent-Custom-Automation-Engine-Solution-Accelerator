import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

try:  # pragma: no branch - prefer real SDK
    import azure.core.exceptions  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback stubs
    import types

    if "azure" not in sys.modules:
        sys.modules["azure"] = types.ModuleType("azure")
    azure_core = sys.modules.setdefault("azure.core", types.ModuleType("azure.core"))
    azure_core_exceptions = sys.modules.setdefault(
        "azure.core.exceptions", types.ModuleType("azure.core.exceptions")
    )

    class ResourceNotFoundError(Exception):
        pass

    azure_core_exceptions.ResourceNotFoundError = ResourceNotFoundError

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from models.messages_kernel import (
    AgentType,
    ApplicationContext,
    AssetIdentifier,
    AssetIdentifierType,
    CanonicalFinding,
    EnrichmentRecord,
    ExposureSurface,
    FindingLifecycleStatus,
    RiskTier,
    RiskTreatmentStatus,
    RiskTreatmentTask,
    RiskTreatmentWorkflow,
    RunEventRecord,
    TriageRecord,
    TreatmentRecommendation,
    ResidualRisk,
)
from services.risk_treatment_processor import RiskTreatmentProcessor


class MemoryRiskTreatmentRepository:
    def __init__(self, tasks):
        self.tasks = tasks

    async def list_pending(self, *, workflow=None, limit=100):
        del workflow
        return [task for task in self.tasks if task.status == RiskTreatmentStatus.PENDING][:limit]

    async def upsert_task(self, task: RiskTreatmentTask):
        for idx, existing in enumerate(self.tasks):
            if existing.task_id == task.task_id:
                self.tasks[idx] = task
                return task
        self.tasks.append(task)
        return task


class MemoryCanonicalRepository:
    def __init__(self, finding: CanonicalFinding):
        self.finding = finding

    async def get_by_id(self, canonical_id: str, asset_id: str):
        if canonical_id == self.finding.canonical_id and asset_id == self.finding.asset_id:
            return self.finding
        return None


class MemoryTriageRepository:
    def __init__(self, record: TriageRecord):
        self.record = record

    async def list_for_canonical(self, canonical_id: str, limit: int = 50):  # noqa: ARG002
        return [self.record]


class MemoryEnrichmentRepository:
    def __init__(self, enrichment: EnrichmentRecord):
        self.enrichment = enrichment

    async def get_enrichment(self, canonical_id: str, asset_id: str):
        if canonical_id == self.enrichment.canonical_id and asset_id == self.enrichment.asset_id:
            return self.enrichment
        return None


class MemoryRunEventRepository:
    def __init__(self):
        self.events: list[RunEventRecord] = []

    async def upsert_event(self, record: RunEventRecord):
        self.events.append(record)
        return record


class FakeJiraTicketClient:
    def __init__(self):
        self.created = []
        self.updates = {}
        self._asset_hosts_field = "customfield_10120"
        self._asset_apps_field = "customfield_10121"

    async def create_waiver_ticket(self, summary, description, expiry, status, custom_fields=None):  # noqa: ARG002
        issue_key = f"CYB-{len(self.created) + 100}"
        browse_url = f"https://jira/browse/{issue_key}"
        self.created.append(
            {
                "summary": summary,
                "description": description,
                "expiry": expiry,
                "status": status,
                "custom_fields": custom_fields,
            }
        )
        return type("Result", (), {"issue_key": issue_key, "browse_url": browse_url})

    async def update_issue_fields(self, issue_key, fields):
        self.updates[issue_key] = fields

    async def find_user_account_id(self, email):
        if not email:
            return None
        return f"account-{email.lower()}"

    async def close(self):
        return None


class FakeJiraAssetsClient:
    def __init__(self):
        self.calls = []

    async def resolve_asset_links(self, asset_identifiers):
        self.calls.append(list(asset_identifiers))
        return ([{"objectId": "host-1"}], {"objectId": "app-1"})

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_processor_creates_risk_acceptance_ticket():
    now = datetime.now(timezone.utc)
    canonical = CanonicalFinding(
        id="canon-1",
        canonical_id="canon-1",
        asset_id="asset-1",
        asset_identifiers=[AssetIdentifier(id_type=AssetIdentifierType.HOSTNAME, value="vm-1")],
        sources=[],
        vuln_key="CVE-2024-0001",
        severity="high",
        risk_tier=RiskTier.HIGH,
        status=FindingLifecycleStatus.TRIAGED,
        remediation_bucket="control",
    )

    triage = TriageRecord(
        id="tri-1",
        triage_id="tri-1",
        canonical_id="canon-1",
        created_by=AgentType.TRIAGE.value,
        likelihood=3,
        impact=4,
        risk_score=12,
        risk_tier=RiskTier.HIGH,
        treatment=TreatmentRecommendation.ACCEPT,
        rationale="Risk accepted due to strong controls.",
        supporting_inputs={"treatment_metadata": {"waiver_justification": "Controls adequate"}},
        residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM, rationale="Monitored by SOC"),
        supersedes=None,
    )

    enrichment = EnrichmentRecord(
        id="canon-1",
        canonical_id="canon-1",
        asset_id="asset-1",
        application_context=ApplicationContext(
            application="Payments API",
            owner="Owner",
            owner_email="owner@example.com",
            environment="Prod",
        ),
        exposure=ExposureSurface(internet_facing=True),
        threat_signals=[],
    )

    task = RiskTreatmentTask(
        id="rt-1",
        task_id="rt-1",
        canonical_id="canon-1",
        triage_id="tri-1",
        asset_id="asset-1",
        workflow=RiskTreatmentWorkflow.WAIVER,
        treatment=TreatmentRecommendation.ACCEPT,
        risk_tier=RiskTier.HIGH,
        residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM, rationale="Monitored"),
        status=RiskTreatmentStatus.PENDING,
        justification="Controls adequate",
    )

    risk_repo = MemoryRiskTreatmentRepository([task])
    fake_jira = FakeJiraTicketClient()
    fake_assets = FakeJiraAssetsClient()
    run_repo = MemoryRunEventRepository()
    processor = RiskTreatmentProcessor(
        risk_repo=risk_repo,
        canonical_repo=MemoryCanonicalRepository(canonical),
        triage_repo=MemoryTriageRepository(triage),
        enrichment_repo=MemoryEnrichmentRepository(enrichment),
        jira_ticket_client=fake_jira,
        jira_assets_client=fake_assets,
        run_repo=run_repo,
    )

    metrics = await processor.process(limit=10)

    assert metrics["waiver_created"] == 1
    updated_task = risk_repo.tasks[0]
    assert updated_task.status == RiskTreatmentStatus.IN_PROGRESS
    assert updated_task.ticket_key.startswith("CYB-")
    assert updated_task.ticket_url.endswith(updated_task.ticket_key)
    assert fake_jira.created
    issue_key = updated_task.ticket_key
    assert issue_key in fake_jira.updates
    update_fields = fake_jira.updates[issue_key]
    assert update_fields["customfield_10072"]["value"] == "Accept"
    assert update_fields["customfield_10079"]["value"] == "No"
    assert run_repo.events and run_repo.events[0].run_type == "risk_treatment_processor"


@pytest.mark.asyncio
async def test_processor_creates_risk_transfer_ticket():
    canonical = CanonicalFinding(
        id="canon-2",
        canonical_id="canon-2",
        asset_id="asset-2",
        asset_identifiers=[AssetIdentifier(id_type=AssetIdentifierType.HOSTNAME, value="vm-2")],
        sources=[],
        vuln_key="CVE-TRANSFER",
        severity="medium",
        risk_tier=RiskTier.MEDIUM,
        status=FindingLifecycleStatus.TRIAGED,
        remediation_bucket="config",
    )

    triage = TriageRecord(
        id="tri-2",
        triage_id="tri-2",
        canonical_id="canon-2",
        created_by=AgentType.TRIAGE.value,
        likelihood=2,
        impact=3,
        risk_score=6,
        risk_tier=RiskTier.MEDIUM,
        treatment=TreatmentRecommendation.TRANSFER,
        rationale="Vendor will remediate in SLA.",
        supporting_inputs={"treatment_metadata": {"risk_transfer_notes": "Vendor XYZ notified."}},
        residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM, rationale="Pending vendor"),
        supersedes=None,
    )

    enrichment = EnrichmentRecord(
        id="canon-2",
        canonical_id="canon-2",
        asset_id="asset-2",
        application_context=ApplicationContext(
            application="Billing",
            owner="FinanceOwner",
            owner_email="finance@example.com",
            environment="Prod",
        ),
        exposure=ExposureSurface(internet_facing=False),
        threat_signals=[],
    )

    task = RiskTreatmentTask(
        id="rt-2",
        task_id="rt-2",
        canonical_id="canon-2",
        triage_id="tri-2",
        asset_id="asset-2",
        workflow=RiskTreatmentWorkflow.RISK_TRANSFER,
        treatment=TreatmentRecommendation.TRANSFER,
        risk_tier=RiskTier.MEDIUM,
        residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM, rationale="Pending vendor"),
        status=RiskTreatmentStatus.PENDING,
    )

    risk_repo = MemoryRiskTreatmentRepository([task])
    fake_jira = FakeJiraTicketClient()
    processor = RiskTreatmentProcessor(
        risk_repo=risk_repo,
        canonical_repo=MemoryCanonicalRepository(canonical),
        triage_repo=MemoryTriageRepository(triage),
        enrichment_repo=MemoryEnrichmentRepository(enrichment),
        jira_ticket_client=fake_jira,
        jira_assets_client=FakeJiraAssetsClient(),
        run_repo=MemoryRunEventRepository(),
    )

    metrics = await processor.process(limit=10)

    assert metrics["transfer_created"] == 1
    updated_task = risk_repo.tasks[0]
    assert updated_task.status == RiskTreatmentStatus.IN_PROGRESS
    issue_key = updated_task.ticket_key
    update_fields = fake_jira.updates[issue_key]
    assert update_fields["customfield_10072"]["value"] == "Transfer"
