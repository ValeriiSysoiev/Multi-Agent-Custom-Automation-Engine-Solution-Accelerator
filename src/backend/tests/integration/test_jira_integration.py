import json
import os
from pathlib import Path

import httpx
import pytest

from services.http_client import AsyncHttpClient
from services.key_vault import KeyVaultService

ARTIFACT_DIR = Path(__file__).resolve().parent / "../../.." / "artifacts" / "jira"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL")
PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "CYB")
ISSUETYPE_VR = os.environ.get("JIRA_VR_ID", "10021")
ASSET_APP_NAME = os.environ.get("JIRA_TEST_APP_NAME")
ASSET_HOST_NAME = os.environ.get("JIRA_TEST_HOST_NAME")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_jira_create_update_transition():
    if not JIRA_BASE_URL:
        pytest.skip("JIRA_BASE_URL not configured")

    vault = KeyVaultService()
    pat = await vault.get_secret("JIRA_PAT")
    headers = {
        "Authorization": f"Basic {pat}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    async with AsyncHttpClient(base_url=JIRA_BASE_URL, default_headers=headers) as client:
        try:
            create_payload = {
                "fields": {
                    "project": {"key": PROJECT_KEY},
                    "issuetype": {"id": ISSUETYPE_VR},
                    "summary": "Integration smoke test",
                    "description": "Created by automated integration test.",
                }
            }
            response = await client.post("/rest/api/3/issue", json=create_payload, expected_status=[201])
            creation = response.json()
            issue_key = creation["key"]
            (ARTIFACT_DIR / "create_issue.json").write_text(json.dumps(creation, indent=2))

            update_payload = {
                "fields": {
                    "customfield_10068": {"value": "High"},
                    "customfield_10073": {"value": "PATCH"},
                }
            }
            await client.put(f"/rest/api/3/issue/{issue_key}", json=update_payload, expected_status=[204])

            async def fetch_asset_objects(query: str) -> list[dict[str, str]]:
                endpoints = ["/gateway/api/assetapi/object/aql", "/rest/assetapi/object/aql"]
                for endpoint in endpoints:
                    try:
                        resp = await client.get(endpoint, params={"query": query}, expected_status=[200])
                        results = resp.json().get("data", [])
                        if results:
                            return [{"id": obj["id"]} for obj in results]
                    except httpx.HTTPStatusError:
                        continue
                return []

            app_objects = await fetch_asset_objects(
                f"objectType=\"Application / Service\" AND Name = \"{ASSET_APP_NAME}\""
            ) if ASSET_APP_NAME else []

            host_objects = await fetch_asset_objects(
                f"objectType=\"Host\" AND Hostname = \"{ASSET_HOST_NAME}\""
            ) if ASSET_HOST_NAME else []

            if app_objects or host_objects:
                asset_update = {
                    "fields": {
                        "customfield_10066": app_objects,
                        "customfield_10065": host_objects,
                    }
                }
                await client.put(f"/rest/api/3/issue/{issue_key}", json=asset_update, expected_status=[204])

            transitions_resp = await client.get(f"/rest/api/3/issue/{issue_key}/transitions", expected_status=[200])
            transitions_data = transitions_resp.json()
            (ARTIFACT_DIR / "transitions.json").write_text(json.dumps(transitions_data, indent=2))

            verified_transition = next(
                (t for t in transitions_data.get("transitions", []) if t["name"].lower() == "verified"),
                None,
            )
            if verified_transition:
                transition_id = verified_transition["id"]
                # Attempt without evidence (should fail)
                with pytest.raises(httpx.HTTPStatusError):
                    await client.post(
                        f"/rest/api/3/issue/{issue_key}/transitions",
                        json={"transition": {"id": transition_id}},
                        expected_status=[204],
                    )

                await client.post(
                    f"/rest/api/3/issue/{issue_key}/transitions",
                    json={
                        "transition": {"id": transition_id},
                        "fields": {"customfield_10075": "Rescan on integration test"},
                    },
                    expected_status=[204],
                )

            closed_transition = next(
                (t for t in transitions_data.get("transitions", []) if t["name"].lower() == "closed"),
                None,
            )
            if closed_transition:
                with pytest.raises(httpx.HTTPStatusError):
                    await client.post(
                        f"/rest/api/3/issue/{issue_key}/transitions",
                        json={"transition": {"id": closed_transition["id"]}},
                        expected_status=[204],
                    )
        finally:
            await vault.close()
