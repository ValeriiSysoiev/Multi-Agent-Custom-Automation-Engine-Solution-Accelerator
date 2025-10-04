"""Unit tests for DefenderMdcClient sub-assessment link handling."""

import os
import sys
from types import MethodType

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

try:  # pragma: no branch - prefer installed SDKs
    import azure.identity  # type: ignore
    import azure.identity.aio  # type: ignore
    import azure.cosmos.aio  # type: ignore
    import azure.cosmos.exceptions  # type: ignore
    import azure.keyvault.secrets.aio  # type: ignore
    import azure.core.exceptions  # type: ignore
    import azure.ai.projects.aio  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback shims for local testing
    import types

    def _ensure_module(name: str):
        return sys.modules.setdefault(name, types.ModuleType(name))

    _ensure_module("azure")
    azure_ai_projects_aio = _ensure_module("azure.ai.projects.aio")

    class _DummyAIProjectClient:
        async def close(self) -> None:
            return

    azure_ai_projects_aio.AIProjectClient = _DummyAIProjectClient

    azure_identity_module = _ensure_module("azure.identity")
    azure_identity_aio_module = _ensure_module("azure.identity.aio")

    class _DummyCredential:
        def __init__(self, *args, **kwargs):
            pass

        async def close(self) -> None:
            return

    azure_identity_module.ManagedIdentityCredential = _DummyCredential
    azure_identity_module.DefaultAzureCredential = _DummyCredential
    azure_identity_aio_module.ManagedIdentityCredential = _DummyCredential
    azure_identity_aio_module.DefaultAzureCredential = _DummyCredential

    azure_cosmos_aio = _ensure_module("azure.cosmos.aio")
    azure_cosmos_exceptions = _ensure_module("azure.cosmos.exceptions")

    class _DummyContainerProxy:
        pass

    class _DummyCosmosClient:
        pass

    class _DummyCosmosError(Exception):
        pass

    azure_cosmos_aio.ContainerProxy = _DummyContainerProxy
    azure_cosmos_aio.CosmosClient = _DummyCosmosClient
    azure_cosmos_exceptions.CosmosResourceNotFoundError = _DummyCosmosError

    azure_keyvault_secrets_aio = _ensure_module("azure.keyvault.secrets.aio")

    class _DummySecretClient:
        async def close(self) -> None:
            return

    azure_keyvault_secrets_aio.SecretClient = _DummySecretClient

    azure_core_exceptions = _ensure_module("azure.core.exceptions")

    class _DummyResourceNotFoundError(Exception):
        pass

    azure_core_exceptions.ResourceNotFoundError = _DummyResourceNotFoundError

from services.defender_mdc_client import DefenderMdcClient


def test_normalize_link_preserves_query_params() -> None:
    client = DefenderMdcClient("00000000-0000-0000-0000-000000000000")

    link, params = client._normalize_subassessment_link(
        "/subscriptions/00000000-0000-0000-0000-000000000000"
        "/providers/Microsoft.Security/assessments/example/subAssessments"
        "?api-version=2021-06-01&$top=50"
    )

    assert link == (
        "/subscriptions/00000000-0000-0000-0000-000000000000"
        "/providers/Microsoft.Security/assessments/example/subAssessments"
    )
    assert params == {"api-version": "2021-06-01", "$top": "50"}


def test_normalize_link_builds_path_from_identifier() -> None:
    client = DefenderMdcClient("11111111-2222-3333-4444-555555555555")

    link, params = client._normalize_subassessment_link("assessment-id")

    assert link == (
        "/subscriptions/11111111-2222-3333-4444-555555555555"
        "/providers/Microsoft.Security/assessments/assessment-id/subAssessments"
    )
    assert params == {}


