import os
import sys
from unittest.mock import AsyncMock

import types

# Prefer real Azure SDKs; install lightweight shims only when unavailable (e.g., local CI without extras)
try:  # pragma: no branch - use installed SDK whenever present
    import azure.identity  # type: ignore
    import azure.identity.aio  # type: ignore
    import azure.cosmos.exceptions  # type: ignore
    import azure.cosmos.aio  # type: ignore
    import azure.keyvault.secrets.aio  # type: ignore
    import azure.ai.projects.aio  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback stubs for offline test runs
    def _ensure_module(name: str):
        return sys.modules.setdefault(name, types.ModuleType(name))

    azure_mod = _ensure_module("azure")
    azure_identity_mod = _ensure_module("azure.identity")
    azure_identity_aio_mod = _ensure_module("azure.identity.aio")

    class _DummyCredential:
        def __init__(self, *args, **kwargs):
            pass

        def get_token(self, *args, **kwargs):
            class _Token:
                token = "test-token"

            return _Token()

        async def close(self):
            return None

    azure_identity_mod.DefaultAzureCredential = _DummyCredential
    azure_identity_mod.ManagedIdentityCredential = _DummyCredential
    azure_identity_aio_mod.DefaultAzureCredential = _DummyCredential
    azure_identity_aio_mod.ManagedIdentityCredential = _DummyCredential

    azure_cosmos_mod = _ensure_module("azure.cosmos")
    azure_cosmos_exc_mod = _ensure_module("azure.cosmos.exceptions")
    azure_cosmos_aio_mod = _ensure_module("azure.cosmos.aio")

    class CosmosHttpResponseError(Exception):
        pass

    azure_cosmos_exc_mod.CosmosHttpResponseError = CosmosHttpResponseError

    class _DummyCosmosClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_database_client(self, *args, **kwargs):
            class _DB:
                def get_container_client(self, *_args, **_kwargs):
                    class _Container:
                        async def read_container(self):
                            return {}

                    return _Container()

            return _DB()

    azure_cosmos_aio_mod.CosmosClient = _DummyCosmosClient

    azure_keyvault_mod = _ensure_module("azure.keyvault")
    azure_kv_secrets_mod = _ensure_module("azure.keyvault.secrets")
    azure_kv_secrets_aio_mod = _ensure_module("azure.keyvault.secrets.aio")

    class _DummySecretClient:
        def __init__(self, *args, **kwargs):
            pass

        async def close(self):
            return None

    azure_kv_secrets_aio_mod.SecretClient = _DummySecretClient

    azure_ai_mod = _ensure_module("azure.ai")
    azure_ai_projects_mod = _ensure_module("azure.ai.projects")
    azure_ai_projects_aio_mod = _ensure_module("azure.ai.projects.aio")

    class _DummyAIProjectClient:
        def __init__(self, *args, **kwargs):
            pass

        async def close(self):
            return None

    azure_ai_projects_aio_mod.AIProjectClient = _DummyAIProjectClient

import pytest
from fastapi.testclient import TestClient

from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[4]
SRC_ROOT = REPO_ROOT / "src"
BACKEND_DIR = SRC_ROOT / "backend"

for path in (REPO_ROOT, SRC_ROOT, BACKEND_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.backend import app_kernel

# Ensure required env defaults so app import does not fail
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

from models.messages_kernel import ChatAnswer


class FakeMemoryStore:
    def __init__(self):
        self.upserts = []

    async def upsert_async(self, collection_name, record):
        self.upserts.append((collection_name, record))
        return record.get("id", "")


@pytest.fixture()
def client(monkeypatch):
    # Stub authentication helper to provide deterministic scope
    fake_memory_store = FakeMemoryStore()

    async def fake_initialize_runtime_and_context(session_id, user_id):
        return None, fake_memory_store

    monkeypatch.setattr(
        app_kernel,
        "get_authenticated_user_details",
        lambda request_headers: {
            "user_principal_id": "user-123",
            "user_roles": ["Platform Ops"],
            "applications": ["Payments"],
            "groups": ["Platform Ops"],
        },
    )
    monkeypatch.setattr(
        app_kernel,
        "initialize_runtime_and_context",
        fake_initialize_runtime_and_context,
    )
    return TestClient(app_kernel.app)


def test_chat_endpoint_success(client, monkeypatch):
    fake_response = {
        "intent": "open_findings",
        "question": "Show open findings",
        "filters": {"risk_tiers": ["High"]},
        "scope": {"applications": ["Payments"], "owner_groups": ["Platform Ops"], "is_admin": False},
        "results": [{"canonical_id": "canon-1"}],
        "citations": [{"type": "canonical_finding", "id": "canon-1"}],
        "run_id": "run-123",
    }

    fake_chat_service = AsyncMock()
    fake_chat_service.answer_question.return_value = fake_response
    monkeypatch.setattr(app_kernel.AgentFactory, "get_chat_service", lambda: fake_chat_service)

    response = client.post(
        "/api/chat",
        json={"question": "Show open findings", "limit": 5, "session_id": "session-1"},
    )

    assert response.status_code == 200
    data = response.json()
    expected = dict(fake_response)
    expected["session_id"] = "session-1"
    assert data == ChatAnswer(**expected).model_dump()
    fake_chat_service.answer_question.assert_awaited_once()


def test_chat_endpoint_access_denied(client, monkeypatch):
    fake_chat_service = AsyncMock()
    fake_chat_service.answer_question.side_effect = app_kernel.AccessDeniedError("no scope")
    monkeypatch.setattr(app_kernel.AgentFactory, "get_chat_service", lambda: fake_chat_service)

    response = client.post(
        "/api/chat", json={"question": "Show open findings", "session_id": "session-2"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "no scope"
    fake_chat_service.answer_question.assert_awaited_once()
