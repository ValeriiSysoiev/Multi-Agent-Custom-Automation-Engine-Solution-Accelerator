import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from types import ModuleType
from pydantic import BaseModel, Field as PydanticField

os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example-openai")
os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
os.environ.setdefault("AZURE_OPENAI_API_VERSION", "2024-11-20")
os.environ.setdefault("AZURE_AI_SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("AZURE_AI_RESOURCE_GROUP", "rg-test")
os.environ.setdefault("AZURE_AI_PROJECT_NAME", "proj-test")
os.environ.setdefault("AZURE_AI_AGENT_ENDPOINT", "https://agents.example.com")
os.environ.setdefault("COSMOSDB_ENDPOINT", "https://example-cosmos")
os.environ.setdefault("COSMOSDB_DATABASE", "macae")
os.environ.setdefault("KEYVAULT_URI", "https://kv.example.vault.azure.net/")

if "semantic_kernel" not in sys.modules:
    semantic_kernel_module = ModuleType("semantic_kernel")
    sys.modules["semantic_kernel"] = semantic_kernel_module
    kernel_pydantic_module = ModuleType("semantic_kernel.kernel_pydantic")
    sys.modules["semantic_kernel.kernel_pydantic"] = kernel_pydantic_module
    semantic_kernel_module.kernel_pydantic = kernel_pydantic_module
    kernel_module = ModuleType("semantic_kernel.kernel")
    sys.modules["semantic_kernel.kernel"] = kernel_module
    semantic_kernel_module.kernel = kernel_module
    class _KernelBaseModel(BaseModel):
        class Config:
            arbitrary_types_allowed = True
            use_enum_values = True
    kernel_pydantic_module.KernelBaseModel = _KernelBaseModel
    kernel_pydantic_module.Field = PydanticField
    
    class _Kernel:  # lightweight stub for Kernel class
        pass

    kernel_module.Kernel = _Kernel
else:
    semantic_kernel_module = sys.modules["semantic_kernel"]
    if "kernel_pydantic" not in semantic_kernel_module.__dict__:
        kernel_pydantic_module = ModuleType("semantic_kernel.kernel_pydantic")
        sys.modules["semantic_kernel.kernel_pydantic"] = kernel_pydantic_module
        semantic_kernel_module.kernel_pydantic = kernel_pydantic_module
        kernel_pydantic_module.KernelBaseModel = BaseModel
        kernel_pydantic_module.Field = PydanticField
    if "kernel" not in semantic_kernel_module.__dict__:
        kernel_module = ModuleType("semantic_kernel.kernel")
        sys.modules["semantic_kernel.kernel"] = kernel_module
        semantic_kernel_module.kernel = kernel_module

        class _Kernel:  # pragma: no cover - stub for runtime dependency
            pass

        kernel_module.Kernel = _Kernel

try:
    import azure  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    if "azure" not in sys.modules:
        azure_module = ModuleType("azure")
        sys.modules["azure"] = azure_module


try:
    from azure.core import exceptions as azure_core_exceptions_module  # type: ignore
except ModuleNotFoundError:
    azure_core_exceptions_module = sys.modules.setdefault(
        "azure.core.exceptions", ModuleType("azure.core.exceptions")
    )

    class _ResourceNotFoundError(Exception):
        pass

    azure_core_exceptions_module.ResourceNotFoundError = _ResourceNotFoundError
else:
    if not hasattr(azure_core_exceptions_module, "ResourceNotFoundError"):
        class _ResourceNotFoundError(Exception):
            pass

        azure_core_exceptions_module.ResourceNotFoundError = _ResourceNotFoundError

from models.messages_kernel import (
    AgentType,
    ApplicationContext,
    AssetIdentifier,
    AssetIdentifierType,
    CanonicalFinding,
    ConfidenceLevel,
    EnrichmentRecord,
    ExposureSurface,
    FindingLifecycleStatus,
    RemediationBucket,
    RemediationUnitRecord,
    ResidualRisk,
    RiskTier,
    RiskTreatmentTask,
    RiskTreatmentWorkflow,
    TicketRecord,
    TicketStatus,
    TriageRecord,
    TreatmentRecommendation,
)
from services.remediation_policy import RemediationSLA
from services.remediation_service import RemediationRunResult, RemediationService
from services.jira_ticket_client import JiraTicketData, JiraTicketResult


class MemoryCanonicalRepository:
    def __init__(self, findings: List[CanonicalFinding]):
        self.findings = findings

    async def list_ready_for_remediation(self, limit: int = 100):
        ready = []
        for finding in self.findings:
            if finding.status != FindingLifecycleStatus.TRIAGED:
                continue
            if finding.remediation_unit_id:
                continue
            if getattr(finding, "treatment_follow_up_id", None):
                continue
            ready.append(finding)
        return ready[:limit]

    async def upsert_finding(self, finding: CanonicalFinding):
        for idx, item in enumerate(self.findings):
            if item.canonical_id == finding.canonical_id:
                self.findings[idx] = finding
                return finding
        self.findings.append(finding)
        return finding


class MemoryTriageRepository:
    def __init__(self, triage_map: Dict[str, TriageRecord]):
        self.triage_map = triage_map

    async def get_latest(self, canonical_id: str) -> Optional[TriageRecord]:
        return self.triage_map.get(canonical_id)


class MemoryEnrichmentRepository:
    def __init__(self, enrichment_map: Dict[str, EnrichmentRecord]):
        self.enrichment_map = enrichment_map

    async def get_enrichment(self, canonical_id: str, asset_id: str) -> Optional[EnrichmentRecord]:
        return self.enrichment_map.get(canonical_id)


class MemoryRemediationUnitRepository:
    def __init__(self):
        self.units: List[RemediationUnitRecord] = []

    async def upsert_unit(self, record: RemediationUnitRecord) -> RemediationUnitRecord:
        self.units.append(record)
        return record


class MemoryTicketRepository:
    def __init__(self):
        self.tickets: List[TicketRecord] = []

    async def upsert_ticket(self, record: TicketRecord) -> TicketRecord:
        self.tickets.append(record)
        return record


class MemoryRunEventRepository:
    def __init__(self):
        self.events = []

    async def upsert_event(self, record):
        self.events.append(record)
        return record


class MemoryRiskTreatmentRepository:
    def __init__(self):
        self.tasks: List[RiskTreatmentTask] = []

    async def upsert_task(self, task: RiskTreatmentTask):
        self.tasks.append(task)
        return task


class DummyJiraTicketClient:
    def __init__(self):
        self.payloads: List[JiraTicketData] = []

    async def create_remediation_ticket(self, payload: JiraTicketData) -> JiraTicketResult:
        self.payloads.append(payload)
        return JiraTicketResult(issue_id="10000", issue_key="CYB-1", self_url="https://jira/issue/10000", browse_url="https://jira/browse/CYB-1")

    async def close(self) -> None:
        return


class DummyJiraAssetsClient:
    def __init__(self):
        self.calls: List[List[AssetIdentifier]] = []

    async def resolve_asset_links(self, asset_identifiers: Iterable[AssetIdentifier]):
        self.calls.append(list(asset_identifiers))
        return (["13-456"], "11-123")

    async def close(self) -> None:
        return


class DummyPolicy:
    def get_sla(self, bucket, risk_tier, environment):
        return RemediationSLA(ack=timedelta(hours=1), due=timedelta(hours=48), verify=timedelta(hours=24), emergency_ok=True)


@pytest.mark.asyncio
async def test_remediation_service_creates_unit_and_ticket():
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
        remediation_bucket=RemediationBucket.PATCH,
        description="Sample vuln",
        recommendations="Apply patch KB1234",
        first_observed=now,
        last_observed=now,
    )

    triage = TriageRecord(
        id="tri-1",
        triage_id="tri-1",
        canonical_id="canon-1",
        created_by=AgentType.TRIAGE.value,
        likelihood=4,
        impact=5,
        risk_score=20,
        risk_tier=RiskTier.CRITICAL,
        treatment=TreatmentRecommendation.MITIGATE,
        rationale="High risk",
        supporting_inputs={},
        residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM, rationale="Pending fix"),
        supersedes=None,
    )

    context = ApplicationContext(
        application="Payments API",
        business_service="Checkout",
        owner="Owner",
        owner_email="owner@example.com",
        environment="Prod",
        criticality="Tier0",
        completeness=ConfidenceLevel.HIGH,
    )
    exposure = ExposureSurface(internet_facing=True, authentication_required=False, network_segment="DMZ", control_coverage={"waf": True})
    enrichment = EnrichmentRecord(
        id="canon-1",
        canonical_id="canon-1",
        asset_id="asset-1",
        application_context=context,
        exposure=exposure,
        threat_signals=[],
    )

    canonical_repo = MemoryCanonicalRepository([canonical])
    triage_repo = MemoryTriageRepository({"canon-1": triage})
    enrichment_repo = MemoryEnrichmentRepository({"canon-1": enrichment})
    remediation_repo = MemoryRemediationUnitRepository()
    ticket_repo = MemoryTicketRepository()
    run_repo = MemoryRunEventRepository()
    jira_client = DummyJiraTicketClient()
    assets_client = DummyJiraAssetsClient()
    policy = DummyPolicy()
    treatment_repo = MemoryRiskTreatmentRepository()

    service = RemediationService(
        canonical_repo=canonical_repo,
        triage_repo=triage_repo,
        enrichment_repo=enrichment_repo,
        remediation_repo=remediation_repo,
        ticket_repo=ticket_repo,
        run_repo=run_repo,
        jira_ticket_client=jira_client,
        jira_assets_client=assets_client,
        policy=policy,
        treatment_repo=treatment_repo,
    )

    result = await service.plan_and_create(limit=10)
    await service.close()

    assert result.unit_count == 1
    assert result.ticket_count == 1
    assert canonical_repo.findings[0].status == FindingLifecycleStatus.IN_REMEDIATION
    assert canonical_repo.findings[0].remediation_unit_id is not None
    assert remediation_repo.units[0].canonical_ids == ["canon-1"]
    assert ticket_repo.tickets[0].external_key == "CYB-1"
    assert jira_client.payloads[0].summary.startswith("Remediate CVE-2024-0001")
    expected_ack = now + timedelta(hours=1)
    expected_due = now + timedelta(hours=48)
    expected_verify = now + timedelta(hours=24)
    payload = jira_client.payloads[0]
    assert abs((payload.ack_due - expected_ack).total_seconds()) < 1
    assert abs((payload.sla_due - expected_due).total_seconds()) < 1
    assert abs((payload.verify_due - expected_verify).total_seconds()) < 1
    ticket_record = ticket_repo.tickets[0]
    assert abs((ticket_record.ack_due - expected_ack).total_seconds()) < 1
    assert abs((ticket_record.verify_due - expected_verify).total_seconds()) < 1
    assert "Acknowledge by" in jira_client.payloads[0].description
    assert "Verification evidence due" in jira_client.payloads[0].description