def test_normalize_link_handles_absolute_url() -> None:
    client = DefenderMdcClient("sub-id")

    link, params = client._normalize_subassessment_link(
        "https://management.azure.com/subscriptions/sub-id/providers/Microsoft.Security/"
        "assessments/sample?api-version=2020-01-01"
    )

    assert link == (
        "https://management.azure.com/subscriptions/sub-id/providers/Microsoft.Security/"
        "assessments/sample/subAssessments"
    )
    assert params == {"api-version": "2020-01-01"}


def test_normalize_link_decodes_securityentitydata_path() -> None:
    client = DefenderMdcClient("66e84420-9ef4-4264-aedb-7beacbfe9e81")

    raw_link = (
        "/providers/Microsoft.Security/securityentitydata/containerregistry/"
        "%2Fsubscriptions%2F66e84420-9ef4-4264-aedb-7beacbfe9e81%2FresourceGroups%2FRG-AIVM"
        "%2Fproviders%2FMicrosoft.ContainerRegistry%2Fregistries%2Facraivmprod"
    )

    link, params = client._normalize_subassessment_link(raw_link)

    assert link == (
        "/providers/Microsoft.Security/securityentitydata/containerregistry/"
        "%2Fsubscriptions%2F66e84420-9ef4-4264-aedb-7beacbfe9e81%2FresourceGroups%2FRG-AIVM"
        "%2Fproviders%2FMicrosoft.ContainerRegistry%2Fregistries%2Facraivmprod/subAssessments"
    )
    assert params == {}

def test_normalize_container_registry_link_preserves_encoding() -> None:
    client = DefenderMdcClient("00000000-0000-0000-0000-000000000000")

    encoded_link = (
        "https://management.azure.com/providers/Microsoft.Security/securityEntityData/"
        "containerregistry/subscriptions%2F0000/resourceGroups%2Ffoo/providers%2F"
        "Microsoft.ContainerRegistry%2Fregistries%2Fbar/subAssessments"
    )

    link, params = client._normalize_subassessment_link(encoded_link)

    assert "%2F" in link  # encoding preserved
    assert link.endswith("/subAssessments")
    assert params == {}


@pytest.mark.asyncio
async def test_list_sub_assessments_skips_container_ids() -> None:
    client = DefenderMdcClient("00000000-0000-0000-0000-000000000000")

    async def failing_paginate(*args, **kwargs):  # pragma: no cover - should not be invoked
        raise AssertionError("container assessments should be skipped before pagination")

    client._paginate = MethodType(failing_paginate, client)

    results = await client.list_sub_assessments(
        None,
        assessment_ids=[
            "/providers/Microsoft.Security/securityEntityData/containerregistry/foo/subAssessments"
        ],
    )

    assert results == []


@pytest.mark.asyncio
async def test_list_sub_assessments_skips_container_assessments_from_feed() -> None:
    client = DefenderMdcClient("00000000-0000-0000-0000-000000000000")

    async def paginate_stub(self, url, *, params=None, timeout=None, allow_version_fallback=False):
        if "subAssessments" in url and "securityentitydata" in url.lower():
            raise AssertionError("container assessments should be skipped before pagination")
        if url.endswith("/assessments"):
            yield {
                "name": "20606e75-05c4-48c0-9d97-add6daa2109a",
                "properties": {
                    "additionalData": {
                        "subAssessmentsLink": "/providers/Microsoft.Security/securityEntityData/"
                        "containerregistry/example/subAssessments"
                    }
                },
            }

    client._paginate = MethodType(paginate_stub, client)

    results = await client.list_sub_assessments(None)

    assert results == []


@pytest.mark.asyncio
async def test_paginate_treats_404_as_empty(monkeypatch) -> None:
    client = DefenderMdcClient("sub-id")

    async def request_stub(self, method, url, **kwargs):  # pragma: no cover - stubbed behaviour
        response = httpx.Response(404, request=httpx.Request(method, url))
        raise httpx.HTTPStatusError("404", request=response.request, response=response)

    client._request = MethodType(request_stub, client)

    collected = [item async for item in client._paginate("/foo", params={}, allow_version_fallback=True)]
    assert collected == []
