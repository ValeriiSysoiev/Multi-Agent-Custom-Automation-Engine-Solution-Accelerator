import os
import sys
from datetime import datetime, timezone

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
os.environ.setdefault("COSMOSDB_ENDPOINT", "https://cosmos.test")
os.environ.setdefault("COSMOSDB_DATABASE", "test-db")
os.environ.setdefault("AZURE_AI_SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("AZURE_AI_RESOURCE_GROUP", "rg-test")
os.environ.setdefault("AZURE_AI_PROJECT_NAME", "project-test")
os.environ.setdefault("AZURE_AI_AGENT_ENDPOINT", "https://agents.example.com")
os.environ.setdefault("KEYVAULT_URI", "https://kv.test")

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
    def __init__(self, *args, **kwargs):
        pass

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

    def query_items(self, *args, **kwargs):
        async def _iter():
            if False:
                yield None

        return _iter()


azure_cosmos_aio_module.ContainerProxy = _DummyContainerProxy


class _DummyCosmosClient:
    def __init__(self, *args, **kwargs):
        pass

    def get_database_client(self, *args, **kwargs):
        raise RuntimeError("Cosmos access not expected in unit tests")


azure_cosmos_aio_module.CosmosClient = _DummyCosmosClient

azure_core_module = sys.modules.setdefault("azure.core", ModuleType("azure.core"))
azure_core_exceptions_module = sys.modules.setdefault("azure.core.exceptions", ModuleType("azure.core.exceptions"))


class _ResourceExistsError(Exception):
    pass


azure_core_exceptions_module.ResourceExistsError = _ResourceExistsError


class _ResourceNotFoundError(Exception):
    pass


azure_core_exceptions_module.ResourceNotFoundError = _ResourceNotFoundError
StubResourceNotFoundError = azure_core_exceptions_module.ResourceNotFoundError

azure_storage_module = sys.modules.setdefault("azure.storage", ModuleType("azure.storage"))
azure_storage_blob_module = sys.modules.setdefault("azure.storage.blob", ModuleType("azure.storage.blob"))
azure_storage_blob_aio_module = sys.modules.setdefault("azure.storage.blob.aio", ModuleType("azure.storage.blob.aio"))


class _ContentSettings:
    def __init__(self, content_type: str = "application/octet-stream"):
        self.content_type = content_type


class _BlobServiceClient:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("BlobServiceClient should be stubbed in tests")


azure_storage_blob_module.ContentSettings = _ContentSettings
azure_storage_blob_aio_module.BlobServiceClient = _BlobServiceClient
from models.messages_kernel import (
    AgentType,
    AssetIdentifier,
    AssetIdentifierType,
    AssetRecord,
    CanonicalFinding,
    FindingLifecycleStatus,
    RemediationBucket,
    RemediationUnitRecord,
    RiskTier,
    TicketRecord,
    TicketStatus,
    TriageRecord,
    WaiverRecord,
    WaiverStatus,
    ResidualRisk,
)
from repositories.run_event_repository import RunEventRepository
import services.reporting_export_service as reporting_module
from services.reporting_export_service import ReportingExportService


class FakeRepo:
    def __init__(self, items):
        self._items = items

    async def list_all(self):
        return self._items


class MemoryRunEventRepository(RunEventRepository):
    def __init__(self):
        self.events = []

    async def upsert_event(self, record):  # type: ignore[override]
        self.events.append(record)
        return record


class FakeContainer:
    def __init__(self, uploads):
        self.uploads = uploads

    async def create_container(self):
        return

    async def upload_blob(self, name, data, overwrite, content_settings):
        self.uploads.append((name, len(data), content_settings.content_type))


class FakeBlobService:
    def __init__(self):
        self.uploads = []
        self.last_container = None

    def get_container_client(self, name):
        self.last_container = name
        return FakeContainer(self.uploads)

    async def close(self):
        return


class FakePowerBIClient:
    def __init__(self):
        self.calls = 0

    async def trigger_refresh(self, workspace_id, dataset_id):
        self.calls += 1
        return True


class FakePushPowerBIClient(FakePowerBIClient):
    def __init__(self):
        super().__init__()
        self.replace_calls = []

    async def replace_rows(self, workspace_id, dataset_id, table_name, rows):
        if hasattr(rows, "__len__"):
            row_count = len(rows)  # type: ignore[arg-type]
        else:
            materialised = list(rows)
            row_count = len(materialised)
            rows = materialised
        self.replace_calls.append(
            {
                "workspace_id": workspace_id,
                "dataset_id": dataset_id,
                "table": table_name,
                "row_count": row_count,
            }
        )
        return None


def _sample_models():
    canonical = [
        CanonicalFinding(
            id="canon-1",
            canonical_id="canon-1",
            asset_id="asset-1",
            asset_identifiers=[],
            sources=[],
            vuln_key="CVE-2024-0001",
            risk_tier=RiskTier.HIGH,
            status=FindingLifecycleStatus.TRIAGED,
            remediation_bucket=RemediationBucket.PATCH,
        )
    ]
    enrichments = []
    triage = [
        TriageRecord(
            id="tri-1",
            triage_id="tri-1",
            canonical_id="canon-1",
            created_by="Triage_Agent",
            likelihood=3,
            impact=4,
            risk_score=12,
            risk_tier=RiskTier.HIGH,
            treatment="mitigate",
            rationale="test",
            supporting_inputs={},
            residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM),
        )
    ]
    remediation_units = [
        RemediationUnitRecord(
            id="ru-1",
            remediation_unit_id="ru-1",
            bucket=RemediationBucket.PATCH,
            risk_tier=RiskTier.HIGH,
            status=FindingLifecycleStatus.IN_REMEDIATION,
            canonical_ids=["canon-1"],
        )
    ]
    tickets = [
        TicketRecord(
            id="t-1",
            ticket_id="t-1",
            remediation_unit_id="ru-1",
            external_key="CYB-1",
            status=TicketStatus.OPEN,
        )
    ]
    waivers = [
        WaiverRecord(
            id="wa-1",
            waiver_id="wa-1",
            remediation_unit_id="ru-1",
            risk_tier=RiskTier.MEDIUM,
            status=WaiverStatus.REQUESTED,
            requested_by="owner@example.com",
            requested_at=datetime.now(timezone.utc),
            justification="Test",
            compensating_controls=[],
            residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM),
        )
    ]
    assets = [
        AssetRecord(
            id="asset-1",
            asset_id="asset-1",
            identifiers=[AssetIdentifier(id_type=AssetIdentifierType.HOSTNAME, value="host1")],
        )
    ]
    return canonical, enrichments, triage, remediation_units, tickets, waivers, assets


