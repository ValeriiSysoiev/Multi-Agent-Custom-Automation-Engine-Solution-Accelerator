# src/backend/tests/test_config.py
import os
import sys
from importlib import reload
from types import ModuleType
from unittest.mock import patch

# Make repo root importable so `src.backend...` works
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Mock environment variables so app_config can construct safely at import time
MOCK_ENV_VARS = {
    # Cosmos
    "COSMOSDB_ENDPOINT": "https://mock-cosmosdb.documents.azure.com:443/",
    "COSMOSDB_DATABASE": "mock_database",
    "COSMOSDB_CONTAINER": "mock_container",

    # Azure OpenAI
    "AZURE_OPENAI_DEPLOYMENT_NAME": "mock-deployment",
    "AZURE_OPENAI_API_VERSION": "2024-11-20",
    "AZURE_OPENAI_ENDPOINT": "https://mock-openai-endpoint.azure.com/",

    # Optional auth (kept for completeness)
    "AZURE_TENANT_ID": "mock-tenant-id",
    "AZURE_CLIENT_ID": "mock-client-id",
    "AZURE_CLIENT_SECRET": "mock-client-secret",

    # Azure AI Project (required by current AppConfig)
    "AZURE_AI_SUBSCRIPTION_ID": "00000000-0000-0000-0000-000000000000",
    "AZURE_AI_RESOURCE_GROUP": "rg-test",
    "AZURE_AI_PROJECT_NAME": "proj-test",
    "AZURE_AI_AGENT_ENDPOINT": "https://agents.example.com/",

    # Misc
    "USER_LOCAL_BROWSER_LANGUAGE": "en-US",
}

# Provide lightweight Azure module stubs so app_config imports cleanly during tests
try:  # pragma: no branch - prefer real SDKs when available
    import azure.identity  # type: ignore
    import azure.identity.aio  # type: ignore
    import azure.cosmos.aio  # type: ignore
    import azure.keyvault.secrets.aio  # type: ignore
    import azure.ai.projects.aio  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback shims for offline test envs
    def _ensure_module(name: str) -> ModuleType:
        return sys.modules.setdefault(name, ModuleType(name))

    _ensure_module("azure")
    _ensure_module("azure.ai")
    _ensure_module("azure.ai.projects")
    azure_ai_projects_aio = _ensure_module("azure.ai.projects.aio")

    class _DummyAIProjectClient:  # pragma: no cover - test helper
        pass

    azure_ai_projects_aio.AIProjectClient = _DummyAIProjectClient

    _ensure_module("azure.cosmos")
    azure_cosmos_aio = _ensure_module("azure.cosmos.aio")

    class _DummyCosmosClient:  # pragma: no cover - test helper
        def __init__(self, *args, **kwargs):
            pass

        def get_database_client(self, *args, **kwargs):
            raise RuntimeError("Cosmos client should be mocked in config tests")

    azure_cosmos_aio.CosmosClient = _DummyCosmosClient

    _ensure_module("azure.keyvault")
    _ensure_module("azure.keyvault.secrets")
    azure_kv_aio = _ensure_module("azure.keyvault.secrets.aio")

    class _DummySecretClient:  # pragma: no cover - test helper
        def __init__(self, *args, **kwargs):
            pass

        async def close(self):  # noqa: D401 - mimic async close
            return None

    azure_kv_aio.SecretClient = _DummySecretClient

    azure_identity = _ensure_module("azure.identity")
    azure_identity_aio = _ensure_module("azure.identity.aio")

    class _DummyIdentityCredential:  # pragma: no cover - test helper
        def __init__(self, *args, **kwargs):
            pass

        def get_token(self, *args, **kwargs):
            class _Token:  # minimal token shim
                token = "test-token"

            return _Token()

        async def close(self):
            return None

    azure_identity.ManagedIdentityCredential = _DummyIdentityCredential
    azure_identity.DefaultAzureCredential = _DummyIdentityCredential
    azure_identity_aio.ManagedIdentityCredential = _DummyIdentityCredential
    azure_identity_aio.DefaultAzureCredential = _DummyIdentityCredential
else:
    def _ensure_module(name: str) -> ModuleType:  # pragma: no cover - compatibility shim
        return sys.modules.setdefault(name, ModuleType(name))

_ensure_module("semantic_kernel")
semantic_kernel_kernel = _ensure_module("semantic_kernel.kernel")
semantic_kernel_kernel.Kernel = type("Kernel", (), {})

# Import the current config objects/functions under the mocked env
with patch.dict(os.environ, MOCK_ENV_VARS, clear=False):
    # New codebase: config lives in app_config/config_kernel
    from src.backend.app_config import config as app_config
    from src.backend.config_kernel import Config

# Provide thin wrappers so the old test names still work
def GetRequiredConfig(name: str, default=None):
    return app_config._get_required(name, default)

def GetOptionalConfig(name: str, default: str = ""):
    return app_config._get_optional(name, default)

def GetBoolConfig(name: str) -> bool:
    return app_config._get_bool(name)


# ---- Tests (unchanged semantics) ----

@patch.dict(os.environ, MOCK_ENV_VARS, clear=False)
def test_get_required_config():
    assert GetRequiredConfig("COSMOSDB_ENDPOINT") == MOCK_ENV_VARS["COSMOSDB_ENDPOINT"]

@patch.dict(os.environ, MOCK_ENV_VARS, clear=False)
def test_get_optional_config():
    assert GetOptionalConfig("NON_EXISTENT_VAR", "default_value") == "default_value"
    assert GetOptionalConfig("COSMOSDB_DATABASE", "default_db") == MOCK_ENV_VARS["COSMOSDB_DATABASE"]

@patch.dict(os.environ, MOCK_ENV_VARS, clear=False)
def test_get_bool_config():
    with patch.dict("os.environ", {"FEATURE_ENABLED": "true"}):
        assert GetBoolConfig("FEATURE_ENABLED") is True
    with patch.dict("os.environ", {"FEATURE_ENABLED": "false"}):
        assert GetBoolConfig("FEATURE_ENABLED") is False
    with patch.dict("os.environ", {"FEATURE_ENABLED": "1"}):
        assert GetBoolConfig("FEATURE_ENABLED") is True
    with patch.dict("os.environ", {"FEATURE_ENABLED": "0"}):
        assert GetBoolConfig("FEATURE_ENABLED") is False


@patch.dict(os.environ, MOCK_ENV_VARS, clear=False)
def test_managed_identity_client_id_default_fallback():
    from src.backend import app_config as app_config_module

    reload(app_config_module)
    try:
        assert (
            app_config_module.config.AZURE_MANAGED_IDENTITY_CLIENT_ID
            == MOCK_ENV_VARS["AZURE_CLIENT_ID"]
        )
    finally:
        reload(app_config_module)


def test_managed_identity_client_id_override():
    from src.backend import app_config as app_config_module

    with patch.dict(
        os.environ,
        {
            **MOCK_ENV_VARS,
            "AZURE_MANAGED_IDENTITY_CLIENT_ID": "managed-identity-client",
        },
        clear=False,
    ):
        reload(app_config_module)
        assert (
            app_config_module.config.AZURE_MANAGED_IDENTITY_CLIENT_ID
            == "managed-identity-client"
        )

    # Reload once more to restore the original configuration for downstream tests
    reload(app_config_module)