@pytest.mark.asyncio
async def test_control_bucket_updates_summary_and_description():
    now = datetime.now(timezone.utc)
    canonical = CanonicalFinding(
        id="canon-ctrl",
        canonical_id="canon-ctrl",
        asset_id="asset-ctrl",
        asset_identifiers=[AssetIdentifier(id_type=AssetIdentifierType.HOSTNAME, value="vm-ctrl")],
        sources=[],
        vuln_key="CVE-CTRL-0001",
        severity="high",
        risk_tier=RiskTier.HIGH,
        status=FindingLifecycleStatus.TRIAGED,
        remediation_bucket=RemediationBucket.CONTROL,
        description="Sample control",
        recommendations="Enable WAF rule to block exploit traffic.",
        first_observed=now,
        last_observed=now,
    )

    triage = TriageRecord(
        id="tri-ctrl",
        triage_id="tri-ctrl",
        canonical_id="canon-ctrl",
        created_by=AgentType.TRIAGE.value,
        likelihood=3,
        impact=4,
        risk_score=12,
        risk_tier=RiskTier.HIGH,
        treatment=TreatmentRecommendation.MITIGATE,
        rationale="Control required",
        supporting_inputs={},
        residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM, rationale="Pending control"),
        supersedes=None,
    )

    context = ApplicationContext(
        application="Payments API",
        business_service="Checkout",
        owner="Owner",
        owner_email="owner@example.com",
        environment="Prod",
        criticality="Tier0",
        completeness=ConfidenceLevel.HIGH,
    )
    exposure = ExposureSurface(internet_facing=True, authentication_required=False, network_segment="DMZ", control_coverage={"waf": True})
    enrichment = EnrichmentRecord(
        id="canon-ctrl",
        canonical_id="canon-ctrl",
        asset_id="asset-ctrl",
        application_context=context,
        exposure=exposure,
        threat_signals=[],
    )

    canonical_repo = MemoryCanonicalRepository([canonical])
    triage_repo = MemoryTriageRepository({"canon-ctrl": triage})
    enrichment_repo = MemoryEnrichmentRepository({"canon-ctrl": enrichment})
    remediation_repo = MemoryRemediationUnitRepository()
    ticket_repo = MemoryTicketRepository()
    run_repo = MemoryRunEventRepository()
    jira_client = DummyJiraTicketClient()
    assets_client = DummyJiraAssetsClient()
    policy = DummyPolicy()
    treatment_repo = MemoryRiskTreatmentRepository()

    service = RemediationService(
        canonical_repo=canonical_repo,
        triage_repo=triage_repo,
        enrichment_repo=enrichment_repo,
        remediation_repo=remediation_repo,
        ticket_repo=ticket_repo,
        run_repo=run_repo,
        jira_ticket_client=jira_client,
        jira_assets_client=assets_client,
        policy=policy,
        treatment_repo=treatment_repo,
    )

    await service.plan_and_create(limit=10)
    await service.close()

    payload = jira_client.payloads[0]
    assert payload.summary.startswith("Implement control")
    assert "Control Implementation Guidance" in payload.description