@pytest.mark.asyncio
async def test_reporting_export_uploads_and_refreshes(monkeypatch):
    canonical, enrichments, triage, remediation_units, tickets, waivers, assets = _sample_models()

    run_repo = MemoryRunEventRepository()
    blob_service = FakeBlobService()
    powerbi = FakePowerBIClient()

    config = {
        "tenant_id": "tenant",
        "client_id": "client",
        "workspace_id": "workspace",
        "dataset_id": "dataset",
        "storage_account": "storage",
        "storage_container": "container",
        "export_format": "csv",
    }

    service = ReportingExportService(
        config=config,
        canonical_repo=FakeRepo(canonical),
        enrichment_repo=FakeRepo(enrichments),
        triage_repo=FakeRepo(triage),
        remediation_repo=FakeRepo(remediation_units),
        ticket_repo=FakeRepo(tickets),
        waiver_repo=FakeRepo(waivers),
        asset_repo=FakeRepo(assets),
        run_repo=run_repo,
        blob_service=blob_service,
        powerbi_client=powerbi,
    )

    metrics = await service.export(date_key="20250101", refresh_powerbi=True)
    await service.close()

    assert metrics["facts_findings"] == 1
    assert powerbi.calls == 1
    assert len(blob_service.uploads) > 0
    blob_paths = [entry[0] for entry in blob_service.uploads]
    assert any("facts_findings" in path for path in blob_paths)
    assert run_repo.events[-1].agent_name == AgentType.REPORTING.value


@pytest.mark.asyncio
async def test_reporting_export_handles_missing_storage():
    canonical, enrichments, triage, remediation_units, tickets, waivers, assets = _sample_models()

    run_repo = MemoryRunEventRepository()
    config = {
        "storage_account": "TBD",
        "storage_container": "container",
    }
    service = ReportingExportService(
        config=config,
        canonical_repo=FakeRepo(canonical),
        enrichment_repo=FakeRepo(enrichments),
        triage_repo=FakeRepo(triage),
        remediation_repo=FakeRepo(remediation_units),
        ticket_repo=FakeRepo(tickets),
        waiver_repo=FakeRepo(waivers),
        asset_repo=FakeRepo(assets),
        run_repo=run_repo,
    )

    metrics = await service.export(refresh_powerbi=False)
    await service.close()

    assert metrics["facts_findings"] == 1
    assert run_repo.events[-1].status == "completed"


