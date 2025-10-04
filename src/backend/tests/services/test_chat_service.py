import os
import sys
import types
from datetime import datetime, timezone

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pytest

os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example-openai")
os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
os.environ.setdefault("AZURE_OPENAI_API_VERSION", "2024-11-20")
os.environ.setdefault("AZURE_AI_SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("AZURE_AI_RESOURCE_GROUP", "rg-test")
os.environ.setdefault("AZURE_AI_PROJECT_NAME", "project-test")
os.environ.setdefault("AZURE_AI_AGENT_ENDPOINT", "https://agents.example.com")
os.environ.setdefault("KEYVAULT_URI", "https://kv.test")

if "semantic_kernel" not in sys.modules:

    semantic_kernel_module = types.ModuleType("semantic_kernel")
    sys.modules["semantic_kernel"] = semantic_kernel_module
    kernel_pydantic_module = types.ModuleType("semantic_kernel.kernel_pydantic")
    sys.modules["semantic_kernel.kernel_pydantic"] = kernel_pydantic_module

    from pydantic import BaseModel, Field as PydanticField

    class _KernelBaseModel(BaseModel):
        class Config:
            arbitrary_types_allowed = True
            use_enum_values = True

    kernel_pydantic_module.KernelBaseModel = _KernelBaseModel
    kernel_pydantic_module.Field = PydanticField

    semantic_kernel_kernel_module = types.ModuleType("semantic_kernel.kernel")
    semantic_kernel_kernel_module.Kernel = object
    sys.modules["semantic_kernel.kernel"] = semantic_kernel_kernel_module

if "azure" not in sys.modules:
    import types

    azure_module = types.ModuleType("azure")
    sys.modules["azure"] = azure_module

azure_ai_module = sys.modules.setdefault("azure.ai", types.ModuleType("azure.ai"))
azure_ai_projects_module = sys.modules.setdefault("azure.ai.projects", types.ModuleType("azure.ai.projects"))
azure_ai_projects_aio_module = sys.modules.setdefault("azure.ai.projects.aio", types.ModuleType("azure.ai.projects.aio"))


class _DummyAIProjectClient:
    async def close(self) -> None:
        return


azure_ai_projects_aio_module.AIProjectClient = _DummyAIProjectClient

azure_cosmos_module = sys.modules.setdefault("azure.cosmos", types.ModuleType("azure.cosmos"))
azure_cosmos_aio_module = types.ModuleType("azure.cosmos.aio")
azure_cosmos_exceptions_module = types.ModuleType("azure.cosmos.exceptions")


class _DummyContainerProxy:  # pragma: no cover
    pass


class _DummyCosmosClient:  # pragma: no cover
    pass


class _DummyCosmosException(Exception):
    pass


azure_cosmos_aio_module.ContainerProxy = _DummyContainerProxy
azure_cosmos_aio_module.CosmosClient = _DummyCosmosClient
azure_cosmos_exceptions_module.CosmosResourceNotFoundError = _DummyCosmosException

sys.modules["azure.cosmos.aio"] = azure_cosmos_aio_module
sys.modules["azure.cosmos.exceptions"] = azure_cosmos_exceptions_module

azure_keyvault_module = sys.modules.setdefault("azure.keyvault", types.ModuleType("azure.keyvault"))
azure_keyvault_secrets_module = types.ModuleType("azure.keyvault.secrets")
azure_keyvault_secrets_aio_module = types.ModuleType("azure.keyvault.secrets.aio")


class _DummySecretClient:  # pragma: no cover
    async def close(self) -> None:
        return


azure_keyvault_secrets_aio_module.SecretClient = _DummySecretClient
sys.modules["azure.keyvault.secrets"] = azure_keyvault_secrets_module
sys.modules["azure.keyvault.secrets.aio"] = azure_keyvault_secrets_aio_module

azure_identity_module = sys.modules.setdefault("azure.identity", types.ModuleType("azure.identity"))
azure_identity_aio_module = types.ModuleType("azure.identity.aio")


class _DummyCredential:  # pragma: no cover
    async def close(self) -> None:
        return


azure_identity_module.ManagedIdentityCredential = _DummyCredential
azure_identity_module.DefaultAzureCredential = _DummyCredential
azure_identity_aio_module.ManagedIdentityCredential = _DummyCredential
azure_identity_aio_module.DefaultAzureCredential = _DummyCredential

sys.modules["azure.identity.aio"] = azure_identity_aio_module

from models.messages_kernel import (
    AssetIdentifier,
    AssetIdentifierType,
    AssetRecord,
    CanonicalFinding,
    ConfidenceLevel,
    EnrichmentRecord,
    ExposureSurface,
    FindingLifecycleStatus,
    RemediationBucket,
    RemediationUnitRecord,
    ResidualRisk,
    RiskTier,
    SourceReference,
    ThreatSignal,
    TriageRecord,
    TreatmentRecommendation,
)
from services.chat_service import ChatService


class StubAssetRepo:
    def __init__(self, asset):
        self._asset = asset

    async def get_asset(self, asset_id: str):
        return self._asset if self._asset.asset_id == asset_id else None


class StubCanonicalRepo:
    def __init__(self, records):
        self._records = records

    async def query_open_findings(self, **_kwargs):
        return self._records


class StubTriageRepo:
    def __init__(self, triage):
        self._triage = triage

    async def get_latest(self, _canonical_id: str):
        return self._triage


class StubRemediationRepo:
    def __init__(self, record):
        self._record = record

    async def get_unit(self, remediation_unit_id: str):
        return self._record if self._record.remediation_unit_id == remediation_unit_id else None


class StubTicketRepo:
    async def list_by_status(self, **_kwargs):
        return []


class StubWaiverRepo:
    async def list_due_within(self, **_kwargs):
        return []


class StubRunEventRepo:
    def __init__(self):
        self.records = []

    async def upsert_event(self, record):
        self.records.append(record)
        return record


class StubEnrichmentRepo:
    def __init__(self, record: EnrichmentRecord | None):
        self._record = record

    async def get_enrichment(self, canonical_id: str, asset_id: str):
        if self._record and self._record.canonical_id == canonical_id and self._record.asset_id == asset_id:
            return self._record
        return None


@pytest.mark.asyncio
async def test_chat_service_open_findings_returns_data():
    asset = AssetRecord(
        asset_id="asset-web-01",
        identifiers=[
            AssetIdentifier(
                id_type=AssetIdentifierType.HOSTNAME,
                value="web-01",
                source="test",
                last_observed=datetime.now(timezone.utc),
            )
        ],
    )
    asset.application_context.application = "Customer Web"
    asset.application_context.owner = "owner@example.com"

    canonical = CanonicalFinding(
        canonical_id="canon-web-01",
        asset_id="asset-web-01",
        asset_identifiers=asset.identifiers,
        sources=[
            SourceReference(
                scanner_id="seed",
                external_id="1",
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
            )
        ],
        vuln_key="CVE-2024-1111",
        severity="High",
        risk_tier=RiskTier.HIGH,
        status=FindingLifecycleStatus.OPEN,
        remediation_bucket=RemediationBucket.PATCH,
        first_observed=datetime.now(timezone.utc),
        last_observed=datetime.now(timezone.utc),
        remediation_unit_id="ru-canon-web-01",
    )

    triage = TriageRecord(
        triage_id="triage-1",
        canonical_id="canon-web-01",
        created_by="seed",
        likelihood=4,
        impact=4,
        risk_score=16,
        risk_tier=RiskTier.HIGH,
        treatment=TreatmentRecommendation.MITIGATE,
        rationale="Seed",
        residual_risk=ResidualRisk(risk_tier=RiskTier.HIGH, risk_score=16),
    )

    remediation = RemediationUnitRecord(
        remediation_unit_id="ru-canon-web-01",
        bucket=RemediationBucket.PATCH,
        risk_tier=RiskTier.HIGH,
        canonical_ids=["canon-web-01"],
        owner="Platform Operations",
    )

    enrichment = EnrichmentRecord(
        canonical_id="canon-web-01",
        asset_id="asset-web-01",
        exposure=ExposureSurface(),
        threat_signals=[],
    )

    run_repo = StubRunEventRepo()

    service = ChatService(
        asset_repo=StubAssetRepo(asset),
        canonical_repo=StubCanonicalRepo([canonical]),
        triage_repo=StubTriageRepo(triage),
        remediation_repo=StubRemediationRepo(remediation),
        ticket_repo=StubTicketRepo(),
        waiver_repo=StubWaiverRepo(),
        run_event_repo=run_repo,
        enrichment_repo=StubEnrichmentRepo(enrichment),
    )

    response = await service.answer_question(
        question="List high findings",
        user_context={"applications": ["Customer Web"]},
    )

    assert response["intent"] == "open_findings"
    assert response["results"]
    assert any(citation["type"] == "canonical_finding" for citation in response["citations"])
    assert response["run_id"]
    assert run_repo.records


@pytest.mark.asyncio
async def test_chat_service_kev_exposures_filters_enrichment():
    asset = AssetRecord(asset_id="asset-1")
    asset.application_context.application = "Payments"
    asset.application_context.owner = "owner"

    canonical = CanonicalFinding(
        canonical_id="canon-1",
        asset_id="asset-1",
        sources=[],
        vuln_key="CVE-2024-9999",
        severity="High",
        risk_tier=RiskTier.HIGH,
        status=FindingLifecycleStatus.OPEN,
        remediation_bucket=RemediationBucket.PATCH,
        remediation_unit_id=None,
    )

    enrichment = EnrichmentRecord(
        canonical_id="canon-1",
        asset_id="asset-1",
        threat_signals=[
            ThreatSignal(
                source="cisa_kev",
                signal_type="known_exploited",
                confidence=ConfidenceLevel.HIGH,
                details={"description": "Actively exploited"},
            )
        ],
    )

    service = ChatService(
        asset_repo=StubAssetRepo(asset),
        canonical_repo=StubCanonicalRepo([canonical]),
        triage_repo=StubTriageRepo(None),
        remediation_repo=StubRemediationRepo(None),
        ticket_repo=StubTicketRepo(),
        waiver_repo=StubWaiverRepo(),
        run_event_repo=StubRunEventRepo(),
        enrichment_repo=StubEnrichmentRepo(enrichment),
    )

    response = await service.answer_question(
        question="Show KEV exposures",
        user_context={"applications": ["Payments"]},
    )

    assert response["intent"] == "kev_exposures"
    assert len(response["results"]) == 1
    assert response["results"][0]["kev_signals"]


@pytest.mark.asyncio
async def test_chat_service_executive_summary_counts():
    asset = AssetRecord(asset_id="asset-1")
    asset.application_context.application = "CRM"

    canonical = CanonicalFinding(
        canonical_id="canon-1",
        asset_id="asset-1",
        sources=[],
        vuln_key="CVE-2024-0002",
        severity="Critical",
        risk_tier=RiskTier.CRITICAL,
        status=FindingLifecycleStatus.OPEN,
        remediation_bucket=RemediationBucket.PATCH,
    )

    service = ChatService(
        asset_repo=StubAssetRepo(asset),
        canonical_repo=StubCanonicalRepo([canonical]),
        triage_repo=StubTriageRepo(None),
        remediation_repo=StubRemediationRepo(None),
        ticket_repo=StubTicketRepo(),
        waiver_repo=StubWaiverRepo(),
        run_event_repo=StubRunEventRepo(),
        enrichment_repo=StubEnrichmentRepo(None),
    )

    response = await service.answer_question(
        question="Give me an executive summary",
        user_context={"applications": ["CRM"]},
    )

    summary = response["results"][0]
    assert summary["total_open"] == 1
    assert summary["by_risk"]["critical"] == 1
