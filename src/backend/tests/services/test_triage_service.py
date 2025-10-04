import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

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
os.environ.setdefault("AZURE_OPENAI_API_VERSION", "2024-11-20")
os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
os.environ.setdefault("AZURE_AI_SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("AZURE_AI_RESOURCE_GROUP", "rg-test")
os.environ.setdefault("AZURE_AI_PROJECT_NAME", "proj-test")
os.environ.setdefault("AZURE_AI_AGENT_ENDPOINT", "https://agents.example.com")
os.environ.setdefault("COSMOSDB_ENDPOINT", "https://cosmos.test")
os.environ.setdefault("COSMOSDB_DATABASE", "test-db")

if "azure" not in sys.modules:
    azure_module = ModuleType("azure")
    sys.modules["azure"] = azure_module

azure_ai_module = sys.modules.setdefault("azure.ai", ModuleType("azure.ai"))
azure_ai_projects_module = sys.modules.setdefault("azure.ai.projects", ModuleType("azure.ai.projects"))
azure_ai_projects_aio_module = sys.modules.setdefault("azure.ai.projects.aio", ModuleType("azure.ai.projects.aio"))


class _DummyAIProjectClient:  # pragma: no cover - simple stub
    def __init__(self, *args, **kwargs):
        return


azure_ai_projects_aio_module.AIProjectClient = _DummyAIProjectClient

azure_cosmos_module = sys.modules.setdefault("azure.cosmos", ModuleType("azure.cosmos"))
azure_cosmos_aio_module = sys.modules.setdefault("azure.cosmos.aio", ModuleType("azure.cosmos.aio"))


class _CosmosNotFound(Exception):
    pass


azure_cosmos_exceptions_module = sys.modules.setdefault(
    "azure.cosmos.exceptions", ModuleType("azure.cosmos.exceptions")
)
azure_cosmos_exceptions_module.CosmosResourceNotFoundError = _CosmosNotFound


class _DummyCosmosClient:  # pragma: no cover - simple stub
    def __init__(self, *args, **kwargs):
        return

    def get_database_client(self, *args, **kwargs):
        raise RuntimeError("Cosmos access not expected in unit tests")


azure_cosmos_aio_module.CosmosClient = _DummyCosmosClient


class _DummyContainerProxy:  # pragma: no cover - simple stub
    async def upsert_item(self, *args, **kwargs):
        raise RuntimeError("Cosmos access not expected in unit tests")


azure_cosmos_aio_module.ContainerProxy = _DummyContainerProxy

azure_keyvault_module = sys.modules.setdefault("azure.keyvault", ModuleType("azure.keyvault"))
azure_keyvault_secrets_module = sys.modules.setdefault("azure.keyvault.secrets", ModuleType("azure.keyvault.secrets"))
azure_keyvault_secrets_aio_module = sys.modules.setdefault(
    "azure.keyvault.secrets.aio", ModuleType("azure.keyvault.secrets.aio")
)


class _DummySecretClient:  # pragma: no cover - simple stub
    def __init__(self, *args, **kwargs):
        return

    async def close(self) -> None:
        return


azure_keyvault_secrets_aio_module.SecretClient = _DummySecretClient

azure_identity_module = sys.modules.setdefault("azure.identity", ModuleType("azure.identity"))
azure_identity_aio_module = sys.modules.setdefault("azure.identity.aio", ModuleType("azure.identity.aio"))


class _DummyCredential:  # pragma: no cover - simple stub
    async def close(self) -> None:
        return

    async def get_token(self, *args, **kwargs):
        raise RuntimeError("Token acquisition not expected in unit tests")


azure_identity_aio_module.ManagedIdentityCredential = _DummyCredential
azure_identity_aio_module.DefaultAzureCredential = _DummyCredential


class _SyncDummyCredential:  # pragma: no cover - simple stub
    def __init__(self, *args, **kwargs):
        return


azure_identity_module.ManagedIdentityCredential = _SyncDummyCredential
azure_identity_module.DefaultAzureCredential = _SyncDummyCredential

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
    kernel_pydantic_module = sys.modules.get("semantic_kernel.kernel_pydantic")
    if kernel_pydantic_module is None:
        kernel_pydantic_module = ModuleType("semantic_kernel.kernel_pydantic")
        sys.modules["semantic_kernel.kernel_pydantic"] = kernel_pydantic_module
        semantic_kernel_module.kernel_pydantic = kernel_pydantic_module

    class _KernelBaseModel(BaseModel):
        class Config:
            arbitrary_types_allowed = True
            use_enum_values = True

    kernel_pydantic_module.KernelBaseModel = _KernelBaseModel
    kernel_pydantic_module.Field = PydanticField

kernel_module = sys.modules.setdefault("semantic_kernel.kernel", ModuleType("semantic_kernel.kernel"))
semantic_kernel_module.kernel = kernel_module


class _Kernel:  # pragma: no cover - minimal stub
    pass


kernel_module.Kernel = _Kernel

from models.messages_kernel import (
    ApplicationContext,
    AssetIdentifier,
    AssetIdentifierType,
    CanonicalFinding,
    ConfidenceLevel,
    EnrichmentRecord,
    ExposureSurface,
    FindingLifecycleStatus,
    OwnershipStatus,
    RiskTier,
    SourceReference,
    ThreatSignal,
    TreatmentRecommendation,
    TriageRecord,
)
from services.triage_models import TriageLLMResponse
from services.triage_service import TriageService


class MemoryCanonicalRepository:
    def __init__(self, finding: CanonicalFinding) -> None:
        self.finding = finding
        self.upserts: List[CanonicalFinding] = []

    async def list_pending_triage(self, limit: int = 100) -> List[CanonicalFinding]:
        return [self.finding][:limit]

    async def upsert_finding(self, finding: CanonicalFinding) -> CanonicalFinding:
        self.finding = finding
        self.upserts.append(finding)
        return finding

    async def get_by_id(self, canonical_id: str, asset_id: str) -> Optional[CanonicalFinding]:
        if self.finding.canonical_id == canonical_id and self.finding.asset_id == asset_id:
            return self.finding
        return None


class MemoryEnrichmentRepository:
    def __init__(self, record: EnrichmentRecord) -> None:
        self.record = record

    async def get_enrichment(self, canonical_id: str, asset_id: str) -> Optional[EnrichmentRecord]:
        if self.record.canonical_id == canonical_id and self.record.asset_id == asset_id:
            return self.record
        return None


class MemoryTriageRepository:
    def __init__(self) -> None:
        self.records: List[TriageRecord] = []

    async def upsert_record(self, record: TriageRecord) -> TriageRecord:
        self.records.append(record)
        return record

    async def get_latest(self, canonical_id: str) -> Optional[TriageRecord]:
        for record in reversed(self.records):
            if record.canonical_id == canonical_id:
                return record
        return None


class MemoryRunEventRepository:
    def __init__(self) -> None:
        self.events: List[Dict[str, object]] = []

    async def upsert_event(self, record) -> object:  # pragma: no cover - simple container
        self.events.append(record)
        return record


@pytest.mark.asyncio
async def test_triage_service_scores_and_persists_records():
    identifier = AssetIdentifier(
        id_type=AssetIdentifierType.CLOUD_RESOURCE_ID,
        value="/subscriptions/123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/app1",
        source="defender",
    )
    source = SourceReference(
        scanner_id="defender",
        external_id="ext-1",
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
        severity="high",
    )
    canonical = CanonicalFinding(
        id="canon-1",
        canonical_id="canon-1",
        asset_id="asset-1",
        asset_identifiers=[identifier],
        sources=[source],
        vuln_key="CVE-2024-0001",
        severity="high",
        risk_tier=RiskTier.HIGH,
        status=FindingLifecycleStatus.OPEN,
        description="Sample vuln",
        recommendations="Patch immediately",
        first_observed=datetime.now(timezone.utc),
        last_observed=datetime.now(timezone.utc),
    )
    canonical.ownership_status = OwnershipStatus.CONFIRMED

    context = ApplicationContext(
        application="Payments API",
        business_service="Checkout",
        owner="Owner",
        environment="Prod",
        criticality="Tier0",
        completeness=ConfidenceLevel.HIGH,
        tags={"application_data_classification": "Regulated"},
    )
    exposure = ExposureSurface(
        internet_facing=True,
        authentication_required=False,
        network_segment="DMZ",
        control_coverage={"waf": True, "edr": True},
    )
    threat_signal = ThreatSignal(source="cisa", signal_type="known_exploited")
    enrichment = EnrichmentRecord(
        id="canon-1",
        canonical_id="canon-1",
        asset_id="asset-1",
        application_context=context,
        exposure=exposure,
        threat_signals=[threat_signal],
    )

    canonical_repo = MemoryCanonicalRepository(canonical)
    enrichment_repo = MemoryEnrichmentRepository(enrichment)
    triage_repo = MemoryTriageRepository()
    run_repo = MemoryRunEventRepository()

    service = TriageService(
        canonical_repo=canonical_repo,
        enrichment_repo=enrichment_repo,
        triage_repo=triage_repo,
        run_repo=run_repo,
        enable_llm=False,
    )

    try:
        records = await service.triage_findings(limit=5)
    finally:
        await service.close()

    assert len(records) == 1
    triaged = records[0]
    assert triaged.risk_tier == RiskTier.CRITICAL
    assert triaged.likelihood >= 4
    assert canonical_repo.finding.status == FindingLifecycleStatus.TRIAGED
    assert triage_repo.records[0].supporting_inputs["unacceptable_conditions"]
    assert run_repo.events  # run events captured


@pytest.mark.asyncio
async def test_triage_enforces_active_exploitation_override():
    signal = ThreatSignal(source="kev", signal_type="Known_Exploited")
    canonical = CanonicalFinding(
        id="canon-override",
        canonical_id="canon-override",
        asset_id="asset-override",
        asset_identifiers=[
            AssetIdentifier(
                id_type=AssetIdentifierType.CLOUD_RESOURCE_ID,
                value="/subscriptions/123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/app2",
                source="defender",
            )
        ],
        sources=[
            SourceReference(
                scanner_id="defender",
                external_id="ext-override",
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
                severity="medium",
            )
        ],
        vuln_key="CVE-2024-1000",
        severity="medium",
        risk_tier=RiskTier.MEDIUM,
        status=FindingLifecycleStatus.OPEN,
        description="Override test",
        recommendations="Investigate",
        first_observed=datetime.now(timezone.utc),
        last_observed=datetime.now(timezone.utc),
    )
    canonical.ownership_status = OwnershipStatus.CONFIRMED

    enrichment = EnrichmentRecord(
        id="canon-override",
        canonical_id="canon-override",
        asset_id="asset-override",
        application_context=ApplicationContext(
            application="Checkout Gateway",
            business_service="Customer Checkout",
            owner="Owner",
            owner_email="owner@example.com",
            environment="Prod",
            criticality="Tier0",
            completeness=ConfidenceLevel.HIGH,
            tags={"portfolio": "payments"},
        ),
        exposure=ExposureSurface(
            internet_facing=True,
            authentication_required=True,
            network_segment="DMZ",
            control_coverage={"waf": True},
        ),
        threat_signals=[signal],
    )

    canonical_repo = MemoryCanonicalRepository(canonical)
    enrichment_repo = MemoryEnrichmentRepository(enrichment)
    triage_repo = MemoryTriageRepository()
    run_repo = MemoryRunEventRepository()

    service = TriageService(
        canonical_repo=canonical_repo,
        enrichment_repo=enrichment_repo,
        triage_repo=triage_repo,
        run_repo=run_repo,
        enable_llm=False,
    )

    try:
        record = await service.triage_single(canonical)
    finally:
        await service.close()

    assert record is not None
    assert record.risk_tier == RiskTier.CRITICAL
    assert canonical_repo.finding.risk_tier == RiskTier.CRITICAL
    assert triage_repo.records, "triage record should be persisted"


@pytest.mark.asyncio
async def test_triage_applies_llm_adjustments(monkeypatch):
    canonical = CanonicalFinding(
        id="canon-llm",
        canonical_id="canon-llm",
        asset_id="asset-llm",
        asset_identifiers=[
            AssetIdentifier(
                id_type=AssetIdentifierType.HOSTNAME,
                value="internal.api.local",
                source="qualys",
            )
        ],
        sources=[
            SourceReference(
                scanner_id="qualys",
                external_id="ext-llm",
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
                severity="medium",
            )
        ],
        vuln_key="CVE-2024-2000",
        severity="medium",
        risk_tier=RiskTier.MEDIUM,
        status=FindingLifecycleStatus.OPEN,
        description="LLM adjustment test",
        recommendations="Assess",
        first_observed=datetime.now(timezone.utc),
        last_observed=datetime.now(timezone.utc),
    )
    canonical.ownership_status = OwnershipStatus.CONFIRMED

    enrichment = EnrichmentRecord(
        id="canon-llm",
        canonical_id="canon-llm",
        asset_id="asset-llm",
        application_context=ApplicationContext(
            application="Internal Reporting",
            business_service="Analytics",
            owner="Owner",
            owner_email="owner@example.com",
            environment="Dev",
            criticality="Tier2",
            completeness=ConfidenceLevel.HIGH,
        ),
        exposure=ExposureSurface(
            internet_facing=False,
            authentication_required=True,
            network_segment="Internal",
        ),
        threat_signals=[],
    )

    canonical_repo = MemoryCanonicalRepository(canonical)
    enrichment_repo = MemoryEnrichmentRepository(enrichment)
    triage_repo = MemoryTriageRepository()
    run_repo = MemoryRunEventRepository()

    service = TriageService(
        canonical_repo=canonical_repo,
        enrichment_repo=enrichment_repo,
        triage_repo=triage_repo,
        run_repo=run_repo,
        enable_llm=True,
    )

    async def fake_llm(self, finding, enrichment_record, risk_computation):  # pragma: no cover - stub
        assert finding.canonical_id == "canon-llm"
        return TriageLLMResponse(
            likelihood=5,
            impact=4,
            risk_score=20,
            risk_tier=RiskTier.HIGH,
            treatment=TreatmentRecommendation.AVOID,
            rationale="Escalate due to regulatory concern.",
            residual_risk_rationale="Residual risk acceptable after code hardening.",
            unacceptable_conditions=["regulatory_non_compliance"],
        )

    service._maybe_invoke_llm = fake_llm.__get__(service, TriageService)  # bind to instance

    try:
        record = await service.triage_single(canonical)
    finally:
        await service.close()

    assert record is not None
    assert record.risk_tier == RiskTier.HIGH
    assert record.likelihood == 5
    assert record.impact == 4
    assert record.treatment == TreatmentRecommendation.AVOID
    assert "regulatory" in record.rationale.lower()