@pytest.mark.asyncio
async def test_accept_treatment_routes_to_waiver_follow_up():
    now = datetime.now(timezone.utc)
    canonical = CanonicalFinding(
        id="canon-accept",
        canonical_id="canon-accept",
        asset_id="asset-accept",
        asset_identifiers=[AssetIdentifier(id_type=AssetIdentifierType.HOSTNAME, value="vm-accept")],
        sources=[],
        vuln_key="CVE-2024-ACCEPT",
        severity="medium",
        risk_tier=RiskTier.MEDIUM,
        status=FindingLifecycleStatus.TRIAGED,
        remediation_bucket=RemediationBucket.PATCH,
        description="Acceptance candidate",
        recommendations="Document rationale",
        first_observed=now,
        last_observed=now,
    )

    triage = TriageRecord(
        id="tri-accept",
        triage_id="tri-accept",
        canonical_id="canon-accept",
        created_by=AgentType.TRIAGE.value,
        likelihood=2,
        impact=2,
        risk_score=4,
        risk_tier=RiskTier.LOW,
        treatment=TreatmentRecommendation.ACCEPT,
        rationale="Risk within tolerance",
        supporting_inputs={
            "treatment_metadata": {
                "compensating_controls": ["WAF block in place"],
                "waiver_justification": "Existing controls reduce likelihood to acceptable level.",
                "waiver_expiry_days": 45,
            }
        },
        residual_risk=ResidualRisk(risk_tier=RiskTier.LOW, rationale="Documented"),
        supersedes=None,
    )

    context = ApplicationContext(
        application="Payments API",
        business_service="Checkout",
        owner="Owner",
        owner_email="owner@example.com",
        environment="Prod",
        criticality="Tier1",
        completeness=ConfidenceLevel.HIGH,
    )
    enrichment = EnrichmentRecord(
        id="canon-accept",
        canonical_id="canon-accept",
        asset_id="asset-accept",
        application_context=context,
        exposure=ExposureSurface(),
        threat_signals=[],
    )

    canonical_repo = MemoryCanonicalRepository([canonical])
    triage_repo = MemoryTriageRepository({"canon-accept": triage})
    enrichment_repo = MemoryEnrichmentRepository({"canon-accept": enrichment})
    remediation_repo = MemoryRemediationUnitRepository()
    ticket_repo = MemoryTicketRepository()
    run_repo = MemoryRunEventRepository()
    jira_client = DummyJiraTicketClient()
    assets_client = DummyJiraAssetsClient()
    policy = DummyPolicy()
    treatment_repo = MemoryRiskTreatmentRepository()

    service = RemediationService(
        canonical_repo=canonical_repo,
        triage_repo=triage_repo,
        enrichment_repo=enrichment_repo,
        remediation_repo=remediation_repo,
        ticket_repo=ticket_repo,
        run_repo=run_repo,
        jira_ticket_client=jira_client,
        jira_assets_client=assets_client,
        policy=policy,
        treatment_repo=treatment_repo,
    )

    result = await service.plan_and_create(limit=5)
    await service.close()

    assert result.unit_count == 0
    assert result.ticket_count == 0
    assert "canon-accept" in result.follow_up_tasks
    stored_task = treatment_repo.tasks[0]
    assert RiskTreatmentWorkflow(stored_task.workflow) == RiskTreatmentWorkflow.WAIVER
    assert TreatmentRecommendation(stored_task.treatment) == TreatmentRecommendation.ACCEPT
    assert stored_task.compensating_controls == ["WAF block in place"]
    assert stored_task.justification.startswith("Existing controls")
    assert stored_task.proposed_expiry is not None
    assert stored_task.triage_reference == "tri-accept"
    assert canonical_repo.findings[0].treatment_follow_up_id == treatment_repo.tasks[0].task_id
    assert run_repo.events[-1].metrics["follow_up_accept"] == 1


