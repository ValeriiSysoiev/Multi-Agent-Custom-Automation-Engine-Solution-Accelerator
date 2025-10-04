"""Power BI client for dataset refresh operations."""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Sequence

import msal

from services.http_client import AsyncHttpClient

logger = logging.getLogger(__name__)

_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
_API_BASE = "https://api.powerbi.com/v1.0/myorg"


class PowerBIClient:
    """Wrapper around MSAL + Power BI REST API for dataset refreshes."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        self._app = msal.ConfidentialClientApplication(
            client_id=client_id,
            authority=authority,
            client_credential=client_secret,
        )

    def _acquire_token(self) -> str:
        result = self._app.acquire_token_silent(_SCOPE, account=None)
        if not result:
            result = self._app.acquire_token_for_client(scopes=_SCOPE)
        if "access_token" not in result:
            error = result.get("error_description") or result
            raise RuntimeError(f"Power BI token acquisition failed: {error}")
        return result["access_token"]

    async def trigger_refresh(self, workspace_id: str, dataset_id: str) -> bool:
        token = self._acquire_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        client = AsyncHttpClient(base_url=_API_BASE, default_headers=headers)
        try:
            await client.post(
                f"/groups/{workspace_id}/datasets/{dataset_id}/refreshes",
                json={"notifyOption": "NoNotification"},
                expected_status=[200, 202],
            )
            return True
        finally:
            await client.close()

    async def create_push_dataset(
        self,
        workspace_id: str,
        dataset_name: str,
        tables: Sequence[dict],
    ) -> str:
        """Create a push dataset and return its ID."""

        token = self._acquire_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        client = AsyncHttpClient(base_url=_API_BASE, default_headers=headers)
        try:
            response = await client.post(
                f"/groups/{workspace_id}/datasets",
                json={
                    "name": dataset_name,
                    "defaultMode": "Push",
                    "tables": list(tables),
                },
                expected_status=[201],
            )
            return response.json()["id"]
        finally:
            await client.close()

    async def replace_rows(
        self,
        workspace_id: str,
        dataset_id: str,
        table_name: str,
        rows: Iterable[dict],
    ) -> None:
        """Replace all rows in a push dataset table."""

        rows = list(rows)
        token = self._acquire_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        client = AsyncHttpClient(base_url=_API_BASE, default_headers=headers)
        try:
            await client.delete(
                f"/groups/{workspace_id}/datasets/{dataset_id}/tables/{table_name}/rows",
                expected_status=[200],
            )
            if not rows:
                return

            chunk: List[dict] = []
            for row in rows:
                chunk.append(row)
                if len(chunk) >= 10000:
                    await client.post(
                        f"/groups/{workspace_id}/datasets/{dataset_id}/tables/{table_name}/rows",
                        json={"rows": chunk},
                        expected_status=[200],
                    )
                    chunk = []
            if chunk:
                await client.post(
                    f"/groups/{workspace_id}/datasets/{dataset_id}/tables/{table_name}/rows",
                    json={"rows": chunk},
                    expected_status=[200],
                )
        finally:
            await client.close()


__all__ = ["PowerBIClient"]
