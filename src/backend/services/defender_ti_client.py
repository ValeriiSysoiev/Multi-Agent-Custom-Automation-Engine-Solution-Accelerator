"""Client for Microsoft Defender Threat Intelligence vulnerability data."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from azure.identity.aio import DefaultAzureCredential
from models.messages_kernel import ConfidenceLevel, ThreatSignal

from services.http_client import AsyncHttpClient

logger = logging.getLogger(__name__)

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_BASE_URL = "https://graph.microsoft.com"


class DefenderTIClient:
    """Fetch vulnerability intelligence from Microsoft Defender Threat Intelligence."""

    def __init__(self) -> None:
        self._http: Optional[AsyncHttpClient] = None
        self._credential: Optional[DefaultAzureCredential] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        if self._http:
            await self._http.close()
            self._http = None
        if self._credential:
            await self._credential.close()
            self._credential = None

    async def get_vulnerability(self, cve_id: str) -> Optional[Dict[str, Any]]:
        cve_norm = (cve_id or "").upper()
        if not cve_norm.startswith("CVE-"):
            return None

        if cve_norm in self._cache:
            return self._cache[cve_norm]

        async with self._lock:
            if cve_norm in self._cache:
                return self._cache[cve_norm]
            payload = await self._fetch_vulnerability(cve_norm)
            if payload:
                self._cache[cve_norm] = payload
            return payload

    async def _ensure_clients(self) -> None:
        if self._http is None:
            self._http = AsyncHttpClient(base_url=GRAPH_BASE_URL)
        if self._credential is None:
            self._credential = DefaultAzureCredential()

    async def _get_token(self) -> str:
        await self._ensure_clients()
        assert self._credential is not None
        token = await self._credential.get_token(GRAPH_SCOPE)
        return token.token

    async def _fetch_vulnerability(self, cve: str) -> Optional[Dict[str, Any]]:
        await self._ensure_clients()
        assert self._http is not None

        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "ConsistencyLevel": "eventual",
        }
        params = {
            "$filter": f"cveNumber eq '{cve}'",
            "$top": 1,
        }

        try:
            response = await self._http.get(
                "/beta/security/threatIntelligence/vulnerabilities",
                headers=headers,
                params=params,
                expected_status=[200],
            )
        except Exception as exc:  # broad to surface permission issues in logs
            logger.warning("Defender TI request failed for %s: %s", cve, exc)
            return None

        payload = response.json()
        items = payload.get("value")
        if isinstance(items, list) and items:
            return items[0]
        return None

    def to_threat_signal(self, payload: Dict[str, Any]) -> ThreatSignal:
        """Map Defender TI payload into a ThreatSignal structure."""

        details = {
            "description": payload.get("description"),
            "severity": payload.get("severity"),
            "exploitation": payload.get("exploitation"),
            "publicExploit": payload.get("publicExploit"),
            "lastUpdatedDateTime": payload.get("lastUpdatedDateTime"),
            "threatTypes": payload.get("threatTypes"),
        }
        confidence = ConfidenceLevel.MEDIUM
        if payload.get("exploitation") and str(payload["exploitation"]).lower() == "active":
            confidence = ConfidenceLevel.HIGH
        return ThreatSignal(
            source="defender_ti",
            signal_type="vulnerability_intel",
            confidence=confidence,
            details={k: v for k, v in details.items() if v is not None},
        )
