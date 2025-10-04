"""Client for Qualys VM detection APIs."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, Iterable, List, Optional

import httpx
import xmltodict

logger = logging.getLogger(__name__)

from models.messages_kernel import (
    AssetIdentifier,
    AssetIdentifierType,
    CanonicalFinding,
    FindingLifecycleStatus,
    RawFinding,
    RemediationBucket,
    RiskTier,
    SourceReference,
)

from repositories.canonical_finding_repository import CanonicalFindingRepository
from repositories.raw_finding_repository import RawFindingRepository
from repositories.sync_state_repository import SyncStateRecord, SyncStateRepository
from services.canonical_utils import (
    generate_canonical_id,
    map_qualys_severity,
    make_asset_identifier,
    default_remediation_bucket,
    default_finding_status,
)
from services.dedup_service import DeduplicationService
from services.http_client import AsyncHttpClient
from services.key_vault import KeyVaultService
from services.ingestion_result import IngestionResult

SCANNER_ID = "qualys_vm"
DEFAULT_BASE_URL = "https://qualysapi.qg3.apps.qualys.com"
DEFAULT_TRUNCATION_LIMIT = 10000


def _coerce_lookback_days(raw_value: Optional[str]) -> Optional[int]:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized or normalized.lower() == "all":
        return None
    try:
        days = int(normalized)
    except ValueError as exc:  # pragma: no cover - misconfiguration should surface fast
        raise ValueError("QUALYS_LOOKBACK_DAYS must be an integer or 'all'") from exc
    return days if days > 0 else None


DEFAULT_LOOKBACK_DAYS = _coerce_lookback_days(os.getenv("QUALYS_LOOKBACK_DAYS"))
QUALYS_STATUS_TO_LIFECYCLE = {
    "new": FindingLifecycleStatus.OPEN,
    "active": FindingLifecycleStatus.OPEN,
    "re-opened": FindingLifecycleStatus.REOPENED,
    "fixed": FindingLifecycleStatus.RESOLVED,
}


def _iso_today_minus(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def _normalize_status(value: str) -> str:
    return value.lower().strip()


class QualysClient:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base_url = base_url or DEFAULT_BASE_URL
        self._http: Optional[AsyncHttpClient] = None
        self._auth: Optional[httpx.BasicAuth] = None
        self._vault = KeyVaultService()

    async def _ensure_client(self) -> None:
        if self._http is None:
            headers = {
                "Accept": "application/xml",
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "QualysGuardAPI",
            }
            self._http = AsyncHttpClient(base_url=self._base_url, default_headers=headers)
        if self._auth is None:
            username = await self._vault.get_secret("QUALYS-API-USER")
            password = await self._vault.get_secret("QUALYS-API-PASS")
            self._auth = httpx.BasicAuth(username, password)

    async def close(self) -> None:
        if self._http:
            await self._http.close()
            self._http = None
        await self._vault.close()

    async def fetch_detections(self, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        await self._ensure_client()
        assert self._http is not None and self._auth is not None

        params = {
            "action": "list",
            "truncation_limit": DEFAULT_TRUNCATION_LIMIT,
            "output_format": "XML",
            "show_asset_id": "1",
            "status": "New,Active,Re-Opened,Fixed",
        }
        if since:
            params["vm_scan_since"] = since.strftime("%Y-%m-%d")
        elif DEFAULT_LOOKBACK_DAYS is not None:
            params["vm_scan_since"] = _iso_today_minus(DEFAULT_LOOKBACK_DAYS)

        logger.info(
            "Qualys detection request prepared with params=%s (since=%s default_lookback=%s)",
            {**params, "password": "***"} if "password" in params else params,
            since,
            DEFAULT_LOOKBACK_DAYS,
        )

        response = await self._http.post(
            "/api/2.0/fo/asset/host/vm/detection/",
            data=params,
            auth=self._auth,
            expected_status=[200],
        )
        detections = self._parse_detection_xml(response.text)
        logger.info("Qualys response contained %d detections", len(detections))
        return detections

    def _parse_detection_xml(self, payload: str) -> List[Dict[str, Any]]:
        document = xmltodict.parse(payload)
        response_node = (
            document.get("HOST_LIST_VM_DETECTION_OUTPUT", {}).get("RESPONSE")
            or document.get("SIMPLE_RETURN", {}).get("RESPONSE")
            or {}
        )
        host_list = response_node.get("HOST_LIST", {}).get("HOST", [])
        if isinstance(host_list, dict):
            host_list = [host_list]

        records: List[Dict[str, Any]] = []
        for host in host_list:
            host_identifiers = self._extract_identifiers(host)
            detections = host.get("DETECTION_LIST", {}).get("DETECTION", [])
            if isinstance(detections, dict):
                detections = [detections]
            for detection in detections:
                record = {
                    "host": host,
                    "detection": detection,
                    "asset_identifiers": host_identifiers,
                }
                records.append(record)
        return records

    def _extract_identifiers(self, host: Dict[str, Any]) -> List[AssetIdentifier]:
        identifiers: List[AssetIdentifier] = []
        if ip := host.get("IP"):
            identifiers.append(make_asset_identifier(AssetIdentifierType.IP_ADDRESS, ip, SCANNER_ID))
        if hostname := host.get("DNS"):  # Qualys uses DNS field for hostname
            identifiers.append(make_asset_identifier(AssetIdentifierType.HOSTNAME, hostname, SCANNER_ID))
        if agent_id := host.get("AGENT_ID"):
            identifiers.append(make_asset_identifier(AssetIdentifierType.SCANNER_AGENT_ID, agent_id, SCANNER_ID))
        if host_id := host.get("ID"):
            identifiers.append(make_asset_identifier(AssetIdentifierType.OTHER, str(host_id), SCANNER_ID))
        return identifiers


class QualysIngestionService:
    def __init__(
        self,
        base_url: Optional[str] = None,
        raw_repo: Optional[RawFindingRepository] = None,
        canonical_repo: Optional[CanonicalFindingRepository] = None,
        sync_repo: Optional[SyncStateRepository] = None,
        dedup_service: Optional[DeduplicationService] = None,
    ) -> None:
        self._client = QualysClient(base_url)
        self._raw_repo = raw_repo or RawFindingRepository()
        canonical_repository = canonical_repo or CanonicalFindingRepository()
        self._dedup_service = dedup_service or DeduplicationService(canonical_repository)
        self._sync_repo = sync_repo or SyncStateRepository()

    async def close(self) -> None:
        await self._client.close()

    async def ingest(self) -> IngestionResult:
        state = await self._sync_repo.get_state(SCANNER_ID)
        since = state.last_seen_timestamp if state else None

        detections = await self._client.fetch_detections(since)
        logger.info(
            "Qualys ingestion retrieved %d detections (since=%s)",
            len(detections),
            since,
        )
        if not detections:
            return IngestionResult(scanner_id=SCANNER_ID, processed=0)

        max_timestamp = since
        count = 0
        canonical_records: list[CanonicalFinding] = []

        for record in detections:
            raw = self._map_raw(record)
            canonical = self._map_canonical(record)

            await self._raw_repo.upsert_finding(raw)
            merged = await self._dedup_service.merge(canonical)
            canonical_records.append(merged)

            last_found = record["detection"].get("LAST_FOUND")
            if last_found:
                dt = datetime.strptime(last_found, "%Y-%m-%dT%H:%M:%SZ")
                if max_timestamp is None or dt > max_timestamp:
                    max_timestamp = dt
            count += 1

        if max_timestamp:
            record = SyncStateRecord(
                id=SCANNER_ID,
                scanner_id=SCANNER_ID,
                last_seen_timestamp=max_timestamp,
            )
            await self._sync_repo.upsert_state(record)

        return IngestionResult(scanner_id=SCANNER_ID, processed=count, canonical_findings=canonical_records)

    def _map_raw(self, payload: Dict[str, Any]) -> RawFinding:
        detection = payload["detection"]
        ingestion_id = detection.get("QID")
        last_found = detection.get("LAST_FOUND")
        recorded_at = (
            datetime.strptime(last_found, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if last_found
            else datetime.now(timezone.utc)
        )

        return RawFinding(
            scanner_id=SCANNER_ID,
            ingestion_id=str(ingestion_id),
            asset_identifiers=payload["asset_identifiers"],
            normalized_signature=str(detection.get("QID")),
            recorded_at=recorded_at,
            payload_preview={
                "qid": detection.get("QID"),
                "type": detection.get("TYPE"),
                "status": detection.get("STATUS"),
            },
            redaction_applied=False,
        )

    def _map_canonical(self, payload: Dict[str, Any]) -> CanonicalFinding:
        host = payload["host"]
        detection = payload["detection"]
        asset_id = host.get("ID") or host.get("IP") or host.get("DNS") or "unknown-host"
        asset_identifiers = payload["asset_identifiers"]

        qid = detection.get("QID")
        cve_list = detection.get("CVE_LIST", {})
        cves = cve_list.get("CVE") if isinstance(cve_list, dict) else []
        if isinstance(cves, str):
            cves = [cves]
        vuln_key = (cves[0] if cves else f"QID-{qid}")

        port = detection.get("PORT")
        protocol = detection.get("PROTOCOL")
        service = detection.get("SERVICE")
        location_signature = "|".join(filter(None, [port, protocol, service])) or None

        canonical_id = generate_canonical_id(str(asset_id), vuln_key, location_signature)

        severity_raw = detection.get("SEVERITY")
        try:
            severity_int = int(severity_raw)
        except (TypeError, ValueError):
            severity_int = 3

        risk_tier = map_qualys_severity(severity_int)
        lifecycle = QUALYS_STATUS_TO_LIFECYCLE.get(
            _normalize_status(detection.get("STATUS", "active")),
            FindingLifecycleStatus.OPEN,
        )

        first_found = detection.get("FIRST_FOUND")
        last_found = detection.get("LAST_FOUND")
        first_observed = datetime.strptime(first_found, "%Y-%m-%dT%H:%M:%SZ") if first_found else None
        last_observed = datetime.strptime(last_found, "%Y-%m-%dT%H:%M:%SZ") if last_found else first_observed

        source_reference = SourceReference(
            scanner_id=SCANNER_ID,
            external_id=str(qid),
            first_seen=first_observed or datetime.now(timezone.utc),
            last_seen=last_observed or datetime.now(timezone.utc),
            severity=str(severity_int),
            raw_finding_id=str(qid),
            status=detection.get("STATUS"),
        )

        return CanonicalFinding(
            id=canonical_id,
            canonical_id=canonical_id,
            asset_id=str(asset_id),
            asset_identifiers=asset_identifiers,
            sources=[source_reference],
            vuln_key=vuln_key,
            severity=str(severity_int),
            risk_tier=risk_tier,
            status=lifecycle,
            remediation_bucket=default_remediation_bucket(),
            description=detection.get("RESULTS"),
            recommendations=detection.get("SOLUTION"),
            first_observed=first_observed,
            last_observed=last_observed,
        )
