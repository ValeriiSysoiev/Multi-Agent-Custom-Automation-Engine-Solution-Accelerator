import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example-openai")
os.environ.setdefault("COSMOSDB_ENDPOINT", "https://cosmos.test")
os.environ.setdefault("COSMOSDB_DATABASE", "test-db")
os.environ.setdefault("AZURE_AI_SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("AZURE_AI_RESOURCE_GROUP", "rg-test")
os.environ.setdefault("AZURE_AI_PROJECT_NAME", "project-test")
os.environ.setdefault("AZURE_AI_AGENT_ENDPOINT", "https://agents.example.com")
os.environ.setdefault("KEYVAULT_URI", "https://kv.test")

from types import ModuleType
from pydantic import BaseModel, Field as PydanticField

if "semantic_kernel" not in sys.modules:
    semantic_kernel_module = ModuleType("semantic_kernel")
    sys.modules["semantic_kernel"] = semantic_kernel_module
    kernel_pydantic_module = ModuleType("semantic_kernel.kernel_pydantic")
    sys.modules["semantic_kernel.kernel_pydantic"] = kernel_pydantic_module
    semantic_kernel_module.kernel_pydantic = kernel_pydantic_module
    class _KernelBaseModel(BaseModel):
        class Config:
            arbitrary_types_allowed = True
            use_enum_values = True
    kernel_pydantic_module.KernelBaseModel = _KernelBaseModel
    kernel_pydantic_module.Field = PydanticField
else:
    semantic_kernel_module = sys.modules["semantic_kernel"]
    if "kernel_pydantic" not in semantic_kernel_module.__dict__:
        kernel_pydantic_module = ModuleType("semantic_kernel.kernel_pydantic")
        sys.modules["semantic_kernel.kernel_pydantic"] = kernel_pydantic_module
        semantic_kernel_module.kernel_pydantic = kernel_pydantic_module
        kernel_pydantic_module.KernelBaseModel = BaseModel
        kernel_pydantic_module.Field = PydanticField

semantic_kernel_kernel_module = sys.modules.setdefault("semantic_kernel.kernel", ModuleType("semantic_kernel.kernel"))
semantic_kernel_kernel_module.Kernel = object

if "azure" not in sys.modules:
    azure_module = ModuleType("azure")
    sys.modules["azure"] = azure_module

azure_ai_module = sys.modules.setdefault("azure.ai", ModuleType("azure.ai"))
azure_ai_projects_module = sys.modules.setdefault("azure.ai.projects", ModuleType("azure.ai.projects"))
azure_ai_projects_aio_module = sys.modules.setdefault("azure.ai.projects.aio", ModuleType("azure.ai.projects.aio"))


class _DummyAIProjectClient:
    pass


azure_ai_projects_aio_module.AIProjectClient = _DummyAIProjectClient

azure_keyvault_module = sys.modules.setdefault("azure.keyvault", ModuleType("azure.keyvault"))
azure_keyvault_secrets_module = sys.modules.setdefault("azure.keyvault.secrets", ModuleType("azure.keyvault.secrets"))
azure_keyvault_secrets_aio_module = sys.modules.setdefault("azure.keyvault.secrets.aio", ModuleType("azure.keyvault.secrets.aio"))

class _DummySecretClient:
    async def close(self) -> None:
        return

azure_keyvault_secrets_aio_module.SecretClient = _DummySecretClient

azure_identity_module = sys.modules.setdefault("azure.identity", ModuleType("azure.identity"))
azure_identity_aio_module = sys.modules.setdefault("azure.identity.aio", ModuleType("azure.identity.aio"))

class _DummyCredential:
    async def close(self) -> None:
        return

azure_identity_module.ManagedIdentityCredential = _DummyCredential
azure_identity_module.DefaultAzureCredential = _DummyCredential
azure_identity_aio_module.ManagedIdentityCredential = _DummyCredential
azure_identity_aio_module.DefaultAzureCredential = _DummyCredential

azure_cosmos_module = sys.modules.setdefault("azure.cosmos", ModuleType("azure.cosmos"))
azure_cosmos_aio_module = sys.modules.setdefault("azure.cosmos.aio", ModuleType("azure.cosmos.aio"))
azure_cosmos_exceptions_module = sys.modules.setdefault("azure.cosmos.exceptions", ModuleType("azure.cosmos.exceptions"))


class _CosmosNotFound(Exception):
    pass


azure_cosmos_exceptions_module.CosmosResourceNotFoundError = _CosmosNotFound


class _DummyContainerProxy:
    async def upsert_item(self, *args, **kwargs):
        return {}


azure_cosmos_aio_module.ContainerProxy = _DummyContainerProxy


class _DummyCosmosClient:
    def get_database_client(self, *args, **kwargs):
        raise RuntimeError("Cosmos access not expected in unit tests")


azure_cosmos_aio_module.CosmosClient = _DummyCosmosClient

azure_core_module = sys.modules.setdefault("azure.core", ModuleType("azure.core"))
azure_core_exceptions_module = sys.modules.setdefault("azure.core.exceptions", ModuleType("azure.core.exceptions"))


class _ResourceNotFoundError(Exception):
    pass


azure_core_exceptions_module.ResourceNotFoundError = _ResourceNotFoundError

from models.messages_kernel import (
    AgentType,
    CompensatingControl,
    RemediationBucket,
    RemediationUnitRecord,
    ResidualRisk,
    RiskTier,
    WaiverApproval,
    WaiverRecord,
    WaiverStatus,
)
from repositories.remediation_unit_repository import RemediationUnitRepository
from repositories.run_event_repository import RunEventRepository
from repositories.waiver_repository import WaiverRepository
from services.jira_ticket_client import JiraTicketResult
from services.waiver_service import WaiverService


class MemoryWaiverRepository(WaiverRepository):
    def __init__(self):
        self.records: Dict[str, WaiverRecord] = {}

    async def upsert_waiver(self, record: WaiverRecord) -> WaiverRecord:
        self.records[record.waiver_id] = record
        return record

    async def get_by_id(self, waiver_id: str) -> Optional[WaiverRecord]:
        return self.records.get(waiver_id)

    async def list_active(self, limit: int = 100) -> List[WaiverRecord]:
        return [record for record in self.records.values() if record.status != WaiverStatus.EXPIRED][:limit]


class MemoryRemediationUnitRepository(RemediationUnitRepository):
    def __init__(self, units: Dict[str, RemediationUnitRecord]):
        self._units = units

    async def get_unit(self, remediation_unit_id: str) -> Optional[RemediationUnitRecord]:
        return self._units.get(remediation_unit_id)


class MemoryRunEventRepository(RunEventRepository):
    def __init__(self):
        self.events = []

    async def upsert_event(self, record):
        self.events.append(record)
        return record


class DummyJiraClient:
    def __init__(self):
        self.created = []
        self.status_updates = []

    async def create_waiver_ticket(self, summary, description, expiry, status, custom_fields=None):
        self.created.append((summary, description, expiry, status, custom_fields))
        return JiraTicketResult(issue_id="20000", issue_key="CYB-W1", self_url="", browse_url="")

    async def set_waiver_status(self, issue_key: str, status: str, expiry=None):
        self.status_updates.append((issue_key, status, expiry))

    async def close(self) -> None:
        return


@pytest.mark.asyncio
async def test_request_waiver_creates_record_and_jira_ticket():
    now = datetime.now(timezone.utc)
    unit = RemediationUnitRecord(
        id="ru-1",
        remediation_unit_id="ru-1",
        bucket=RemediationBucket.PATCH,
        risk_tier=RiskTier.HIGH,
        canonical_ids=["canon-1"],
    )
    waiver_repo = MemoryWaiverRepository()
    jira_client = DummyJiraClient()
    service = WaiverService(
        waiver_repo=waiver_repo,
        remediation_repo=MemoryRemediationUnitRepository({"ru-1": unit}),
        run_repo=MemoryRunEventRepository(),
        jira_client=jira_client,
    )

    record = await service.request_waiver(
        remediation_unit=unit,
        requested_by="owner@example.com",
        justification="Vendor fix unavailable",
        controls=[CompensatingControl(control_type="waf", description="WAF block")],
        residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM, rationale="WAF coverage"),
        expiry=now + timedelta(days=30),
    )

    await service.close()

    assert record.status == WaiverStatus.REQUESTED
    assert record.waiver_id in waiver_repo.records
    assert jira_client.created
    assert len(jira_client.created) == 1
    assert jira_client.created[0][0].startswith("Waiver for")
    assert record.ticket_key == "CYB-W1"
    assert record.ticket_id == "20000"
    assert record.approvals == []


