"""Client for FIRST.org EPSS scores."""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.http_client import build_default_client

EPSS_URL = "https://api.first.org/data/v1/epss"


class EpssClient:
    """Retrieve EPSS probability scores for CVEs."""

    async def get_score(self, cve: str) -> Optional[Dict[str, Any]]:
        cve_norm = (cve or "").upper()
        if not cve_norm.startswith("CVE-"):
            return None

        params = {"cve": cve_norm}
        async with build_default_client() as client:
            response = await client.get(EPSS_URL, params=params, expected_status=[200])
            payload = response.json()

        data = payload.get("data")
        if isinstance(data, list) and data:
            entry = data[0]
            if entry.get("cve"):
                return entry
        return None
