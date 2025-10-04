import os
import sys

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
os.environ.setdefault("AZURE_AI_PROJECT_NAME", "proj-test")
os.environ.setdefault("AZURE_AI_AGENT_ENDPOINT", "https://agents.example.com")
os.environ.setdefault("KEYVAULT_URI", "https://kv.example.vault.azure.net/")

from models.messages_kernel import AssetIdentifier, AssetIdentifierType
from services.jira_assets_client import JiraAssetsClient


def _build_client(monkeypatch: pytest.MonkeyPatch, **env: str) -> JiraAssetsClient:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # Provide a dummy base URL so the client does not require JIRA_BASE_URL
    monkeypatch.setattr(
        "services.jira_assets_client.KeyVaultService",
        lambda: _DummyKeyVault(),
    )
    return JiraAssetsClient(base_url="https://example.atlassian.net")


class _DummyKeyVault:
    async def get_secret(self, name: str) -> str:  # pragma: no cover - should not be invoked
        raise RuntimeError(f"Unexpected secret lookup for {name}")

    async def close(self) -> None:
        return None


def test_attributes_map_preserves_object_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(monkeypatch)
    attributes = [
        {
            "name": "Application",
            "objectAttributeValues": [
                {
                    "objectId": 42,
                    "objectTypeName": "Application / Service",
                    "displayValue": "Payments",
                }
            ],
        }
    ]

    mapping = client._attributes_to_map(attributes)
    values = mapping.get("Application")

    assert values is not None
    assert values[0]["displayValue"] == "Payments"
    assert values[0]["raw"]["objectId"] == 42


@pytest.mark.asyncio
async def test_value_to_reference_prefers_existing_id(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(monkeypatch)
    value = {"objectId": 7, "displayValue": "Billing", "objectTypeName": "Application"}

    reference = await client._value_to_reference(value)

    assert reference == ("7", "Billing", "application")


@pytest.mark.asyncio
async def test_find_host_object_queries_all_host_types(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(monkeypatch, JIRA_ASSETS_HOST_TYPE_NAME="Server,Host")

    queries: list[str] = []

    async def fake_run_aql(query: str):  # type: ignore[override]
        queries.append(query)
        if 'objectType = "Server"' in query:
            return [{"id": "123"}]
        return []

    async def fake_get_object(object_id: str):  # type: ignore[override]
        return {"id": object_id}

    client._run_aql = fake_run_aql  # type: ignore[assignment]
    client._get_object = fake_get_object  # type: ignore[assignment]

    identifier = AssetIdentifier(id_type=AssetIdentifierType.HOSTNAME, value="host-01")

    host_object = await client._find_host_object([identifier])

    assert host_object == {"id": "123"}
    assert any('objectType = "Server"' in query for query in queries)
