
# src/backend/tests/context/test_cosmos_memory.py
# Drop-in test that self-stubs all external imports used by cosmos_memory_kernel
# so we don't need to modify the repo structure or CI env.

import os
import sys
import types
from pathlib import Path

import pytest
from unittest.mock import AsyncMock

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[4]
SRC_ROOT = REPO_ROOT / "src"
BACKEND_DIR = SRC_ROOT / "backend"

for path in (REPO_ROOT, SRC_ROOT, BACKEND_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.backend.models import messages_kernel as real_messages_kernel
from src.backend import app_config

sys.modules.setdefault("models", types.ModuleType("models"))
sys.modules["models"].messages_kernel = real_messages_kernel
sys.modules["models.messages_kernel"] = real_messages_kernel

try:  # pragma: no branch - prefer installed SDKs
    import azure.identity  # type: ignore
    import azure.identity.aio  # type: ignore
    import azure.keyvault.secrets.aio  # type: ignore
    import azure.ai.projects.aio  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback stubs
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

# 4) azure.cosmos.partition_key.PartitionKey (provide if sdk isn't installed)
try:
    from azure.cosmos.partition_key import PartitionKey  # type: ignore
except Exception:  # pragma: no cover
    azure_mod = sys.modules.setdefault("azure", types.ModuleType("azure"))
    azure_cosmos_mod = sys.modules.setdefault("azure.cosmos", types.ModuleType("azure.cosmos"))
    azure_cosmos_pk_mod = types.ModuleType("azure.cosmos.partition_key")
    class PartitionKey:  # minimal shim
        def __init__(self, path: str): self.path = path
    azure_cosmos_pk_mod.PartitionKey = PartitionKey
    sys.modules.setdefault("azure.cosmos.partition_key", azure_cosmos_pk_mod)
    azure_cosmos_exc_mod = types.ModuleType("azure.cosmos.exceptions")
    class CosmosHttpResponseError(Exception):
        pass
    azure_cosmos_exc_mod.CosmosHttpResponseError = CosmosHttpResponseError
    sys.modules.setdefault("azure.cosmos.exceptions", azure_cosmos_exc_mod)

# 5) azure.cosmos.aio.CosmosClient (we’ll patch it in a fixture, but ensure import exists)
try:
    from azure.cosmos.aio import CosmosClient  # type: ignore
except Exception:  # pragma: no cover
    azure_cosmos_aio_mod = types.ModuleType("azure.cosmos.aio")
    class CosmosClient:  # placeholder; we patch this class below
        def __init__(self, *a, **k): ...
        def get_database_client(self, *a, **k): ...
    azure_cosmos_aio_mod.CosmosClient = CosmosClient
    sys.modules.setdefault("azure.cosmos.aio", azure_cosmos_aio_mod)

# ----------------- Import the SUT (after stubs are in place) -----------------
try:
    # If you added an alias file src/backend/context/cosmos_memory.py, this will work:
    from src.backend.context.cosmos_memory import CosmosMemoryContext as CosmosBufferedChatCompletionContext
except Exception:
    # Fallback to the kernel module (your provided code)
    from src.backend.context.cosmos_memory_kernel import CosmosMemoryContext as CosmosBufferedChatCompletionContext  # type: ignore

# Import PartitionKey (either real or our shim) for assertions
try:
    from azure.cosmos.partition_key import PartitionKey  # type: ignore
except Exception:  # already defined above in shim
    pass

# ----------------- Fixtures -----------------

@pytest.fixture
def fake_cosmos_stack(monkeypatch):
    """
    Patch the *SUT's* CosmosClient symbol so initialize() uses our AsyncMocks:
      CosmosClient(...).get_database_client() -> mock_db
      mock_db.create_container_if_not_exists(...) -> mock_container
    """
    import sys

    mock_container = AsyncMock()
    mock_db = AsyncMock()
    mock_db.create_container_if_not_exists = AsyncMock(return_value=mock_container)

    def _fake_ctor(*_a, **_k):
        # mimic a client object with get_database_client returning our mock_db
        return types.SimpleNamespace(
            get_database_client=lambda *_a2, **_k2: mock_db
        )

    # Find the actual module where CosmosBufferedChatCompletionContext is defined
    sut_module_name = CosmosBufferedChatCompletionContext.__module__
    sut_module = sys.modules[sut_module_name]

    # Patch the symbol the SUT imported (its local binding), not the SDK module
    monkeypatch.setattr(sut_module, "CosmosClient", _fake_ctor, raising=False)

    return mock_db, mock_container


@pytest.fixture(autouse=True)
def patch_app_config(monkeypatch):
    monkeypatch.setenv("COSMOSDB_CONTAINER", "mock-container")
    monkeypatch.setenv("COSMOSDB_ENDPOINT", "https://mock-endpoint")
    monkeypatch.setenv("COSMOSDB_DATABASE", "mock-database")

    from src.backend.app_config import AppConfig
    from src.backend.context import cosmos_memory_kernel

    new_config = AppConfig()
    monkeypatch.setattr(app_config, "config", new_config)
    monkeypatch.setattr(cosmos_memory_kernel, "config", new_config)

@pytest.fixture
def mock_env(monkeypatch):
    # Optional: not strictly needed because we stubbed app_config.config above,
    # but keeps parity with your previous env fixture.
    env_vars = {
        "COSMOSDB_ENDPOINT": "https://mock-endpoint",
        "COSMOSDB_KEY": "mock-key",
        "COSMOSDB_DATABASE": "mock-database",
        "COSMOSDB_CONTAINER": "mock-container",
    }
    for k, v in env_vars.items():
        monkeypatch.setenv(k, v)

# ----------------- Test -----------------

@pytest.mark.asyncio
async def test_initialize(fake_cosmos_stack, mock_env):
    mock_db, mock_container = fake_cosmos_stack

    assert app_config.config.COSMOSDB_CONTAINER == "mock-container"
    assert app_config.config.COSMOSDB_ENDPOINT == "https://mock-endpoint"
    assert app_config.config.COSMOSDB_DATABASE == "mock-database"

    ctx = CosmosBufferedChatCompletionContext(
        session_id="test_session",
        user_id="test_user",
    )
    assert ctx._cosmos_container == "mock-container"

    await ctx.initialize()

    mock_db.create_container_if_not_exists.assert_called_once()
    # Strict arg check:
    args, kwargs = mock_db.create_container_if_not_exists.call_args
    container_id = kwargs.get("id") if "id" in kwargs else (args[0] if args else None)
    assert container_id == "mock-container"

    pk = kwargs.get("partition_key") if "partition_key" in kwargs else (args[1] if len(args) > 1 else None)
    assert isinstance(pk, PartitionKey) and getattr(pk, "path", None) == "/session_id"

    assert ctx._container == mock_container
