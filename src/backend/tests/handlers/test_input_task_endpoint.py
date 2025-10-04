import os
import sys
from typing import Any

from fastapi.testclient import TestClient
import types

# Prefer actual Azure SDKs; fall back to lightweight stubs when unavailable (e.g., offline CI).
try:  # pragma: no branch - use installed SDK whenever present
    import azure.identity  # type: ignore
    import azure.identity.aio  # type: ignore
    import azure.cosmos.exceptions  # type: ignore
    import azure.cosmos.aio  # type: ignore
    import azure.keyvault.secrets.aio  # type: ignore
    import azure.ai.projects.aio  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback shims
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

import pytest
# Ensure env defaults so app imports succeed
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

from models.messages_kernel import AgentType, Plan


class FakeMemoryStore:
    def __init__(self):
        self.plan: Plan | None = None

    async def get_plan_by_session(self, session_id: str):  # pragma: no cover - simple storage
        return self.plan


class FakeGroupChatManager:
    def __init__(self, memory_store: FakeMemoryStore):
        self.memory_store = memory_store
        self.handled_payload: Any = None

    async def handle_input_task(self, input_task):
        self.handled_payload = input_task
        self.memory_store.plan = Plan(
            session_id=input_task.session_id,
            user_id="user-123",
            initial_goal=input_task.description,
        )


@pytest.fixture()
def input_task_client(monkeypatch):
    memory_store = FakeMemoryStore()

    async def fake_initialize_runtime_and_context(session_id, user_id):
        return None, memory_store

    async def fake_rai_success(description: str, is_task_creation: bool) -> bool:
        return True

    async def fake_create_all_agents(*args, **kwargs):
        store = kwargs.get("memory_store", memory_store)
        manager = FakeGroupChatManager(store)
        return {AgentType.GROUP_CHAT_MANAGER: manager}

    monkeypatch.setattr(app_kernel, "initialize_runtime_and_context", fake_initialize_runtime_and_context)
    monkeypatch.setattr(app_kernel, "rai_success", fake_rai_success)
    monkeypatch.setattr(app_kernel.AgentFactory, "create_all_agents", fake_create_all_agents)
    monkeypatch.setattr(app_kernel.config, "get_ai_project_client", lambda: None)
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

    return TestClient(app_kernel.app), memory_store


def test_input_task_creates_plan(input_task_client):
    client, memory_store = input_task_client
    payload = {
        "session_id": "session-abc",
        "description": "Investigate outstanding KEV findings",
    }

    response = client.post("/api/input_task", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == payload["session_id"]
    assert data["plan_id"]
    assert data["status"].startswith("Plan created")

    plan = memory_store.plan
    assert plan is not None
    assert plan.session_id == payload["session_id"]
    assert plan.initial_goal == payload["description"]