@pytest.mark.asyncio
async def test_transfer_treatment_routes_to_transfer_follow_up():
    now = datetime.now(timezone.utc)
    canonical = CanonicalFinding(
        id="canon-transfer",
        canonical_id="canon-transfer",
        asset_id="asset-transfer",
        asset_identifiers=[AssetIdentifier(id_type=AssetIdentifierType.HOSTNAME, value="vm-transfer")],
        sources=[],
        vuln_key="CVE-2024-TRANSFER",
        severity="medium",
        risk_tier=RiskTier.MEDIUM,
        status=FindingLifecycleStatus.TRIAGED,
        remediation_bucket=RemediationBucket.CONFIG,
        description="Third-party risk",
        recommendations="Coordinate vendor remediation",
        first_observed=now,
        last_observed=now,
    )

    triage = TriageRecord(
        id="tri-transfer",
        triage_id="tri-transfer",
        canonical_id="canon-transfer",
        created_by=AgentType.TRIAGE.value,
        likelihood=2,
        impact=3,
        risk_score=6,
        risk_tier=RiskTier.MEDIUM,
        treatment=TreatmentRecommendation.TRANSFER,
        rationale="Vendor remediation required",
        supporting_inputs={
            "treatment_metadata": {
                "risk_transfer_notes": "Vendor XYZ owns patch timeline.",
                "waiver_justification": "Contractual responsibility lies with vendor.",
            }
        },
        residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM, rationale="Pending vendor"),
        supersedes=None,
    )

    enrichment = EnrichmentRecord(
        id="canon-transfer",
        canonical_id="canon-transfer",
        asset_id="asset-transfer",
        application_context=ApplicationContext(owner="Owner", application="Billing"),
        exposure=ExposureSurface(),
        threat_signals=[],
    )

    canonical_repo = MemoryCanonicalRepository([canonical])
    triage_repo = MemoryTriageRepository({"canon-transfer": triage})
    enrichment_repo = MemoryEnrichmentRepository({"canon-transfer": enrichment})
    remediation_repo = MemoryRemediationUnitRepository()
    ticket_repo = MemoryTicketRepository()
    run_repo = MemoryRunEventRepository()
    jira_client = DummyJiraTicketClient()
    assets_client = DummyJiraAssetsClient()
    policy = DummyPolicy()
    treatment_repo = MemoryRiskTreatmentRepository()

    service = RemediationService(
        canonical_repo=canonical_repo,
        triage_repo=triage_repo,
        enrichment_repo=enrichment_repo,
        remediation_repo=remediation_repo,
        ticket_repo=ticket_repo,
        run_repo=run_repo,
        jira_ticket_client=jira_client,
        jira_assets_client=assets_client,
        policy=policy,
        treatment_repo=treatment_repo,
    )

    result = await service.plan_and_create(limit=5)
    await service.close()

    assert result.unit_count == 0
    assert result.ticket_count == 0
    assert "canon-transfer" in result.follow_up_tasks
    stored_transfer = treatment_repo.tasks[0]
    assert RiskTreatmentWorkflow(stored_transfer.workflow) == RiskTreatmentWorkflow.RISK_TRANSFER
    assert TreatmentRecommendation(stored_transfer.treatment) == TreatmentRecommendation.TRANSFER
    assert stored_transfer.justification.startswith("Contractual responsibility")
    assert stored_transfer.proposed_expiry is None
    assert canonical_repo.findings[0].treatment_follow_up_id == treatment_repo.tasks[0].task_id
    assert run_repo.events[-1].metrics["follow_up_transfer"] == 1
