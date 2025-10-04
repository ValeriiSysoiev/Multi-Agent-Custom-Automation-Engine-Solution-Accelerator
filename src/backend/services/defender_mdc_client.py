"""Client for Microsoft Defender for Cloud assessments/sub-assessments."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urlparse

import httpx

from azure.identity.aio import DefaultAzureCredential

from models.messages_kernel import (
    AssetIdentifier,
    AssetIdentifierType,
    CanonicalFinding,
    DataType,
    FindingLifecycleStatus,
    RawFinding,
    RemediationBucket,
    RiskTier,
    SourceReference,
)

from repositories.canonical_finding_repository import CanonicalFindingRepository
from repositories.raw_finding_repository import RawFindingRepository
from repositories.sync_state_repository import SyncStateRepository
from models.messages_kernel import SyncStateRecord
from services.canonical_utils import (
    generate_canonical_id,
    map_severity_to_risk_tier,
    normalize_severity,
    default_remediation_bucket,
    make_asset_identifier,
)
from services.http_client import AsyncHttpClient, DEFAULT_CONNECT_TIMEOUT
from services.dedup_service import DeduplicationService
from services.ingestion_result import IngestionResult

SCANNER_ID = "defender_mdc"
DEFAULT_API_VERSIONS = [
    "2025-05-04",
    "2021-06-01",
    "2020-01-01",
    "2019-01-01-preview",
]
TOKEN_SCOPE = "https://management.azure.com/.default"
BASE_URL = "https://management.azure.com"
MAX_ASSESSMENTS = 20
MAX_SUB_ASSESSMENTS = 500


logger = logging.getLogger(__name__)


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class DefenderMdcClient:
    """Thin wrapper over the Defender for Cloud REST API."""

    def __init__(
        self,
        subscription_id: str,
        *,
        api_versions: Optional[Iterable[str]] = None,
    ) -> None:
        self._subscription_id = subscription_id
        self._api_versions = list(api_versions or DEFAULT_API_VERSIONS)
        self._http: Optional[AsyncHttpClient] = None
        self._credential: Optional[DefaultAzureCredential] = None
        self._api_version_resolved: Optional[str] = None
        self._lock = asyncio.Lock()

    async def _ensure_clients(self) -> None:
        if self._http is None:
            self._http = AsyncHttpClient(base_url=BASE_URL)
        if self._credential is None:
            self._credential = DefaultAzureCredential()

    async def close(self) -> None:
        if self._http:
            await self._http.close()
            self._http = None
        if self._credential:
            await self._credential.close()
            self._credential = None

    async def _get_token(self) -> str:
        await self._ensure_clients()
        assert self._credential is not None
        token = await self._credential.get_token(TOKEN_SCOPE)
        return token.token

    async def _request(self, method: str, url: str, **kwargs: Any) -> Dict[str, Any]:
        await self._ensure_clients()
        assert self._http is not None
        token = await self._get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        response = await self._http.request(method, url, headers=headers, expected_status=[200], **kwargs)
        return response.json()

    async def _resolve_api_version(self) -> str:
        if self._api_version_resolved:
            return self._api_version_resolved

        async with self._lock:
            if self._api_version_resolved:
                return self._api_version_resolved

            for version in self._api_versions:
                url = f"/subscriptions/{self._subscription_id}/providers/Microsoft.Security/assessments"
                params = {"api-version": version, "$top": 1}
                try:
                    await self._request("GET", url, params=params)
                    self._api_version_resolved = version
                    break
                except Exception:
                    continue

            if not self._api_version_resolved:
                raise RuntimeError("Unable to resolve Defender API version")

            return self._api_version_resolved

    async def _paginate(
        self,
        url: str,
        *,
        params: Dict[str, Any],
        timeout: float | None = None,
        allow_version_fallback: bool = False,
    ) -> AsyncIterator[Dict[str, Any]]:
        base_params = {k: v for k, v in dict(params).items() if v is not None}
        target_url = url
        versions: List[str]
        if allow_version_fallback:
            versions = list(dict.fromkeys(self._api_versions))
        else:
            resolved = await self._resolve_api_version()
            versions = [resolved]

        last_exc: Optional[httpx.HTTPStatusError] = None

        for version in versions:
            next_url: Optional[str] = url
            request_params = dict(base_params)
            if "api-version" not in request_params:
                request_params["api-version"] = version

            while next_url:
                request_kwargs: Dict[str, Any] = {"params": request_params}
                if timeout:
                    request_kwargs["timeout"] = httpx.Timeout(
                        connect=DEFAULT_CONNECT_TIMEOUT,
                        read=timeout,
                        write=None,
                        pool=None,
                    )
                try:
                    payload = await self._request("GET", next_url, **request_kwargs)
                except httpx.HTTPStatusError as exc:
                    if allow_version_fallback and exc.response.status_code == 404:
                        logger.debug(
                            "Defender sub-assessment 404 for %s with api-version %s; attempting fallback",
                            next_url,
                            version,
                        )
                        last_exc = exc
                        break
                    raise

                for item in payload.get("value", []):
                    yield item

                next_url = payload.get("nextLink")
                request_params = {}

            else:
                return

        if last_exc:
            if last_exc.response is not None and last_exc.response.status_code == 404:
                logger.warning(
                    "Defender API returned 404 for %s with versions %s; treating as empty result",
                    url,
                    versions,
                )
                return
            raise last_exc

    async def list_sub_assessments(
        self,
        since: Optional[datetime] = None,
        *,
        assessment_ids: Optional[Iterable[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        effective_limit = limit or MAX_SUB_ASSESSMENTS

        if assessment_ids:
            for assessment_id in assessment_ids:
                if not assessment_id:
                    continue
                if "securityentitydata" in str(assessment_id).lower():
                    # Temporary guard: Defender container registry assessments currently 404.
                    # Remove once Microsoft resolves the API defect (tracked via support ticket).
                    logger.warning(
                        "Skipping Defender container assessment %s due to known Microsoft 404 defect",
                        assessment_id,
                    )
                    continue
                link, query_params = self._normalize_subassessment_link(str(assessment_id))
                try:
                    async for sub in self._paginate(
                        link,
                        params=query_params,
                        timeout=60,
                        allow_version_fallback=True,
                    ):
                        if since:
                            time_generated = sub.get("properties", {}).get("timeGenerated")
                            if time_generated and _parse_datetime(time_generated) < since:
                                continue
                        results.append(sub)
                        if len(results) >= effective_limit:
                            return results
                except httpx.HTTPError as exc:
                    logger.warning(
                        "Defender sub-assessment request failed for %s: %s", link, exc
                    )
                    continue
            return results

        count_assessments = 0
        async for assessment in self._paginate(
            f"/subscriptions/{self._subscription_id}/providers/Microsoft.Security/assessments",
            params={"$top": MAX_ASSESSMENTS},
            timeout=120,
        ):
            props = assessment.get("properties", {})
            name = assessment.get("name")
            if not name:
                continue
            count_assessments += 1
            if count_assessments > MAX_ASSESSMENTS:
                break

            sub_link = props.get("additionalData", {}).get("subAssessmentsLink")
            if not sub_link:
                sub_link = assessment.get("id")
            if not sub_link:
                sub_link = name

            if sub_link and "securityentitydata" in str(sub_link).lower():
                # Temporary guard mirroring assessment_ids handling above.
                logger.warning(
                    "Skipping Defender container assessment %s due to known Microsoft 404 defect",
                    sub_link,
                )
                continue
            sub_link, query_params = self._normalize_subassessment_link(str(sub_link))

            try:
                async for sub in self._paginate(
                    sub_link,
                    params=query_params,
                    timeout=120,
                    allow_version_fallback=True,
                ):
                    if since:
                        time_generated = sub.get("properties", {}).get("timeGenerated")
                        if time_generated and _parse_datetime(time_generated) < since:
                            continue
                    results.append(sub)
                    if len(results) >= effective_limit:
                        return results
            except httpx.HTTPError as exc:
                logger.warning(
                    "Defender sub-assessment request failed for %s: %s", sub_link, exc
                )
                continue

        return results

    def _normalize_subassessment_link(self, link: str) -> Tuple[str, Dict[str, Any]]:
        """Ensure sub-assessment requests use a valid resource path and preserve query arguments."""

        if not link:
            raise ValueError("Assessment link cannot be empty")

        parsed = urlparse(link)
        query_params: Dict[str, Any] = dict(parse_qsl(parsed.query))
        path = parsed.path or link

        stripped_path = path.lstrip("/")
        if stripped_path.startswith("subscriptions/") or stripped_path.startswith("providers/"):
            path = f"/{stripped_path}"
        else:
            path = (
                f"/subscriptions/{self._subscription_id}"
                f"/providers/Microsoft.Security/assessments/{path}"
            )

        if "securityentitydata" in path.lower():
            normalized_path = path.rstrip("/")
        else:
            normalized_path = unquote(path).rstrip("/")

        if not normalized_path.lower().endswith("/subassessments"):
            normalized_path = f"{normalized_path}/subAssessments"
        normalized_path = normalized_path.replace("//sub", "/sub")

        if parsed.scheme and parsed.netloc:
            url = f"{parsed.scheme}://{parsed.netloc}{normalized_path}"
        else:
            url = normalized_path

        return url, query_params


class DefenderIngestionService:
    """Coordinates ingestion from Defender for Cloud into Cosmos."""

    def __init__(
        self,
        subscription_id: str,
        raw_repo: Optional[RawFindingRepository] = None,
        canonical_repo: Optional[CanonicalFindingRepository] = None,
        sync_repo: Optional[SyncStateRepository] = None,
        api_versions: Optional[Iterable[str]] = None,
        dedup_service: Optional[DeduplicationService] = None,
    ) -> None:
        self._client = DefenderMdcClient(subscription_id, api_versions=api_versions)
        self._raw_repo = raw_repo or RawFindingRepository()
        canonical_repository = canonical_repo or CanonicalFindingRepository()
        self._dedup_service = dedup_service or DeduplicationService(canonical_repository)
        self._sync_repo = sync_repo or SyncStateRepository()

    async def close(self) -> None:
        await self._client.close()

    async def ingest(
        self,
        *,
        assessment_filter: Optional[Iterable[str]] = None,
        max_items: Optional[int] = None,
    ) -> IngestionResult:
        state = await self._sync_repo.get_state(SCANNER_ID)
        since = state.last_seen_timestamp if state else None

        sub_assessments = await self._client.list_sub_assessments(
            since,
            assessment_ids=assessment_filter,
            limit=max_items,
        )
        if not sub_assessments:
            return IngestionResult(scanner_id=SCANNER_ID, processed=0)

        max_timestamp = since
        count = 0
        canonical_records: list[CanonicalFinding] = []

        for sub in sub_assessments:
            raw = self._map_raw(sub)
            canonical = self._map_canonical(sub)

            await self._raw_repo.upsert_finding(raw)
            merged = await self._dedup_service.merge(canonical)
            canonical_records.append(merged)

            time_generated = sub.get("properties", {}).get("timeGenerated")
            if time_generated:
                dt = _parse_datetime(time_generated)
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

        return IngestionResult(
            scanner_id=SCANNER_ID,
            processed=count,
            canonical_findings=canonical_records,
        )

    def _map_raw(self, payload: Dict[str, Any]) -> RawFinding:
        props = payload.get("properties", {})
        time_generated = props.get("timeGenerated")
        ingestion_id = payload.get("id") or payload.get("name")
        resource_id = (
            props.get("resourceDetails", {}).get("id")
            or props.get("resourceDetails", {}).get("source")
            or "unknown-resource"
        )
        asset_identifier = make_asset_identifier(
            AssetIdentifierType.CLOUD_RESOURCE_ID,
            resource_id,
            source=SCANNER_ID,
        )

        fallback_ingestion_id = generate_canonical_id(
            "defender", payload.get("name", "")
        )

        return RawFinding(
            scanner_id=SCANNER_ID,
            ingestion_id=ingestion_id or fallback_ingestion_id,
            asset_identifiers=[asset_identifier],
            normalized_signature=payload.get("name", "defender-subassessment"),
            recorded_at=
                _parse_datetime(time_generated)
                if time_generated
                else datetime.now(timezone.utc),
            payload_preview={
                "name": payload.get("name"),
                "assessmentKey": props.get("assessmentKey"),
                "status": props.get("status"),
            },
            redaction_applied=False,
        )

    def _map_canonical(self, payload: Dict[str, Any]) -> CanonicalFinding:
        props = payload.get("properties", {})
        status_block = props.get("status", {})
        severity_raw = status_block.get("severity") or status_block.get("value", "medium")
        severity = normalize_severity(severity_raw)
        risk_tier = map_severity_to_risk_tier(severity)

        resource_id = (
            props.get("resourceDetails", {}).get("id")
            or props.get("resourceDetails", {}).get("source")
            or "unknown-resource"
        )
        asset_identifier = make_asset_identifier(
            AssetIdentifierType.CLOUD_RESOURCE_ID,
            resource_id,
            source=SCANNER_ID,
        )
        asset_id = resource_id

        cve_list = props.get("additionalData", {}).get("cve") or []
        vuln_key = (
            cve_list[0]
            if cve_list
            else f"MDC-{payload.get('name', 'unknown')}"
        )

        port = props.get("additionalData", {}).get("port")
        protocol = props.get("additionalData", {}).get("protocol")
        service = props.get("additionalData", {}).get("service")
        location_signature = "|".join(
            filter(None, [str(port) if port else "", protocol, service])
        ) or None

        canonical_id = generate_canonical_id(
            asset_id,
            vuln_key,
            location_signature,
        )

        status_code = status_block.get("code", "Unhealthy").lower()
        if status_code == "healthy":
            lifecycle = FindingLifecycleStatus.RESOLVED
        elif status_code == "unhealthy":
            lifecycle = FindingLifecycleStatus.OPEN
        else:
            lifecycle = FindingLifecycleStatus.OPEN

        time_generated = props.get("timeGenerated")
        first_observed = _parse_datetime(time_generated) if time_generated else None

        raw_ingestion_id = payload.get("id") or payload.get("name", "")

        source_reference = SourceReference(
            scanner_id=SCANNER_ID,
            external_id=raw_ingestion_id,
            first_seen=first_observed or datetime.now(timezone.utc),
            last_seen=first_observed or datetime.now(timezone.utc),
            severity=severity,
            raw_finding_id=raw_ingestion_id,
            status=status_block.get("code", "Unhealthy"),
        )

        return CanonicalFinding(
            id=canonical_id,
            canonical_id=canonical_id,
            asset_id=asset_id,
            asset_identifiers=[asset_identifier],
            sources=[source_reference],
            vuln_key=vuln_key,
            cwe=None,
            cvss_score=(
                props.get("additionalData", {})
                .get("cvss", {})
                .get("baseScore")
            ),
            severity=severity,
            risk_tier=risk_tier,
            status=lifecycle,
            remediation_bucket=default_remediation_bucket(),
            description=props.get("displayName"),
            recommendations=props.get("remediation"),
            first_observed=first_observed,
            last_observed=first_observed,
        )


class DefenderMdcIngestionService(DefenderIngestionService):
    """Backward-compatible alias for legacy imports."""


__all__ = [
    "DefenderMdcClient",
    "DefenderIngestionService",
    "DefenderMdcIngestionService",
]