@pytest.mark.asyncio
async def test_reporting_export_push_dataset(monkeypatch):
    canonical, enrichments, triage, remediation_units, tickets, waivers, assets = _sample_models()

    run_repo = MemoryRunEventRepository()
    blob_service = FakeBlobService()
    powerbi = FakePushPowerBIClient()

    config = {
        "tenant_id": "tenant",
        "client_id": "client",
        "workspace_id": "workspace",
        "dataset_id": "dataset",
        "storage_account": "storage",
        "storage_container": "container",
        "export_format": "csv",
        "push_dataset_enabled": True,
    }

    service = ReportingExportService(
        config=config,
        canonical_repo=FakeRepo(canonical),
        enrichment_repo=FakeRepo(enrichments),
        triage_repo=FakeRepo(triage),
        remediation_repo=FakeRepo(remediation_units),
        ticket_repo=FakeRepo(tickets),
        waiver_repo=FakeRepo(waivers),
        asset_repo=FakeRepo(assets),
        run_repo=run_repo,
        blob_service=blob_service,
        powerbi_client=powerbi,
    )

    metrics = await service.export(date_key="20250102", refresh_powerbi=True)
    await service.close()

    expected_tables = {
        "facts_findings": 1,
        "facts_enrichment": 0,
        "facts_triage": 1,
        "facts_remediation_units": 1,
        "facts_tickets": 1,
        "facts_waivers": 1,
        "dim_assets": 1,
    }

    push_metrics = {k.removeprefix("pbi_rows_"): v for k, v in metrics.items() if k.startswith("pbi_rows_")}
    assert push_metrics == expected_tables
    assert powerbi.calls == 0  # refresh skipped when push dataset enabled
    assert len(powerbi.replace_calls) == len(expected_tables)
    tables_called = {call["table"] for call in powerbi.replace_calls}
    assert tables_called == set(expected_tables.keys())


@pytest.mark.asyncio
async def test_powerbi_secret_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("POWERBI_CLIENT_SECRET", "env-secret")

    captured = {}

    class DummyPowerBI:
        def __init__(self, tenant_id: str, client_id: str, secret: str) -> None:
            captured["args"] = (tenant_id, client_id, secret)

    class MissingSecretVault:
        async def get_secret(self, name: str) -> str:
            raise StubResourceNotFoundError("missing")

        async def close(self) -> None:
            return

    monkeypatch.setattr(reporting_module, "PowerBIClient", DummyPowerBI)

    service = ReportingExportService(
        config={
            "tenant_id": "tenant",
            "client_id": "client",
            "workspace_id": "workspace",
            "dataset_id": "dataset",
            "storage_account": "storage",
            "storage_container": "container",
        },
        canonical_repo=FakeRepo([]),
        enrichment_repo=FakeRepo([]),
        triage_repo=FakeRepo([]),
        remediation_repo=FakeRepo([]),
        ticket_repo=FakeRepo([]),
        waiver_repo=FakeRepo([]),
        asset_repo=FakeRepo([]),
        run_repo=MemoryRunEventRepository(),
        key_vault=MissingSecretVault(),
    )

    client = await service._ensure_powerbi_client()
    await service.close()

    assert isinstance(client, DummyPowerBI)
    assert captured["args"] == ("tenant", "client", "env-secret")


@pytest.mark.asyncio
async def test_reporting_export_prefers_env_tenant(monkeypatch):
    monkeypatch.setenv("PBI_TENANT_ID", "env-tenant")

    service = ReportingExportService(
        config={
            "tenant_id": "config-tenant",
            "client_id": "client",
            "workspace_id": "workspace",
            "dataset_id": "dataset",
            "storage_account": "TBD",
            "storage_container": "container",
        },
        canonical_repo=FakeRepo([]),
        enrichment_repo=FakeRepo([]),
        triage_repo=FakeRepo([]),
        remediation_repo=FakeRepo([]),
        ticket_repo=FakeRepo([]),
        waiver_repo=FakeRepo([]),
        asset_repo=FakeRepo([]),
        run_repo=MemoryRunEventRepository(),
    )

    assert service._tenant_id == "env-tenant"
    await service.close()