@pytest.mark.asyncio
async def test_approve_waiver_updates_status():
    now = datetime.now(timezone.utc)
    waiver_repo = MemoryWaiverRepository()
    record = WaiverRecord(
        id="wa-1",
        waiver_id="wa-1",
        remediation_unit_id="ru-1",
        risk_tier=RiskTier.HIGH,
        status=WaiverStatus.REQUESTED,
        requested_by="user",
        requested_at=now,
        justification="Test",
        compensating_controls=[],
        residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM),
        expires_at=now + timedelta(days=10),
        renewal_count=0,
        verification_plan=None,
        ticket_key="CYB-W1",
        ticket_id="20000",
    )
    waiver_repo.records["wa-1"] = record
    jira_client = DummyJiraClient()
    service = WaiverService(
        waiver_repo=waiver_repo,
        remediation_repo=MemoryRemediationUnitRepository({}),
        run_repo=MemoryRunEventRepository(),
        jira_client=jira_client,
    )

    await service.approve_waiver("wa-1", approver="Sec Lead", role="security_lead")
    assert waiver_repo.records["wa-1"].status == WaiverStatus.REQUESTED
    await service.approve_waiver("wa-1", approver="Platform Lead", role="platform_lead")
    await service.approve_waiver("wa-1", approver="Director", role="security_director")
    approved = await service.approve_waiver("wa-1", approver="Product Director", role="product_director", notes="OK")
    await service.close()

    assert approved.status == WaiverStatus.APPROVED
    assert set(approved.approved_by or []) == {
        "Sec Lead",
        "Platform Lead",
        "Director",
        "Product Director",
    }
    assert approved.verification_plan == "OK"
    assert jira_client.status_updates and jira_client.status_updates[0][1] == "Approved"


