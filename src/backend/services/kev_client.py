"""Lightweight client for the CISA KEV feed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from services.http_client import build_default_client

FEED_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
CACHE_WINDOW = timedelta(hours=6)


class KevClient:
    """Fetch and cache CISA Known Exploited Vulnerabilities feed."""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._expires_at: Optional[datetime] = None

    async def lookup(self, cve: str) -> Optional[Dict[str, Any]]:
        cve_norm = (cve or "").upper()
        if not cve_norm.startswith("CVE-"):
            return None

        await self._ensure_feed()
        return self._cache.get(cve_norm)

    async def _ensure_feed(self) -> None:
        now = datetime.now(timezone.utc)
        if self._expires_at and self._expires_at > now:
            return

        async with build_default_client() as client:
            response = await client.get(FEED_URL, expected_status=[200])
            payload = response.json()

        entries = payload.get("vulnerabilities") or payload.get("vulnerabilities_list") or payload.get("vulnerabilitiesCatalog")
        cache: Dict[str, Dict[str, Any]] = {}
        if isinstance(entries, list):
            for entry in entries:
                cve_id = (entry.get("cveID") or entry.get("cve") or "").upper()
                if cve_id:
                    cache[cve_id] = entry

        self._cache = cache
        self._expires_at = now + CACHE_WINDOW
