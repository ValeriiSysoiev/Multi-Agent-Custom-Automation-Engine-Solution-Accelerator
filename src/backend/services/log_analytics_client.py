"""Utility for sending custom logs to Azure Log Analytics."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Iterable, Mapping

import aiohttp


logger = logging.getLogger(__name__)


class LogAnalyticsClient:
    """Lightweight client for Azure Monitor Data Collector API."""

    _CONTENT_TYPE = "application/json"
    _API_PATH = "/api/logs"
    _API_VERSION = "2016-04-01"

    def __init__(self, workspace_id: str, shared_key: str, log_type: str) -> None:
        if not workspace_id or not shared_key:
            raise ValueError("workspace_id and shared_key are required for Log Analytics logging")

        self._workspace_id = workspace_id
        self._shared_key = shared_key
        self._log_type = log_type
        self._endpoint = (
            f"https://{workspace_id}.ods.opinsights.azure.com"
            f"{self._API_PATH}?api-version={self._API_VERSION}"
        )

    async def send(self, records: Iterable[Mapping[str, object]]) -> None:
        payload = list(records)
        if not payload:
            return

        body = json.dumps(payload, default=self._serialize)
        timestamp = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        signature = self._build_signature(len(body.encode("utf-8")), timestamp)

        headers = {
            "Content-Type": self._CONTENT_TYPE,
            "Log-Type": self._log_type,
            "x-ms-date": timestamp,
            "Authorization": f"SharedKey {self._workspace_id}:{signature}",
        }

        logger.info(
            "Sending %d waiver metrics record(s) to Log Analytics logType=%s",
            len(payload),
            self._log_type,
        )

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(self._endpoint, data=body, headers=headers) as response:
                    if response.status not in (200, 202):
                        text = await response.text()
                        raise RuntimeError(
                            f"Log Analytics ingestion failed with status {response.status}: {text}"
                        )
                    logger.info(
                        "Log Analytics ingestion succeeded with status %s", response.status
                    )
        except Exception as exc:  # pragma: no cover - network interactions are best-effort
            logger.warning("Failed to push metrics to Log Analytics: %s", exc)

    def _build_signature(self, content_length: int, timestamp: str) -> str:
        string_to_hash = (
            f"POST\n{content_length}\n{self._CONTENT_TYPE}\n"
            f"x-ms-date:{timestamp}\n{self._API_PATH}"
        )
        bytes_to_hash = string_to_hash.encode("utf-8")
        decoded_key = base64.b64decode(self._shared_key)
        encoded_hash = hmac.new(decoded_key, bytes_to_hash, digestmod=hashlib.sha256).digest()
        return base64.b64encode(encoded_hash).decode("utf-8")

    @staticmethod
    def _serialize(value: object) -> object:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        return value


__all__ = ["LogAnalyticsClient"]
