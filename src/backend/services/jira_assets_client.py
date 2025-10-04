"""Client helpers for retrieving asset metadata from Jira Assets (JSM CMDB)."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

from models.messages_kernel import (
    ApplicationContext,
    AssetIdentifier,
    AssetIdentifierType,
    ConfidenceLevel,
    ExposureSurface,
    LinkageReviewInfo,
    OwnershipStatus,
    RiskTier,
)
from services.http_client import AsyncHttpClient
from services.key_vault import KeyVaultService

logger = logging.getLogger(__name__)

IDENTIFIER_PRIORITY: Dict[AssetIdentifierType, int] = {
    AssetIdentifierType.CLOUD_RESOURCE_ID: 0,
    AssetIdentifierType.SCANNER_AGENT_ID: 1,
    AssetIdentifierType.HOSTNAME: 2,
    AssetIdentifierType.MAC_ADDRESS: 3,
    AssetIdentifierType.IP_ADDRESS: 4,
    AssetIdentifierType.OTHER: 5,
}

ATTRIBUTE_NAME_MAP: Dict[AssetIdentifierType, Tuple[str, ...]] = {
    AssetIdentifierType.CLOUD_RESOURCE_ID: ("ResourceID",),
    AssetIdentifierType.HOSTNAME: ("Hostname",),
    AssetIdentifierType.IP_ADDRESS: ("IP",),
    AssetIdentifierType.MAC_ADDRESS: ("MAC Address",),
}

INTERNET_FACE_KEYS = {"internet facing", "internet-facing", "external facing", "external exposure"}
AUTH_REQUIRED_KEYS = {"authentication required", "auth required"}
NETWORK_SEGMENT_KEYS = {"network segment", "network zone", "subnet", "vnet"}
CONTROL_KEYWORDS = {
    "waf": "waf",
    "firewall": "firewall",
    "edr": "edr",
    "xdr": "xdr",
    "siem": "siem",
    "ids": "ids",
    "ips": "ips",
    "mfa": "mfa",
    "backup": "backup",
    "dr": "disaster_recovery",
    "patch": "patch",
}
PRIORITY_TAG_NAMES = {
    "business unit",
    "service tier",
    "data classification",
    "platform",
    "owner group",
}

DEFAULT_LINKAGE_HIGH_DAYS = 3
DEFAULT_LINKAGE_STANDARD_DAYS = 10


class JiraAssetsClient:
    """Small wrapper around the Jira Assets REST APIs."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self._site_base = base_url or os.getenv("JIRA_BASE_URL")
        if not self._site_base:
            raise RuntimeError("JIRA_BASE_URL environment variable is required for enrichment")

        self._http: Optional[AsyncHttpClient] = None
        self._vault = KeyVaultService()
        self._auth_header: Optional[str] = None
        self._lock = asyncio.Lock()
        self._workspace_id = os.getenv("JIRA_ASSETS_WORKSPACE_ID")
        self._workspace_base: Optional[str] = None
        self._object_type_cache: Dict[str, str] = {}
        self._application_cache: Dict[str, Optional[str]] = {}

        host_type_env = os.getenv("JIRA_ASSETS_HOST_TYPE_NAME")
        if host_type_env:
            self._host_type_names = [item.strip() for item in host_type_env.split(",") if item.strip()]
        else:
            self._host_type_names = ["Host"]

        app_type_env = os.getenv("JIRA_ASSETS_APPLICATION_TYPE_NAME")
        if app_type_env:
            self._app_type_names = [item.strip() for item in app_type_env.split(",") if item.strip()]
        else:
            self._app_type_names = ["Application / Service"]
        # Preserve existing attribute for backward compatibility
        self._host_type_name = self._host_type_names[0]
        self._app_type_name = self._app_type_names[0]
        link_attr_env = os.getenv("JIRA_ASSETS_APPLICATION_LINK_ATTRIBUTES")
        if link_attr_env:
            self._app_link_attributes = [item.strip() for item in link_attr_env.split(",") if item.strip()]
        else:
            self._app_link_attributes = ["Application", "Application / Service"]

    async def close(self) -> None:
        if self._http:
            await self._http.close()
            self._http = None
        await self._vault.close()

    async def _ensure_client(self) -> None:
        async with self._lock:
            if self._auth_header is None:
                pat = await self._vault.get_secret("JIRA-PAT")
                email = os.getenv("JIRA_USER_EMAIL")
                if not email:
                    raise RuntimeError("JIRA_USER_EMAIL environment variable is required for Jira Assets access")
                token = base64.b64encode(f"{email}:{pat}".encode("utf-8")).decode("ascii")
                self._auth_header = f"Basic {token}"

            if self._http is None:
                headers = {
                    "Authorization": self._auth_header,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-ExperimentalApi": "assets",
                }
                self._http = AsyncHttpClient(base_url="https://api.atlassian.com", default_headers=headers)

            await self._ensure_workspace()

    async def _ensure_workspace(self) -> None:
        if self._workspace_id and self._workspace_base:
            return
        assert self._http is not None
        if not self._workspace_id:
            response = await self._http.get("/jsm/assets/workspace", expected_status=[200])
            data = response.json() or []
            if not data:
                raise RuntimeError("No Jira Assets workspace available; set JIRA_ASSETS_WORKSPACE_ID")
            self._workspace_id = data[0].get("workspaceId") or data[0].get("id")
            if not self._workspace_id:
                raise RuntimeError("Unable to determine Jira Assets workspace id")
        self._workspace_base = f"/jsm/assets/workspace/{self._workspace_id}/v1"

    async def resolve_context(
        self,
        canonical_asset_id: str,
        asset_identifiers: Iterable[AssetIdentifier],
        risk_tier: RiskTier,
    ) -> Tuple[ApplicationContext, ExposureSurface, OwnershipStatus, Optional[LinkageReviewInfo]]:
        """Retrieve application and exposure context for a canonical finding."""

        await self._ensure_client()
        assert self._http is not None

        host_object = await self._find_host_object(asset_identifiers)
        if not host_object:
            logger.info("Host not found in Jira Assets for asset_id=%s", canonical_asset_id)
            linkage = self._build_linkage_review(risk_tier)
            return ApplicationContext(), ExposureSurface(), OwnershipStatus.LINKAGE_REVIEW, linkage

        host_attributes = self._attributes_to_map(host_object.get("attributes", []))
        app_reference = await self._extract_application_reference(host_object, host_attributes)
        application_object = await self._get_object(app_reference[0]) if app_reference and app_reference[0] else None
        app_attributes = self._attributes_to_map(application_object.get("attributes", [])) if application_object else {}

        context = self._build_application_context(host_attributes, app_attributes, host_object, application_object)
        exposure = self._build_exposure_surface(host_attributes, app_attributes)
        ownership_status = self._determine_ownership_status(context)
        linkage_info = None if ownership_status != OwnershipStatus.LINKAGE_REVIEW else self._build_linkage_review(risk_tier)

        return context, exposure, ownership_status, linkage_info

    async def _find_host_object(self, identifiers: Iterable[AssetIdentifier]) -> Optional[Dict[str, Any]]:
        ordered = sorted(identifiers, key=lambda item: IDENTIFIER_PRIORITY.get(item.id_type, 99))
        for identifier in ordered:
            attribute_names = ATTRIBUTE_NAME_MAP.get(identifier.id_type)
            if not attribute_names:
                continue
            for host_type in self._host_type_names:
                for attribute_name in attribute_names:
                    query = (
                        f'objectType = "{self._escape(host_type)}" '
                        f'AND "{self._escape(attribute_name)}" = "{self._escape(identifier.value)}"'
                    )
                    result = await self._run_aql(query)
                    if not result:
                        continue
                    candidate_id = str(result[0].get("id") or result[0].get("objectId"))
                    if not candidate_id:
                        continue
                    host_object = await self._get_object(candidate_id)
                    if host_object:
                        return host_object
            # Fallback search without explicit object type in case schema uses inheritance
            for attribute_name in attribute_names:
                query = f'"{self._escape(attribute_name)}" = "{self._escape(identifier.value)}"'
                result = await self._run_aql(query)
                if not result:
                    continue
                candidate_id = str(result[0].get("id") or result[0].get("objectId"))
                if not candidate_id:
                    continue
                host_object = await self._get_object(candidate_id)
                if host_object:
                    return host_object
        return None

    async def resolve_asset_links(
        self, asset_identifiers: Iterable[AssetIdentifier]
    ) -> tuple[list[str], Optional[str]]:
        """Resolve Jira Assets object ids for hosts and associated applications."""

        host_object = await self._find_host_object(asset_identifiers)
        if not host_object:
            return ([], None)

        host_ids: list[str] = []
        host_global = host_object.get("globalId")
        host_object_id = host_object.get("objectId") or host_object.get("id")
        if host_global:
            host_ids.append(str(host_global))
        elif host_object_id:
            workspace = host_object.get("workspaceId") or self._workspace_id
            host_ids.append(
                f"{workspace}:{host_object_id}" if workspace else str(host_object_id)
            )
        host_attrs = self._attributes_to_map(host_object.get("attributes", []))
        app_reference = await self._extract_application_reference(host_object, host_attrs)
        application_id = None
        if app_reference and app_reference[0]:
            raw_id = app_reference[0]
            application_object = await self._get_object(str(raw_id))
            if application_object:
                app_global = application_object.get("globalId")
                app_object_id = (
                    application_object.get("objectId")
                    or application_object.get("id")
                    or raw_id
                )
                if app_global:
                    application_id = str(app_global)
                else:
                    workspace = application_object.get("workspaceId") or self._workspace_id
                    application_id = (
                        f"{workspace}:{app_object_id}" if workspace else str(app_object_id)
                    )
            else:
                application_id = str(raw_id)
        return (host_ids, application_id)

    async def _run_aql(self, query: str) -> List[Dict[str, Any]]:
        await self._ensure_client()
        assert self._http is not None

        payload = {"qlQuery": query, "resultPerPage": 50}
        last_exc: Optional[Exception] = None
        assert self._workspace_base is not None
        url = f"{self._workspace_base}/object/aql"
        try:
            response = await self._http.post(url, json=payload, expected_status=[200])
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            logger.debug("Jira Assets AQL failed for query '%s': %s", query, exc)
            return []
        data = response.json() or {}
        values = data.get("values") or data.get("data") or []
        if not isinstance(values, list):
            logger.debug("Unexpected AQL response format: %s", data)
            return []
        return values

    async def _get_object(self, object_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_client()
        assert self._http is not None
        assert self._workspace_base is not None

        url = f"{self._workspace_base}/object/{object_id}"
        try:
            response = await self._http.get(url, expected_status=[200])
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.debug("Failed to fetch Jira asset object %s: %s", object_id, exc)
            return None

    def _build_application_context(
        self,
        host_attrs: Dict[str, List[Any]],
        app_attrs: Dict[str, List[Any]],
        host_object: Dict[str, Any],
        application_object: Optional[Dict[str, Any]],
    ) -> ApplicationContext:
        context = ApplicationContext()

        context.application = self._first_non_empty(
            self._get_attribute_values(app_attrs, {"Name"}),
            self._get_attribute_values(host_attrs, {"Application", "Application / Service"}),
            [application_object.get("label")] if application_object else None,
        )

        context.business_service = self._first_non_empty(
            self._get_attribute_values(app_attrs, {"Business Service", "Service"}),
        )

        owner_name, owner_email = self._extract_owner(host_attrs, app_attrs)
        context.owner = owner_name
        context.owner_email = owner_email

        context.environment = self._first_non_empty(
            self._get_attribute_values(host_attrs, {"Environment"}),
            self._get_attribute_values(app_attrs, {"Environment"}),
        )

        context.criticality = self._first_non_empty(
            self._get_attribute_values(app_attrs, {"Business Criticality", "Criticality"}),
            self._get_attribute_values(host_attrs, {"Business Criticality", "Criticality"}),
        )

        context.tags = self._collect_tags(host_attrs, app_attrs)
        context.completeness = self._determine_completeness(context)
        return context

    def _build_exposure_surface(
        self,
        host_attrs: Dict[str, List[Any]],
        app_attrs: Dict[str, List[Any]],
    ) -> ExposureSurface:
        exposure = ExposureSurface()

        internet_source = self._first_boolean(host_attrs, app_attrs, INTERNET_FACE_KEYS)
        if internet_source is not None:
            exposure.internet_facing = internet_source

        auth_required = self._first_boolean(host_attrs, app_attrs, AUTH_REQUIRED_KEYS)
        if auth_required is not None:
            exposure.authentication_required = auth_required

        network_segment = self._first_non_empty(
            self._get_attribute_values(host_attrs, NETWORK_SEGMENT_KEYS),
            self._get_attribute_values(app_attrs, NETWORK_SEGMENT_KEYS),
        )
        exposure.network_segment = network_segment

        coverage = self._control_coverage_map(host_attrs, app_attrs)
        if coverage:
            exposure.control_coverage = coverage

        return exposure

    def _determine_completeness(self, context: ApplicationContext) -> ConfidenceLevel:
        score = 0
        if context.owner:
            score += 1
        if context.application:
            score += 1
        if context.environment:
            score += 1
        if context.criticality:
            score += 1

        if score >= 3:
            return ConfidenceLevel.HIGH
        if score >= 1:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    def _determine_ownership_status(self, context: ApplicationContext) -> OwnershipStatus:
        if context.owner and context.application:
            return OwnershipStatus.CONFIRMED
        if context.owner or context.application or context.environment:
            return OwnershipStatus.PROVISIONAL
        return OwnershipStatus.LINKAGE_REVIEW

    def _extract_owner(
        self,
        host_attrs: Dict[str, List[Any]],
        app_attrs: Dict[str, List[Any]],
    ) -> Tuple[Optional[str], Optional[str]]:
        owner_attrs = self._get_attribute_values(host_attrs, {"Owner", "Service Owner", "Business Owner"}) or []
        app_owner_attrs = self._get_attribute_values(app_attrs, {"Owner", "Service Owner", "Business Owner"}) or []

        for candidate in owner_attrs + app_owner_attrs:
            if isinstance(candidate, dict):
                name = candidate.get("displayValue") or candidate.get("name") or candidate.get("value")
                email = None
                user_ref = candidate.get("user") or candidate.get("person")
                if isinstance(user_ref, dict):
                    email = user_ref.get("email") or user_ref.get("name")
                if not email and "@" in (candidate.get("email") or ""):
                    email = candidate.get("email")
                if name:
                    return str(name), email
            elif isinstance(candidate, str) and candidate:
                return candidate, None
        return None, None

    def _collect_tags(
        self,
        host_attrs: Dict[str, List[Any]],
        app_attrs: Dict[str, List[Any]],
    ) -> Dict[str, Any]:
        tags: Dict[str, Any] = {}
        for source, attributes in (("host", host_attrs), ("application", app_attrs)):
            for name, values in attributes.items():
                lowered = name.lower()
                if lowered in PRIORITY_TAG_NAMES:
                    normalized = self._stringify_list(values)
                    if normalized:
                        tags[f"{source}_{lowered.replace(' ', '_')}"] = normalized if len(normalized) > 1 else normalized[0]
        return tags

    def _first_boolean(
        self,
        host_attrs: Dict[str, List[Any]],
        app_attrs: Dict[str, List[Any]],
        keys: Iterable[str],
    ) -> Optional[bool]:
        key_set = {key.lower() for key in keys}
        for attributes in (host_attrs, app_attrs):
            for name, values in attributes.items():
                if name.lower() not in key_set:
                    continue
                for value in values:
                    bool_value = self._coerce_bool(value)
                    if bool_value is not None:
                        return bool_value
        return None

    def _control_coverage_map(
        self,
        host_attrs: Dict[str, List[Any]],
        app_attrs: Dict[str, List[Any]],
    ) -> Dict[str, bool]:
        coverage: Dict[str, bool] = {}
        for attributes in (host_attrs, app_attrs):
            for name, values in attributes.items():
                lower_name = name.lower()
                for keyword, control_key in CONTROL_KEYWORDS.items():
                    if keyword in lower_name:
                        bool_value = self._extract_first_bool(values)
                        if bool_value is not None:
                            coverage[control_key] = bool_value
        return coverage

    def _extract_first_bool(self, values: Iterable[Any]) -> Optional[bool]:
        for value in values:
            bool_value = self._coerce_bool(value)
            if bool_value is not None:
                return bool_value
        return None

    def _coerce_bool(self, value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if isinstance(value, dict):
            candidate = value.get("value") or value.get("displayValue") or value.get("name")
            if candidate is None:
                return None
            value = candidate
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"yes", "true", "y", "1"}:
                return True
            if lowered in {"no", "false", "n", "0"}:
                return False
        return None

    def _get_attribute_values(
        self,
        attributes: Dict[str, List[Any]],
        candidate_names: Iterable[str],
    ) -> Optional[List[Any]]:
        normalized = {name.lower() for name in candidate_names}
        for name, values in attributes.items():
            if name.lower() in normalized:
                return values
        return None

    def _stringify_list(self, values: Iterable[Any]) -> List[str]:
        result: List[str] = []
        for value in values:
            if isinstance(value, dict):
                candidate = value.get("displayValue") or value.get("name") or value.get("value")
                if candidate:
                    result.append(str(candidate))
            elif isinstance(value, str):
                result.append(value)
        return result

    def _first_non_empty(self, *value_groups: Optional[Iterable[Any]]) -> Optional[str]:
        for group in value_groups:
            if not group:
                continue
            for value in group:
                if isinstance(value, dict):
                    candidate = value.get("displayValue") or value.get("name") or value.get("value")
                    if candidate:
                        return str(candidate)
                elif isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    async def _extract_application_reference(
        self,
        host_object: Dict[str, Any],
        host_attrs: Dict[str, List[Any]],
    ) -> Optional[Tuple[Optional[str], Optional[str]]]:
        normalized_attrs = {name.lower(): values for name, values in host_attrs.items()}
        checked_names = {attr.lower() for attr in self._app_link_attributes}

        # Primary lookup: explicit link attributes configured for the schema
        for attr_name in checked_names:
            values = normalized_attrs.get(attr_name)
            if not values:
                continue
            for value in values:
                ref = await self._value_to_reference(value)
                if ref:
                    object_id, display, _ = ref
                    return object_id, display

        # Fallback: inspect raw attribute payloads in case objectAttributeValues preserve references only there
        for attribute in host_object.get("attributes", []):
            name = (
                attribute.get("name")
                or attribute.get("objectTypeAttribute", {}).get("name")
                or attribute.get("attribute", {}).get("name")
            )
            if not name or name.lower() not in checked_names:
                continue
            raw_values = attribute.get("objectAttributeValues") or attribute.get("values") or []
            for raw in raw_values:
                ref = await self._value_to_reference(raw)
                if ref:
                    object_id, display, _ = ref
                    return object_id, display

        # Final fallback: relationships returned by the Assets API when the host links to other objects
        for relation in host_object.get("relations", []):
            ref = await self._value_to_reference(relation)
            if ref:
                object_id, display, object_type = ref
                if object_type and "application" not in object_type:
                    continue
                return object_id, display
        return None

    async def _value_to_reference(
        self,
        value: Any,
    ) -> Optional[Tuple[Optional[str], Optional[str], Optional[str]]]:
        reference = self._coerce_reference(value)
        if not reference:
            return None

        object_id, display, object_type = reference
        if object_id:
            return object_id, display, object_type

        if display:
            application_id = await self._find_application_id_by_name(display)
            if application_id:
                return application_id, display, object_type
        return reference

    def _coerce_reference(
        self,
        value: Any,
    ) -> Optional[Tuple[Optional[str], Optional[str], Optional[str]]]:
        if isinstance(value, dict):
            candidates: List[Dict[str, Any]] = []
            for key in ("raw", "value", "referencedObject", "objectAttributeValue"):
                candidate = value.get(key)
                if isinstance(candidate, dict):
                    candidates.append(candidate)
            if isinstance(value.get("objectAttributeValues"), list):
                candidates.extend([
                    candidate for candidate in value.get("objectAttributeValues", []) if isinstance(candidate, dict)
                ])
            candidates.append(value)

            for candidate in candidates:
                object_id = candidate.get("objectId") or candidate.get("id") or candidate.get("objectKey")
                display = (
                    candidate.get("label")
                    or candidate.get("displayValue")
                    or candidate.get("name")
                    or value.get("displayValue")
                )
                object_type = candidate.get("objectTypeName")
                if not object_type and isinstance(candidate.get("objectType"), dict):
                    object_type = candidate.get("objectType", {}).get("name")
                if not object_type and value.get("objectTypeName"):
                    object_type = value.get("objectTypeName")
                if object_id or display:
                    return (
                        str(object_id) if object_id else None,
                        display,
                        object_type.lower() if isinstance(object_type, str) else None,
                    )
        elif isinstance(value, str) and value.strip():
            return (None, value.strip(), None)
        return None

    async def _find_application_id_by_name(self, name: str) -> Optional[str]:
        normalized = name.strip()
        if not normalized:
            return None

        cache_key = normalized.lower()
        if cache_key in self._application_cache:
            return self._application_cache[cache_key]

        escaped_name = self._escape(normalized)
        for app_type in self._app_type_names:
            query = (
                f'objectType = "{self._escape(app_type)}" '
                f'AND "Name" = "{escaped_name}"'
            )
            result = await self._run_aql(query)
            if result:
                candidate_id = result[0].get("id") or result[0].get("objectId")
                if candidate_id:
                    self._application_cache[cache_key] = str(candidate_id)
                    return str(candidate_id)

        self._application_cache[cache_key] = None
        return None

    def _normalize_reference_dict(
        self,
        value: Dict[str, Any],
        *,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        object_id = value.get("objectId") or value.get("id") or value.get("objectKey")
        display = value.get("label") or value.get("displayValue") or value.get("name")
        object_type = value.get("objectTypeName")
        if not object_type and isinstance(value.get("objectType"), dict):
            object_type = value.get("objectType", {}).get("name")

        email = value.get("email") or value.get("emailAddress")
        user = value.get("user") if isinstance(value.get("user"), dict) else None

        if raw and isinstance(raw, dict):
            display = display or raw.get("displayValue")
            object_id = object_id or raw.get("objectId") or raw.get("id")
            if not object_type:
                object_type = raw.get("objectTypeName")
            if not email:
                email = raw.get("email") or raw.get("emailAddress")
            if not user and isinstance(raw.get("user"), dict):
                user = raw.get("user")

        if not (object_id or display or email or user):
            return None

        normalized: Dict[str, Any] = {
            "objectId": str(object_id) if object_id else None,
            "displayValue": display,
            "objectTypeName": object_type,
            "raw": raw or value,
        }
        if email:
            normalized["email"] = email
        if user:
            normalized["user"] = user
        return normalized

    def _attributes_to_map(self, attributes: Iterable[Dict[str, Any]]) -> Dict[str, List[Any]]:
        mapping: Dict[str, List[Any]] = {}
        for attribute in attributes or []:
            name = (
                attribute.get("name")
                or attribute.get("attribute", {}).get("name")
                or attribute.get("objectTypeAttribute", {}).get("name")
            )
            if not name:
                continue
            raw_values = attribute.get("values")
            if raw_values is None:
                raw_values = attribute.get("objectAttributeValues")
            if isinstance(raw_values, dict):
                raw_values = [raw_values]
            elif raw_values is None:
                raw_values = []
            values = [self._unwrap_attribute_value(value) for value in raw_values or []]
            mapping.setdefault(name, []).extend([value for value in values if value is not None])
        return mapping

    def _unwrap_attribute_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            inner = value.get("value") if isinstance(value.get("value"), dict) else None
            referenced = value.get("referencedObject") if isinstance(value.get("referencedObject"), dict) else None

            if inner:
                normalized = self._normalize_reference_dict(inner, raw=value)
                if normalized:
                    return normalized
            if referenced:
                normalized = self._normalize_reference_dict(referenced, raw=value)
                if normalized:
                    return normalized

            if "objectAttributeValues" in value and isinstance(value["objectAttributeValues"], list):
                for candidate in value["objectAttributeValues"]:
                    if isinstance(candidate, dict):
                        normalized = self._normalize_reference_dict(candidate, raw=value)
                        if normalized:
                            return normalized

            if "displayValue" in value and isinstance(value["displayValue"], str):
                return {
                    "displayValue": value.get("displayValue"),
                    "raw": value,
                }
            if "user" in value and isinstance(value["user"], dict):
                user = value["user"]
                return {
                    "displayValue": value.get("displayValue")
                    or user.get("displayName")
                    or user.get("name"),
                    "email": user.get("emailAddress") or user.get("email"),
                    "user": user,
                    "raw": value,
                }
            return {"raw": value}
        return value

    def _escape(self, value: str) -> str:
        return value.replace("\"", "\\\"")

    def _build_linkage_review(self, risk_tier: RiskTier) -> LinkageReviewInfo:
        now = datetime.now(timezone.utc)
        days = DEFAULT_LINKAGE_HIGH_DAYS if risk_tier in {RiskTier.CRITICAL, RiskTier.HIGH} else DEFAULT_LINKAGE_STANDARD_DAYS
        sla_due = now + timedelta(days=days)
        return LinkageReviewInfo(status=OwnershipStatus.LINKAGE_REVIEW, queued_at=now, sla_due=sla_due)
