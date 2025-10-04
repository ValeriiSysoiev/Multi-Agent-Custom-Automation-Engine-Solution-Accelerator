import asyncio
import os
import sys
from typing import Any, Dict
from unittest.mock import AsyncMock

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
os.environ.setdefault("JIRA_ASSETS_WORKSPACE_ID", "workspace-123")
os.environ.setdefault("JIRA_ASSET_HOSTS_FIELD", "customfield_10120")
os.environ.setdefault("JIRA_APPLICATION_ASSET_FIELD", "customfield_10121")

from services.jira_ticket_client import JiraTicketClient


class FakeResponse:
    def __init__(self, payload: Dict[str, Any]):
        self._payload = payload

    def json(self) -> Dict[str, Any]:
        return self._payload


class FakeHttpClient:
    def __init__(self, *, summary: str = "", description: Dict[str, Any] | None = None) -> None:
        self.summary = summary
        self.description = description or {"type": "doc", "version": 1, "content": []}
        self.get_calls: list[tuple[str, Dict[str, Any] | None]] = []
        self.put_calls: list[Dict[str, Any]] = []

    async def get(self, path: str, *, params: Dict[str, Any] | None = None, expected_status: list[int]) -> FakeResponse:  # noqa: D401
        self.get_calls.append((path, params))
        return FakeResponse({"fields": {"summary": self.summary, "description": self.description}})

    async def put(self, path: str, *, json: Dict[str, Any], expected_status: list[int]) -> FakeResponse:  # noqa: D401
        self.put_calls.append({"path": path, "json": json})
        return FakeResponse({})


def _build_client(fake_http: FakeHttpClient) -> JiraTicketClient:
    client = JiraTicketClient.__new__(JiraTicketClient)
    client._base_url = "https://example.atlassian.net"
    client._vault = None
    client._http = fake_http
    client._auth_header = "Basic test"
    client._lock = asyncio.Lock()
    client._project_key = "CYB"
    client._issue_type_id = "10021"
    client._waiver_issue_type_id = "10022"
    client._verification_field = "customfield_10075"
    client._waiver_status_field = "customfield_10084"
    client._waiver_expiry_field = "customfield_10083"
    client._verified_transition = "Verified"
    client._reopen_transition = "Reopen"
    client._asset_hosts_field = os.getenv("JIRA_ASSET_HOSTS_FIELD", "customfield_10120")
    client._asset_apps_field = os.getenv("JIRA_APPLICATION_ASSET_FIELD", "customfield_10121")
    client._assets_workspace_id = os.getenv("JIRA_ASSETS_WORKSPACE_ID", "workspace-123")
    client._ensure_client = AsyncMock()  # type: ignore[attr-defined]
    return client


@pytest.mark.asyncio
async def test_update_issue_fields_injects_required_fields() -> None:
    fake_http = FakeHttpClient(summary="Existing summary")
    client = _build_client(fake_http)

    await client.update_issue_fields("CYB-42", {"customfield_10120": ["workspace-456:13-123"]})

    assert fake_http.get_calls == [
        ("/rest/api/3/issue/CYB-42", {"fields": "summary,description"})
    ]
    assert fake_http.put_calls, "Expected PUT request to be issued"
    payload = fake_http.put_calls[0]["json"]["fields"]
    assert payload["summary"] == "Existing summary"
    assert payload["description"] == fake_http.description
    assert payload["customfield_10120"] == [
        {
            "workspaceId": "workspace-456",
            "id": "workspace-456:13-123",
            "objectId": "13-123",
        }
    ]


@pytest.mark.asyncio
async def test_update_issue_fields_handles_global_id_values() -> None:
    fake_http = FakeHttpClient(summary="Existing summary")
    client = _build_client(fake_http)

    global_id = "ari:cloud:jira-asset::object/123"
    await client.update_issue_fields("CYB-43", {"customfield_10120": [global_id]})

    payload = fake_http.put_calls[-1]["json"]["fields"]
    assert payload["customfield_10120"] == [{"globalId": global_id}]


@pytest.mark.asyncio
async def test_update_issue_fields_skips_fetch_when_summary_and_description_present() -> None:
    fake_http = FakeHttpClient()
    client = _build_client(fake_http)

    await client.update_issue_fields(
        "CYB-7",
        {
            "summary": "Updated summary",
            "description": "Updated description",
            "customfield_10069": 42,
            "customfield_10121": ["11-456"],
        },
    )

    assert fake_http.get_calls == []
    payload = fake_http.put_calls[0]["json"]["fields"]
    assert payload["summary"] == "Updated summary"
    assert payload["description"]["type"] == "doc"
    assert payload["customfield_10069"] == 42
    assert payload["customfield_10121"] == [
        {
            "workspaceId": "workspace-123",
            "id": "11-456",
            "objectId": "11-456",
        }
    ]
