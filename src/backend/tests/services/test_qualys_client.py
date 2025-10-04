"""Regression tests for QualysClient XML parsing."""

import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

import httpx
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example-openai")
os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
os.environ.setdefault("AZURE_OPENAI_API_VERSION", "2024-11-20")
os.environ.setdefault("AZURE_AI_SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("AZURE_AI_RESOURCE_GROUP", "rg-test")
os.environ.setdefault("AZURE_AI_PROJECT_NAME", "project-test")
os.environ.setdefault("AZURE_AI_AGENT_ENDPOINT", "https://agents.example.com")
os.environ.setdefault("KEYVAULT_URI", "https://kv.test")
os.environ.setdefault("COSMOSDB_ENDPOINT", "https://cosmos.test")
os.environ.setdefault("COSMOSDB_DATABASE", "test-db")

if "semantic_kernel" not in sys.modules:  # pragma: no cover - stub for tests
    import types
    from pydantic import BaseModel, Field as PydanticField

    semantic_kernel_module = types.ModuleType("semantic_kernel")
    sys.modules["semantic_kernel"] = semantic_kernel_module
    kernel_pydantic_module = types.ModuleType("semantic_kernel.kernel_pydantic")
    sys.modules["semantic_kernel.kernel_pydantic"] = kernel_pydantic_module

    class _KernelBaseModel(BaseModel):
        class Config:
            arbitrary_types_allowed = True
            use_enum_values = True

    kernel_pydantic_module.KernelBaseModel = _KernelBaseModel
    kernel_pydantic_module.Field = PydanticField

    semantic_kernel_kernel_module = types.ModuleType("semantic_kernel.kernel")
    semantic_kernel_kernel_module.Kernel = object
    sys.modules["semantic_kernel.kernel"] = semantic_kernel_kernel_module

if "azure" not in sys.modules:  # pragma: no cover - stub for tests
    import types

    azure_pkg = types.ModuleType("azure")
    azure_pkg.__path__ = []  # mark as package for imports
    sys.modules["azure"] = azure_pkg
    azure_ai_module = sys.modules.setdefault("azure.ai", types.ModuleType("azure.ai"))
    azure_ai_projects = types.ModuleType("azure.ai.projects")
    azure_ai_projects_aio = types.ModuleType("azure.ai.projects.aio")

    class _DummyAIProjectClient:
        async def close(self) -> None:  # pragma: no cover - stub
            return

    azure_ai_projects_aio.AIProjectClient = _DummyAIProjectClient
    sys.modules["azure.ai.projects"] = azure_ai_projects
    sys.modules["azure.ai.projects.aio"] = azure_ai_projects_aio

    azure_identity_module = types.ModuleType("azure.identity")
    azure_identity_aio_module = types.ModuleType("azure.identity.aio")

    class _DummyCredential:
        def __init__(self, *args, **kwargs):  # pragma: no cover - stub
            pass

        async def close(self) -> None:  # pragma: no cover - stub
            return

    azure_identity_module.ManagedIdentityCredential = _DummyCredential
    azure_identity_module.DefaultAzureCredential = _DummyCredential
    azure_identity_aio_module.ManagedIdentityCredential = _DummyCredential
    azure_identity_aio_module.DefaultAzureCredential = _DummyCredential
    sys.modules["azure.identity"] = azure_identity_module
    sys.modules["azure.identity.aio"] = azure_identity_aio_module

    azure_cosmos_aio = types.ModuleType("azure.cosmos.aio")
    azure_cosmos_exceptions = types.ModuleType("azure.cosmos.exceptions")

    class _DummyContainerProxy:
        pass

    class _DummyCosmosClient:
        pass

    class _DummyCosmosError(Exception):
        pass

    azure_cosmos_aio.ContainerProxy = _DummyContainerProxy
    azure_cosmos_aio.CosmosClient = _DummyCosmosClient
    azure_cosmos_exceptions.CosmosResourceNotFoundError = _DummyCosmosError
    sys.modules["azure.cosmos.aio"] = azure_cosmos_aio
    sys.modules["azure.cosmos.exceptions"] = azure_cosmos_exceptions

    azure_keyvault_secrets = types.ModuleType("azure.keyvault.secrets")
    azure_keyvault_secrets_aio = types.ModuleType("azure.keyvault.secrets.aio")

    class _DummySecretClient:
        async def close(self) -> None:  # pragma: no cover - stub
            return

    azure_keyvault_secrets_aio.SecretClient = _DummySecretClient
    sys.modules["azure.keyvault"] = types.ModuleType("azure.keyvault")
    sys.modules["azure.keyvault.secrets"] = azure_keyvault_secrets
    sys.modules["azure.keyvault.secrets.aio"] = azure_keyvault_secrets_aio

    azure_core_exceptions = types.ModuleType("azure.core.exceptions")

    class _DummyResourceNotFoundError(Exception):
        pass

    azure_core_exceptions.ResourceNotFoundError = _DummyResourceNotFoundError
    azure_core_pkg = types.ModuleType("azure.core")
    azure_core_pkg.__path__ = []
    sys.modules["azure.core"] = azure_core_pkg
    sys.modules["azure.core.exceptions"] = azure_core_exceptions

import services.qualys_client as qualys_module
from services.qualys_client import QualysClient


def _client() -> QualysClient:
    return object.__new__(QualysClient)


class _VaultStub:
    async def close(self) -> None:  # pragma: no cover - simple async stub
        return None


def _build_test_client(monkeypatch: pytest.MonkeyPatch, lookback: Optional[int]) -> QualysClient:
    monkeypatch.setattr(qualys_module, "DEFAULT_LOOKBACK_DAYS", lookback)
    monkeypatch.setattr(qualys_module, "KeyVaultService", lambda: _VaultStub())
    return QualysClient()


def test_parse_detection_xml_new_schema() -> None:
    client = _client()
    xml_payload = """
    <HOST_LIST_VM_DETECTION_OUTPUT>
      <RESPONSE>
        <HOST_LIST>
          <HOST>
            <ID>1</ID>
            <DETECTION_LIST>
              <DETECTION>
                <QID>105936</QID>
                <LAST_FOUND>2025-09-26T00:00:00Z</LAST_FOUND>
                <TYPE>Confirmed</TYPE>
                <STATUS>Active</STATUS>
              </DETECTION>
            </DETECTION_LIST>
          </HOST>
        </HOST_LIST>
      </RESPONSE>
    </HOST_LIST_VM_DETECTION_OUTPUT>
    """

    records = client._parse_detection_xml(xml_payload)

    assert len(records) == 1
    assert records[0]["detection"]["QID"] == "105936"


def test_parse_detection_xml_legacy_schema() -> None:
    client = _client()
    xml_payload = """
    <SIMPLE_RETURN>
      <RESPONSE>
        <HOST_LIST>
          <HOST>
            <ID>2</ID>
            <DETECTION_LIST>
              <DETECTION>
                <QID>90007</QID>
                <LAST_FOUND>2025-09-20T00:00:00Z</LAST_FOUND>
                <STATUS>Active</STATUS>
              </DETECTION>
            </DETECTION_LIST>
          </HOST>
        </HOST_LIST>
      </RESPONSE>
    </SIMPLE_RETURN>
    """

    records = client._parse_detection_xml(xml_payload)

    assert len(records) == 1
    assert records[0]["detection"]["QID"] == "90007"


@pytest.mark.asyncio
async def test_fetch_detections_skips_lookback_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_test_client(monkeypatch, None)

    captured: dict[str, dict[str, str]] = {}

    async def fake_post(*args, **kwargs):
        captured["data"] = kwargs.get("data", {})
        return SimpleNamespace(text="<HOST_LIST_VM_DETECTION_OUTPUT><RESPONSE/></HOST_LIST_VM_DETECTION_OUTPUT>")

    async def ensure_stub() -> None:
        client._http = SimpleNamespace(post=fake_post)
        client._auth = httpx.BasicAuth("user", "pass")

    client._ensure_client = ensure_stub  # type: ignore[assignment]

    detections = await client.fetch_detections()

    assert detections == []
    assert "vm_scan_since" not in captured["data"]


@pytest.mark.asyncio
async def test_fetch_detections_uses_sync_state(monkeypatch: pytest.MonkeyPatch) -> None:
    since = datetime(2024, 1, 2, tzinfo=timezone.utc)
    client = _build_test_client(monkeypatch, None)

    captured: dict[str, dict[str, str]] = {}

    async def fake_post(*args, **kwargs):
        captured["data"] = kwargs.get("data", {})
        return SimpleNamespace(text="<HOST_LIST_VM_DETECTION_OUTPUT><RESPONSE/></HOST_LIST_VM_DETECTION_OUTPUT>")

    async def ensure_stub() -> None:
        client._http = SimpleNamespace(post=fake_post)
        client._auth = httpx.BasicAuth("user", "pass")

    client._ensure_client = ensure_stub  # type: ignore[assignment]

    await client.fetch_detections(since)

    assert captured["data"]["vm_scan_since"] == "2024-01-02"


@pytest.mark.asyncio
async def test_fetch_detections_applies_lookback_override(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_test_client(monkeypatch, 7)

    captured: dict[str, dict[str, str]] = {}

    async def fake_post(*args, **kwargs):
        captured["data"] = kwargs.get("data", {})
        return SimpleNamespace(text="<HOST_LIST_VM_DETECTION_OUTPUT><RESPONSE/></HOST_LIST_VM_DETECTION_OUTPUT>")

    async def ensure_stub() -> None:
        client._http = SimpleNamespace(post=fake_post)
        client._auth = httpx.BasicAuth("user", "pass")

    client._ensure_client = ensure_stub  # type: ignore[assignment]

    await client.fetch_detections()

    assert captured["data"].get("vm_scan_since") is not None
