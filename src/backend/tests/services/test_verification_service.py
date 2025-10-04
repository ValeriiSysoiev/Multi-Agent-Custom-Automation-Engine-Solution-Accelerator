import os
import sys
from datetime import datetime, timezone, timedelta
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

azure_core_module = sys.modules.setdefault("azure.core", ModuleType("azure.core"))
azure_core_exceptions_module = sys.modules.setdefault("azure.core.exceptions", ModuleType("azure.core.exceptions"))


class _ResourceNotFoundError(Exception):
    pass


azure_core_exceptions_module.ResourceNotFoundError = _ResourceNotFoundError

from models.messages_kernel import (
    AgentType,
    CanonicalFinding,
    EvidenceRecord,
    EvidenceType,
    FindingLifecycleStatus,
    RemediationBucket,
    RemediationUnitRecord,
    RiskTier,
    TicketRecord,
    TicketStatus,
    VerificationStatus,
)
from repositories.canonical_finding_repository import CanonicalFindingRepository
from repositories.evidence_repository import EvidenceRepository
from repositories.remediation_unit_repository import RemediationUnitRepository
from repositories.run_event_repository import RunEventRepository
from repositories.ticket_repository import TicketRepository
from services.verification_service import VerificationService


class MemoryCanonicalRepository(CanonicalFindingRepository):
    def __init__(self, findings: Dict[str, CanonicalFinding]):
        self._store = findings

    async def get_by_canonical_id(self, canonical_id: str) -> Optional[CanonicalFinding]:
        return self._store.get(canonical_id)

    async def upsert_finding(self, finding: CanonicalFinding) -> CanonicalFinding:
        self._store[finding.canonical_id] = finding
        return finding


class MemoryTicketRepository(TicketRepository):
    def __init__(self, tickets: List[TicketRecord]):
        self._tickets = tickets

    async def list_pending_verification(self, limit: int = 50) -> List[TicketRecord]:
        return [t for t in self._tickets if t.status == TicketStatus.RESOLVED][:limit]

    async def upsert_ticket(self, record: TicketRecord) -> TicketRecord:
        for idx, ticket in enumerate(self._tickets):
            if ticket.ticket_id == record.ticket_id:
                self._tickets[idx] = record
                return record
        self._tickets.append(record)
        return record


class MemoryEvidenceRepository(EvidenceRepository):
    def __init__(self, evidence: List[EvidenceRecord]):
        self._evidence = evidence

    async def list_for_ticket(self, ticket_id: str) -> List[EvidenceRecord]:
        return [e for e in self._evidence if e.ticket_id == ticket_id]

    async def upsert_evidence(self, record: EvidenceRecord) -> EvidenceRecord:
        for idx, ev in enumerate(self._evidence):
            if ev.evidence_id == record.evidence_id:
                self._evidence[idx] = record
                return record
        self._evidence.append(record)
        return record


class MemoryRemediationUnitRepository(RemediationUnitRepository):
    def __init__(self, units: Dict[str, RemediationUnitRecord]):
        self._units = units

    async def get_unit(self, remediation_unit_id: str) -> Optional[RemediationUnitRecord]:
        return self._units.get(remediation_unit_id)

    async def upsert_unit(self, record: RemediationUnitRecord) -> RemediationUnitRecord:
        self._units[record.remediation_unit_id] = record
        return record


class MemoryRunEventRepository(RunEventRepository):
    def __init__(self):
        self.events = []

    async def upsert_event(self, record):
        self.events.append(record)
        return record


class DummyJiraClient:
    def __init__(self):
        self.marked: List[tuple[str, str]] = []
        self.reopened: List[tuple[str, Optional[str]]] = []

    async def mark_ticket_verified(self, issue_key: str, evidence_summary: str) -> None:
        self.marked.append((issue_key, evidence_summary))

    async def reopen_ticket(self, issue_key: str, reason: Optional[str] = None) -> None:
        self.reopened.append((issue_key, reason))

    async def close(self) -> None:
        return


def _ticket(remediation_unit_id: str) -> TicketRecord:
    now = datetime.now(timezone.utc)
    return TicketRecord(
        id="t1",
        ticket_id="t1",
        remediation_unit_id=remediation_unit_id,
        external_key="CYB-1",
        url="https://jira/browse/CYB-1",
        status=TicketStatus.RESOLVED,
        opened_at=now - timedelta(days=5),
        resolved_at=now - timedelta(hours=12),
    )


