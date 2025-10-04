import os
import sys
from importlib.machinery import ModuleSpec
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Ensure repository and backend paths are importable
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Provide minimal environment configuration expected during imports
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example-openai-endpoint")
os.environ.setdefault("AZURE_AI_SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("AZURE_AI_RESOURCE_GROUP", "rg-test")
os.environ.setdefault("AZURE_AI_PROJECT_NAME", "project-test")
os.environ.setdefault("AZURE_AI_AGENT_ENDPOINT", "https://agents.example.com/")
os.environ.setdefault("COSMOSDB_ENDPOINT", "https://cosmos.test")
os.environ.setdefault("COSMOSDB_DATABASE", "test-db")
os.environ.setdefault("COSMOSDB_CONTAINER", "test-container")
os.environ.setdefault("USER_LOCAL_BROWSER_LANGUAGE", "en-US")


def _create_package(name: str) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = []
    module.__spec__ = ModuleSpec(name=name, loader=None, is_package=True)
    return module


# Stub Azure SDK modules referenced at import time
azure_module = _create_package("azure")
sys.modules.setdefault("azure", azure_module)

azure_ai_module = _create_package("azure.ai")
sys.modules.setdefault("azure.ai", azure_ai_module)
azure_module.ai = azure_ai_module

azure_ai_projects_module = _create_package("azure.ai.projects")
sys.modules.setdefault("azure.ai.projects", azure_ai_projects_module)
azure_ai_module.projects = azure_ai_projects_module

azure_ai_projects_aio_module = _create_package("azure.ai.projects.aio")
sys.modules.setdefault("azure.ai.projects.aio", azure_ai_projects_aio_module)
azure_ai_projects_module.aio = azure_ai_projects_aio_module
azure_ai_projects_aio_module.AIProjectClient = MagicMock()

azure_ai_agents_module = _create_package("azure.ai.agents")
sys.modules.setdefault("azure.ai.agents", azure_ai_agents_module)
azure_ai_module.agents = azure_ai_agents_module

azure_ai_agents_models_module = _create_package("azure.ai.agents.models")
sys.modules.setdefault("azure.ai.agents.models", azure_ai_agents_models_module)
azure_ai_agents_module.models = azure_ai_agents_models_module


class _ResponseFormatJsonSchema:
    def __init__(self, *args, **kwargs):
        pass


class _ResponseFormatJsonSchemaType:
    def __init__(self, **kwargs):
        self.json_schema = kwargs.get("json_schema")


azure_ai_agents_models_module.ResponseFormatJsonSchema = (
    _ResponseFormatJsonSchema
)
azure_ai_agents_models_module.ResponseFormatJsonSchemaType = (
    _ResponseFormatJsonSchemaType
)

azure_cosmos_module = _create_package("azure.cosmos")
sys.modules.setdefault("azure.cosmos", azure_cosmos_module)
azure_module.cosmos = azure_cosmos_module

azure_cosmos_aio_module = _create_package("azure.cosmos.aio")
sys.modules.setdefault("azure.cosmos.aio", azure_cosmos_aio_module)
azure_cosmos_module.aio = azure_cosmos_aio_module
azure_cosmos_aio_module.CosmosClient = MagicMock()

azure_cosmos_partition_key_module = _create_package("azure.cosmos.partition_key")
sys.modules.setdefault("azure.cosmos.partition_key", azure_cosmos_partition_key_module)
azure_cosmos_module.partition_key = azure_cosmos_partition_key_module


class _PartitionKey:
    def __init__(self, *args, **kwargs):
        pass


azure_cosmos_partition_key_module.PartitionKey = _PartitionKey

azure_identity_module = _create_package("azure.identity")
sys.modules.setdefault("azure.identity", azure_identity_module)
azure_module.identity = azure_identity_module
azure_identity_module.ManagedIdentityCredential = MagicMock()
azure_identity_module.DefaultAzureCredential = MagicMock()

azure_identity_aio_module = _create_package("azure.identity.aio")
sys.modules.setdefault("azure.identity.aio", azure_identity_aio_module)
azure_identity_module.aio = azure_identity_aio_module
azure_identity_aio_module.ManagedIdentityCredential = MagicMock()
azure_identity_aio_module.DefaultAzureCredential = MagicMock()

azure_keyvault_module = _create_package("azure.keyvault")
sys.modules.setdefault("azure.keyvault", azure_keyvault_module)
azure_module.keyvault = azure_keyvault_module

azure_keyvault_secrets_module = _create_package("azure.keyvault.secrets")
sys.modules.setdefault("azure.keyvault.secrets", azure_keyvault_secrets_module)
azure_keyvault_module.secrets = azure_keyvault_secrets_module

azure_keyvault_secrets_aio_module = _create_package("azure.keyvault.secrets.aio")
sys.modules.setdefault("azure.keyvault.secrets.aio", azure_keyvault_secrets_aio_module)
azure_keyvault_secrets_module.aio = azure_keyvault_secrets_aio_module
azure_keyvault_secrets_aio_module.SecretClient = MagicMock()

azure_monitor_module = _create_package("azure.monitor")
sys.modules.setdefault("azure.monitor", azure_monitor_module)

azure_monitor_events_module = _create_package("azure.monitor.events")
sys.modules.setdefault("azure.monitor.events", azure_monitor_events_module)
azure_monitor_module.events = azure_monitor_events_module

azure_monitor_events_extension_module = _create_package(
    "azure.monitor.events.extension"
)
sys.modules.setdefault(
    "azure.monitor.events.extension", azure_monitor_events_extension_module
)
azure_monitor_events_module.extension = azure_monitor_events_extension_module
azure_monitor_events_extension_module.track_event = MagicMock()

semantic_kernel_module = _create_package("semantic_kernel")
sys.modules.setdefault("semantic_kernel", semantic_kernel_module)

semantic_kernel_kernel_module = _create_package("semantic_kernel.kernel")
sys.modules.setdefault("semantic_kernel.kernel", semantic_kernel_kernel_module)
semantic_kernel_module.kernel = semantic_kernel_kernel_module


class _Kernel:  # minimal placeholder used by app_config
    pass


semantic_kernel_kernel_module.Kernel = _Kernel

semantic_kernel_functions_module = _create_package("semantic_kernel.functions")
sys.modules.setdefault("semantic_kernel.functions", semantic_kernel_functions_module)
semantic_kernel_module.functions = semantic_kernel_functions_module


class _KernelFunction:
    @staticmethod
    def from_method(method):
        return method


semantic_kernel_functions_module.KernelFunction = _KernelFunction


def _kernel_function_decorator(func=None, **kwargs):
    def decorator(target):
        target.__kernel_function__ = SimpleNamespace(
            description=kwargs.get("description")
        )
        return target

    if func is not None:
        return decorator(func)
    return decorator


semantic_kernel_functions_module.kernel_function = _kernel_function_decorator

semantic_kernel_functions_kernel_function_module = _create_package(
    "semantic_kernel.functions.kernel_function"
)
sys.modules.setdefault(
    "semantic_kernel.functions.kernel_function",
    semantic_kernel_functions_kernel_function_module,
)
semantic_kernel_functions_module.kernel_function_module = (
    semantic_kernel_functions_kernel_function_module
)
semantic_kernel_functions_kernel_function_module.KernelFunction = _KernelFunction

semantic_kernel_functions_kernel_arguments_module = _create_package(
    "semantic_kernel.functions.kernel_arguments"
)
sys.modules.setdefault(
    "semantic_kernel.functions.kernel_arguments",
    semantic_kernel_functions_kernel_arguments_module,
)


class _KernelArguments(dict):
    pass


semantic_kernel_functions_kernel_arguments_module.KernelArguments = (
    _KernelArguments
)

semantic_kernel_agents_module = _create_package("semantic_kernel.agents")
sys.modules.setdefault("semantic_kernel.agents", semantic_kernel_agents_module)
semantic_kernel_module.agents = semantic_kernel_agents_module

semantic_kernel_agents_azure_ai_module = _create_package(
    "semantic_kernel.agents.azure_ai"
)
sys.modules.setdefault(
    "semantic_kernel.agents.azure_ai", semantic_kernel_agents_azure_ai_module
)
semantic_kernel_agents_module.azure_ai = semantic_kernel_agents_azure_ai_module

semantic_kernel_agents_azure_ai_agent_module = _create_package(
    "semantic_kernel.agents.azure_ai.azure_ai_agent"
)
sys.modules.setdefault(
    "semantic_kernel.agents.azure_ai.azure_ai_agent",
    semantic_kernel_agents_azure_ai_agent_module,
)
semantic_kernel_agents_azure_ai_module.azure_ai_agent = (
    semantic_kernel_agents_azure_ai_agent_module
)


class _AzureAIAgent:  # minimal constructor-compatible stub
    def __init__(self, *args, **kwargs):
        pass


semantic_kernel_agents_azure_ai_agent_module.AzureAIAgent = _AzureAIAgent

semantic_kernel_memory_module = _create_package("semantic_kernel.memory")
sys.modules.setdefault("semantic_kernel.memory", semantic_kernel_memory_module)
semantic_kernel_module.memory = semantic_kernel_memory_module

semantic_kernel_memory_memory_record_module = _create_package(
    "semantic_kernel.memory.memory_record"
)
sys.modules.setdefault(
    "semantic_kernel.memory.memory_record",
    semantic_kernel_memory_memory_record_module,
)
semantic_kernel_memory_module.memory_record = (
    semantic_kernel_memory_memory_record_module
)


class _MemoryRecord:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


semantic_kernel_memory_memory_record_module.MemoryRecord = _MemoryRecord

semantic_kernel_memory_store_base_module = _create_package(
    "semantic_kernel.memory.memory_store_base"
)
sys.modules.setdefault(
    "semantic_kernel.memory.memory_store_base",
    semantic_kernel_memory_store_base_module,
)
semantic_kernel_memory_module.memory_store_base = (
    semantic_kernel_memory_store_base_module
)


class _MemoryStoreBase:
    pass


semantic_kernel_memory_store_base_module.MemoryStoreBase = _MemoryStoreBase

semantic_kernel_contents_module = _create_package("semantic_kernel.contents")
sys.modules.setdefault("semantic_kernel.contents", semantic_kernel_contents_module)
semantic_kernel_module.contents = semantic_kernel_contents_module

semantic_kernel_contents_module.ChatMessageContent = MagicMock()
semantic_kernel_contents_module.ChatHistory = MagicMock()
semantic_kernel_contents_module.AuthorRole = MagicMock()

semantic_kernel_kernel_pydantic_module = _create_package(
    "semantic_kernel.kernel_pydantic"
)
sys.modules.setdefault(
    "semantic_kernel.kernel_pydantic", semantic_kernel_kernel_pydantic_module
)


def Field(default=None, *args, **kwargs):  # noqa: N802 - mimic pydantic signature
    return default


class _KernelBaseModel:
    def __init__(self, **data):
        for key, value in data.items():
            setattr(self, key, value)

    def model_dump(self):
        return dict(self.__dict__)

    @classmethod
    def model_validate(cls, data):
        return cls(**data)

    @classmethod
    def model_json_schema(cls):
        return {}


semantic_kernel_kernel_pydantic_module.Field = Field
semantic_kernel_kernel_pydantic_module.KernelBaseModel = _KernelBaseModel

numpy_module = ModuleType("numpy")
sys.modules.setdefault("numpy", numpy_module)
numpy_module.array = MagicMock()
numpy_module.dot = MagicMock(return_value=0.0)
numpy_module.linalg = SimpleNamespace(norm=lambda *_: 1.0)
numpy_module.ndarray = object

# Import after stubbing Azure dependencies
from app_config import config
from kernel_agents.agent_factory import AgentFactory
from models.messages_kernel import AgentType


@pytest.mark.asyncio
async def test_create_all_agents_returns_enum_keys(monkeypatch):
    created_types = []

    async def fake_create_agent(cls, **kwargs):  # type: ignore[override]
        agent_type = kwargs["agent_type"]
        created_types.append(agent_type)
        return f"{agent_type.value}_instance"

    # Patch create_agent to avoid invoking actual Azure dependencies
    monkeypatch.setattr(AgentFactory, "create_agent", classmethod(fake_create_agent))

    # Prevent configuration from creating real clients
    monkeypatch.setattr(config, "get_ai_project_client", lambda: "fake-client")

    agents = await AgentFactory.create_all_agents(
        session_id="session", user_id="user", memory_store=object()
    )

    assert all(isinstance(key, AgentType) for key in agents.keys())
    assert agents[AgentType.GROUP_CHAT_MANAGER] == "Group_Chat_Manager_instance"
    # Ensure every agent type defined in the factory was requested
    assert set(created_types) == set(AgentFactory._agent_classes.keys())