@pytest.mark.asyncio
async def test_expire_waivers_sets_status_and_logs_event():
    now = datetime.now(timezone.utc)
    waiver_repo = MemoryWaiverRepository()
    waiver_repo.records["wa-old"] = WaiverRecord(
        id="wa-old",
        waiver_id="wa-old",
        remediation_unit_id="ru-1",
        risk_tier=RiskTier.MEDIUM,
        status=WaiverStatus.APPROVED,
        requested_by="user",
        requested_at=now - timedelta(days=40),
        justification="Old",
        compensating_controls=[],
        residual_risk=ResidualRisk(risk_tier=RiskTier.LOW),
        expires_at=now - timedelta(days=1),
        renewal_count=0,
        verification_plan=None,
        ticket_key="CYB-W1",
        ticket_id="20000",
    )

    run_repo = MemoryRunEventRepository()
    jira_client = DummyJiraClient()
    service = WaiverService(
        waiver_repo=waiver_repo,
        remediation_repo=MemoryRemediationUnitRepository({}),
        run_repo=run_repo,
        jira_client=jira_client,
    )

    expired = await service.expire_waivers()
    await service.close()

    assert expired == 1
    assert waiver_repo.records["wa-old"].status == WaiverStatus.EXPIRED
    assert run_repo.events
    assert jira_client.status_updates and jira_client.status_updates[0][1] == "Expired"


@pytest.mark.asyncio
async def test_request_waiver_enforces_control_minimum():
    now = datetime.now(timezone.utc)
    unit = RemediationUnitRecord(
        id="ru-crit",
        remediation_unit_id="ru-crit",
        bucket=RemediationBucket.CONFIG,
        risk_tier=RiskTier.CRITICAL,
        canonical_ids=["canon"]
    )
    waiver_repo = MemoryWaiverRepository()
    jira_client = DummyJiraClient()
    service = WaiverService(
        waiver_repo=waiver_repo,
        remediation_repo=MemoryRemediationUnitRepository({"ru-crit": unit}),
        run_repo=MemoryRunEventRepository(),
        jira_client=jira_client,
    )

    with pytest.raises(ValueError):
        await service.request_waiver(
            remediation_unit=unit,
            requested_by="owner@example.com",
            justification="Need time",
            controls=[CompensatingControl(control_type="manual review", description="")],
            residual_risk=ResidualRisk(risk_tier=RiskTier.CRITICAL),
            expiry=now + timedelta(days=10),
        )

    await service.close()