@pytest.mark.asyncio
async def test_verification_service_marks_ticket_verified():
    canonical = CanonicalFinding(
        id="canon-1",
        canonical_id="canon-1",
        asset_id="asset-1",
        asset_identifiers=[],
        sources=[],
        vuln_key="CVE-2024-0001",
        risk_tier=RiskTier.CRITICAL,
        status=FindingLifecycleStatus.IN_REMEDIATION,
        remediation_bucket=RemediationBucket.PATCH,
    )
    unit = RemediationUnitRecord(
        id="ru-1",
        remediation_unit_id="ru-1",
        bucket=RemediationBucket.PATCH,
        risk_tier=RiskTier.CRITICAL,
        canonical_ids=["canon-1"],
    )
    ticket = _ticket("ru-1")

    evidence = EvidenceRecord(
        id="ev-1",
        evidence_id="ev-1",
        canonical_id="canon-1",
        remediation_unit_id="ru-1",
        ticket_id="t1",
        evidence_type=EvidenceType.TARGETED_RESCAN,
        source_uri=None,
        submitted_by="test",
        captured_at=datetime.now(timezone.utc),
    )
    evidence_2 = EvidenceRecord(
        id="ev-2",
        evidence_id="ev-2",
        canonical_id="canon-1",
        remediation_unit_id="ru-1",
        ticket_id="t1",
        evidence_type=EvidenceType.CONFIG_PROOF,
        source_uri=None,
        submitted_by="test",
        captured_at=datetime.now(timezone.utc),
    )

    jira_client = DummyJiraClient()
    service = VerificationService(
        ticket_repo=MemoryTicketRepository([ticket]),
        evidence_repo=MemoryEvidenceRepository([evidence, evidence_2]),
        remediation_repo=MemoryRemediationUnitRepository({"ru-1": unit}),
        canonical_repo=MemoryCanonicalRepository({"canon-1": canonical}),
        run_repo=MemoryRunEventRepository(),
        jira_client=jira_client,
    )

    metrics = await service.process_pending_tickets(limit=10)
    await service.close()

    assert metrics["verified"] == 1
    updated_ticket = service._ticket_repo._tickets[0]
    assert updated_ticket.status == TicketStatus.VERIFIED
    assert service._remediation_repo._units["ru-1"].status == FindingLifecycleStatus.VERIFIED
    assert service._canonical_repo._store["canon-1"].status == FindingLifecycleStatus.VERIFIED
    assert service._evidence_repo._evidence[0].verification_status == VerificationStatus.ACCEPTED
    assert jira_client.marked and jira_client.marked[0][0] == "CYB-1"
    assert "Evidence accepted" in jira_client.marked[0][1]


@pytest.mark.asyncio
async def test_verification_service_reopens_when_insufficient_evidence():
    canonical = CanonicalFinding(
        id="canon-1",
        canonical_id="canon-1",
        asset_id="asset-1",
        asset_identifiers=[],
        sources=[],
        vuln_key="CVE-2024-0001",
        risk_tier=RiskTier.CRITICAL,
        status=FindingLifecycleStatus.IN_REMEDIATION,
        remediation_bucket=RemediationBucket.PATCH,
    )
    unit = RemediationUnitRecord(
        id="ru-1",
        remediation_unit_id="ru-1",
        bucket=RemediationBucket.PATCH,
        risk_tier=RiskTier.CRITICAL,
        canonical_ids=["canon-1"],
    )
    ticket = _ticket("ru-1")
    evidence = EvidenceRecord(
        id="ev-1",
        evidence_id="ev-1",
        canonical_id="canon-1",
        remediation_unit_id="ru-1",
        ticket_id="t1",
        evidence_type=EvidenceType.CONFIG_PROOF,
        source_uri=None,
        submitted_by="test",
        captured_at=datetime.now(timezone.utc),
    )
    jira_client = DummyJiraClient()
    service = VerificationService(
        ticket_repo=MemoryTicketRepository([ticket]),
        evidence_repo=MemoryEvidenceRepository([evidence]),
        remediation_repo=MemoryRemediationUnitRepository({"ru-1": unit}),
        canonical_repo=MemoryCanonicalRepository({"canon-1": canonical}),
        run_repo=MemoryRunEventRepository(),
        jira_client=jira_client,
    )

    metrics = await service.process_pending_tickets(limit=10)
    await service.close()

    assert metrics["reopened"] == 1
    assert service._ticket_repo._tickets[0].status == TicketStatus.REOPENED
    assert service._evidence_repo._evidence[0].verification_status == VerificationStatus.REJECTED
    assert jira_client.reopened and jira_client.reopened[0][0] == "CYB-1"
    assert jira_client.reopened[0][1]