@pytest.mark.asyncio
async def test_approve_waiver_rejects_invalid_role():
    now = datetime.now(timezone.utc)
    waiver_repo = MemoryWaiverRepository()
    record = WaiverRecord(
        id="wa-2",
        waiver_id="wa-2",
        remediation_unit_id="ru-1",
        risk_tier=RiskTier.HIGH,
        status=WaiverStatus.REQUESTED,
        requested_by="user",
        requested_at=now,
        justification="Test",
        compensating_controls=[],
        residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM),
        expires_at=now + timedelta(days=5),
        renewal_count=0,
        verification_plan=None,
        ticket_key="CYB-W1",
        ticket_id="20000",
    )
    waiver_repo.records["wa-2"] = record
    service = WaiverService(
        waiver_repo=waiver_repo,
        remediation_repo=MemoryRemediationUnitRepository({}),
        run_repo=MemoryRunEventRepository(),
        jira_client=DummyJiraClient(),
    )

    with pytest.raises(ValueError):
        await service.approve_waiver("wa-2", approver="Random", role="intern")

    await service.close()


@pytest.mark.asyncio
async def test_monitor_waivers_tracks_pending_and_due():
    now = datetime.now(timezone.utc)
    waiver_repo = MemoryWaiverRepository()

    def _make_waiver(
        waiver_id: str,
        status: WaiverStatus,
        expires_delta: Optional[int],
        approvals: Optional[List[str]] = None,
        risk_tier: RiskTier = RiskTier.HIGH,
    ) -> WaiverRecord:
        record = WaiverRecord(
            id=waiver_id,
            waiver_id=waiver_id,
            remediation_unit_id=f"ru-{waiver_id}",
            risk_tier=risk_tier,
            status=status,
            requested_by="user",
            requested_at=now - timedelta(days=2),
            justification="Test",
            compensating_controls=[CompensatingControl(control_type="waf", description="WAF block")],
            residual_risk=ResidualRisk(risk_tier=risk_tier),
            expires_at=(now + timedelta(days=expires_delta)) if expires_delta is not None else None,
            renewal_count=0,
            verification_plan=None,
        )
        if approvals:
            record.approvals = [
                WaiverApproval(approver=f"approver-{role}", role=role, approved_at=now)
                for role in approvals
            ]
            record.approved_by = [approval.approver for approval in record.approvals]
        waiver_repo.records[waiver_id] = record
        return record

    _make_waiver("wa-request", WaiverStatus.REQUESTED, expires_delta=2, approvals=[])
    _make_waiver("wa-approved", WaiverStatus.APPROVED, expires_delta=10, approvals=[
        "security_lead",
        "platform_lead",
        "security_director",
        "product_director",
    ])
    _make_waiver("wa-overdue", WaiverStatus.APPROVED, expires_delta=-1)
    _make_waiver("wa-missing", WaiverStatus.APPROVED, expires_delta=None)

    run_repo = MemoryRunEventRepository()
    service = WaiverService(
        waiver_repo=waiver_repo,
        remediation_repo=MemoryRemediationUnitRepository({}),
        run_repo=run_repo,
        jira_client=DummyJiraClient(),
    )

    metrics = await service.monitor_waivers(renewal_windows=(7, 3, 1), limit=10)
    await service.close()

    assert metrics["total_active"] == 4
    assert metrics["pending_decision"] == 1
    assert metrics["due_within_7d"] == 1
    assert metrics["due_within_3d"] == 1
    assert metrics["due_within_1d"] == 0
    assert metrics["overdue"] == 1
    assert metrics["missing_expiry"] == 1
    assert run_repo.events, "monitor_waivers should emit a run event"
    event = run_repo.events[-1]
    assert event.run_type == "waiver_monitor"
    assert event.metrics.get("renewal_windows") == [7, 3, 1]
