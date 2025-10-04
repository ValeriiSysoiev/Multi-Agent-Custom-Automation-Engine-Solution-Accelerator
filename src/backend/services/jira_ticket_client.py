"""Client for Jira vulnerability remediation tickets."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import httpx

from services.http_client import AsyncHttpClient
from services.key_vault import KeyVaultService

JIRA_API_BASE = "/rest/api/3"


@dataclass
class JiraTicketData:
    summary: str
    description: str
    risk_tier: str
    risk_score: int
    likelihood: int
    impact: int
    treatment: str
    bucket: str
    sla_due: datetime
    ack_due: Optional[datetime]
    verify_due: Optional[datetime]
    residual_risk: Optional[str]
    triage_link: Optional[str]
    kev: bool
    internet_exposed: bool
    cves: List[str]
    labels: List[str]
    due_date: datetime
    custom_fields: Dict[str, Any]
    application_ids: List[str]
    asset_ids: List[str]


@dataclass
class JiraTicketResult:
    issue_id: str
    issue_key: str
    self_url: str
    browse_url: str


logger = logging.getLogger(__name__)


class JiraTicketClient:
    """Minimal Jira API client for creating remediation tickets."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base_url = base_url or os.getenv("JIRA_BASE_URL")
        if not self._base_url:
            raise RuntimeError("JIRA_BASE_URL environment variable is required")

        self._vault = KeyVaultService()
        self._http: Optional[AsyncHttpClient] = None
        self._auth_header: Optional[str] = None
        self._lock = asyncio.Lock()
        self._project_key = os.getenv("JIRA_PROJECT_KEY", "CYB")
        self._issue_type_id = os.getenv("JIRA_VR_ISSUETYPE_ID", "10021")
        self._waiver_issue_type_id = os.getenv("JIRA_WAIVER_ISSUETYPE_ID", "10022")
        self._verification_field = os.getenv("JIRA_VERIFICATION_FIELD", "customfield_10075")
        self._waiver_status_field = os.getenv("JIRA_WAIVER_STATUS_FIELD", "customfield_10084")
        self._waiver_expiry_field = os.getenv("JIRA_WAIVER_EXPIRY_FIELD", "customfield_10083")
        self._verified_transition = os.getenv("JIRA_VERIFIED_TRANSITION", "Verified")
        self._reopen_transition = os.getenv("JIRA_REOPEN_TRANSITION", "Reopen")
        self._asset_hosts_field = os.getenv("JIRA_ASSET_HOSTS_FIELD", "customfield_10120")
        self._asset_apps_field = os.getenv("JIRA_APPLICATION_ASSET_FIELD", "customfield_10121")
        self._assets_workspace_id = os.getenv("JIRA_ASSETS_WORKSPACE_ID")
        self._ack_field = os.getenv("JIRA_ACK_FIELD")
        self._verify_field = os.getenv("JIRA_VERIFY_DUE_FIELD")
        self._user_cache: Dict[str, Optional[str]] = {}

    async def close(self) -> None:
        if self._http:
            await self._http.close()
            self._http = None
        await self._vault.close()

    async def create_remediation_ticket(self, payload: JiraTicketData) -> JiraTicketResult:
        await self._ensure_client()
        assert self._http is not None

        fields = self._build_fields(payload)
        try:
            response = await self._http.post(
                f"{JIRA_API_BASE}/issue",
                json={"fields": fields},
                expected_status=[201],
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text if exc.response is not None else "<no body>"
            logger.error(
                "Failed to create Jira remediation ticket (status=%s): %s",
                getattr(exc.response, "status_code", "?"),
                detail,
            )
            raise
        data = response.json()

        if payload.application_ids or payload.asset_ids:
            update_fields: Dict[str, Any] = {}
            if payload.application_ids:
                application_refs = self._format_application_refs(payload.application_ids)
                if application_refs:
                    update_fields[self._asset_apps_field] = application_refs
            if payload.asset_ids:
                asset_refs = self._format_asset_refs(payload.asset_ids)
                if asset_refs:
                    update_fields[self._asset_hosts_field] = asset_refs
            # Jira requires summary/description on issue updates when mandatory in the screen
            update_fields["summary"] = payload.summary
            update_fields["description"] = self._to_adf(payload.description)
            if self._ack_field and payload.ack_due:
                update_fields[self._ack_field] = payload.ack_due.strftime("%Y-%m-%d")
            if self._verify_field and payload.verify_due:
                update_fields[self._verify_field] = payload.verify_due.strftime("%Y-%m-%d")
            if update_fields:
                try:
                    await self._http.put(
                        f"{JIRA_API_BASE}/issue/{data['key']}",
                        json={"fields": update_fields},
                        expected_status=[204],
                    )
                except httpx.HTTPStatusError as exc:
                    detail = exc.response.text if exc.response is not None else "<no body>"
                    logger.error(
                        "Failed to update Jira remediation ticket %s (status=%s): %s",
                        data.get("key"),
                        getattr(exc.response, "status_code", "?"),
                        detail,
                    )
                    raise

        self_url = data.get("self") or f"{self._base_url}/rest/api/3/issue/{data['id']}"
        browse_url = f"{self._base_url}/browse/{data['key']}"
        return JiraTicketResult(
            issue_id=data["id"], issue_key=data["key"], self_url=self_url, browse_url=browse_url
        )

    async def transition_issue(
        self,
        issue_key: str,
        transition_name: str,
        *,
        fields: Optional[Dict[str, Any]] = None,
    ) -> None:
        await self._ensure_client()
        assert self._http is not None

        transition_id = await self._get_transition_id(issue_key, transition_name)
        payload: Dict[str, Any] = {"transition": {"id": transition_id}}
        if fields:
            payload["fields"] = fields

        await self._http.post(
            f"{JIRA_API_BASE}/issue/{issue_key}/transitions",
            json=payload,
            expected_status=[204],
        )

    async def update_issue_fields(self, issue_key: str, fields: Dict[str, Any]) -> None:
        if not fields:
            return
        await self._ensure_client()
        assert self._http is not None

        update_fields = await self._prepare_update_fields(issue_key, fields)

        await self._http.put(
            f"{JIRA_API_BASE}/issue/{issue_key}",
            json={"fields": update_fields},
            expected_status=[204],
        )

    async def set_waiver_status(
        self,
        issue_key: str,
        status: str,
        *,
        expiry: Optional[datetime] = None,
    ) -> None:
        fields: Dict[str, Any] = {}
        if self._waiver_status_field:
            fields[self._waiver_status_field] = {"value": status}
        if expiry and self._waiver_expiry_field:
            fields[self._waiver_expiry_field] = expiry.strftime("%Y-%m-%d")
        await self.update_issue_fields(issue_key, fields)

    async def mark_ticket_verified(self, issue_key: str, evidence_summary: str) -> None:
        fields = {}
        if self._verification_field:
            fields[self._verification_field] = evidence_summary
        await self.transition_issue(issue_key, self._verified_transition, fields=fields)

    async def reopen_ticket(self, issue_key: str, reason: Optional[str] = None) -> None:
        fields = {}
        if reason and self._verification_field:
            fields[self._verification_field] = reason
        await self.transition_issue(issue_key, self._reopen_transition, fields=fields or None)

    async def _ensure_client(self) -> None:
        async with self._lock:
            if not self._auth_header:
                pat = await self._vault.get_secret("JIRA-PAT")
                email = os.getenv("JIRA_USER_EMAIL")
                if not email:
                    raise RuntimeError("JIRA_USER_EMAIL environment variable is required")
                token = base64.b64encode(f"{email}:{pat}".encode("utf-8")).decode("ascii")
                self._auth_header = f"Basic {token}"

            if self._http is None:
                headers = {
                    "Authorization": self._auth_header,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
                self._http = AsyncHttpClient(base_url=self._base_url, default_headers=headers)

    async def _get_transition_id(self, issue_key: str, transition_name: str) -> str:
        assert self._http is not None
        response = await self._http.get(
            f"{JIRA_API_BASE}/issue/{issue_key}/transitions",
            expected_status=[200],
        )
        data = response.json()
        transitions = data.get("transitions", [])
        for transition in transitions:
            name = transition.get("name")
            if name and name.lower() == transition_name.lower():
                return transition["id"]
        available = ", ".join(t.get("name", "?") for t in transitions)
        raise ValueError(f"Transition '{transition_name}' not found for issue {issue_key}. Available: {available}")

    def _build_fields(self, payload: JiraTicketData) -> Dict[str, Any]:
        sla_due_str = payload.sla_due.strftime("%Y-%m-%d")

        fields: Dict[str, Any] = {
            "project": {"key": self._project_key},
            "issuetype": {"id": self._issue_type_id},
            "summary": payload.summary,
            "description": self._to_adf(payload.description),
            "customfield_10068": {"value": payload.risk_tier},
            "customfield_10069": payload.risk_score,
            "customfield_10070": payload.likelihood,
            "customfield_10071": payload.impact,
            "customfield_10072": {"value": payload.treatment},
            "customfield_10073": {"value": payload.bucket},
            "customfield_10074": sla_due_str,
            "customfield_10076": payload.residual_risk or "",
            "customfield_10079": {"value": "Yes" if payload.kev else "No"},
            "customfield_10080": {"value": "Yes" if payload.internet_exposed else "No"},
            "customfield_10081": self._to_adf("\n".join(payload.cves)),
        }

        if self._ack_field and payload.ack_due:
            fields[self._ack_field] = payload.ack_due.strftime("%Y-%m-%d")
        if self._verify_field and payload.verify_due:
            fields[self._verify_field] = payload.verify_due.strftime("%Y-%m-%d")

        if payload.custom_fields:
            fields.update(payload.custom_fields)

        if payload.labels and self._env_flag("JIRA_ENABLE_LABELS"):
            fields["labels"] = payload.labels
        if payload.due_date and self._env_flag("JIRA_ENABLE_DUEDATE"):
            fields["duedate"] = payload.due_date.strftime("%Y-%m-%d")
        if payload.triage_link and payload.triage_link.startswith(("http://", "https://")):
            fields["customfield_10078"] = payload.triage_link

        return fields

    @staticmethod
    def _coerce_description(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            # Assume the caller already passed a Jira document.
            return value
        if value is None:
            return JiraTicketClient._to_adf("")
        if isinstance(value, str):
            return JiraTicketClient._to_adf(value)
        return JiraTicketClient._to_adf(str(value))

    def _format_asset_refs(self, asset_ids: Iterable[Any]) -> List[Dict[str, str]]:
        return self._format_cmdb_refs(asset_ids)

    def _format_application_refs(self, application_ids: Iterable[Any]) -> List[Dict[str, str]]:
        return self._format_cmdb_refs(application_ids)

    def _normalize_asset_field(self, value: Any) -> List[Dict[str, str]]:
        return self._format_asset_refs(self._extract_cmdb_values(value))

    def _normalize_application_field(self, value: Any) -> List[Dict[str, str]]:
        return self._format_application_refs(self._extract_cmdb_values(value))

    def _format_cmdb_refs(self, values: Iterable[Any]) -> List[Dict[str, str]]:
        refs: List[Dict[str, str]] = []
        for raw in values:
            ref = self._build_cmdb_ref(raw)
            if ref:
                refs.append(ref)
        return refs

    def _build_cmdb_ref(self, value: Any) -> Optional[Dict[str, str]]:
        if value is None:
            return None

        if isinstance(value, dict):
            workspace = value.get("workspaceId") or self._assets_workspace_id
            global_id = value.get("globalId")
            object_id = value.get("objectId") or value.get("id")
            if global_id and not object_id:
                return {"globalId": str(global_id)}
            if not object_id:
                return None
            entry: Dict[str, str] = {
                "objectId": str(object_id),
                "id": str(object_id),
            }
            if workspace:
                entry["workspaceId"] = str(workspace)
            return entry

        text = str(value).strip()
        if not text:
            return None

        if text.startswith("ari:"):
            return {"globalId": text}

        workspace = self._assets_workspace_id
        object_id = text
        original = text
        if ":" in text:
            prefix, suffix = text.split(":", 1)
            suffix = suffix.strip()
            if suffix:
                workspace_candidate = prefix.strip()
                workspace = workspace_candidate or workspace
                object_id = suffix

        if not object_id:
            return None

        entry = {"objectId": object_id, "id": original}
        if workspace:
            entry["workspaceId"] = workspace
        return entry

    def _extract_cmdb_values(self, value: Any) -> List[Any]:
        if not value:
            return []
        if isinstance(value, list):
            return [item for item in value if item is not None]
        return [value]

    async def _prepare_update_fields(
        self,
        issue_key: str,
        fields: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Ensure Jira-required fields accompany every update request."""

        update_fields = dict(fields)

        summary_present = "summary" in update_fields
        description_present = "description" in update_fields

        if summary_present:
            summary_value = update_fields.get("summary")
            update_fields["summary"] = "" if summary_value is None else str(summary_value)

        if description_present:
            update_fields["description"] = self._coerce_description(update_fields["description"])

        asset_field = self._asset_hosts_field
        if asset_field in update_fields:
            normalized_assets = self._normalize_asset_field(update_fields[asset_field])
            if normalized_assets:
                update_fields[asset_field] = normalized_assets
            else:
                update_fields.pop(asset_field, None)

        app_field = self._asset_apps_field
        if app_field in update_fields:
            normalized_apps = self._normalize_application_field(update_fields[app_field])
            if normalized_apps:
                update_fields[app_field] = normalized_apps
            else:
                update_fields.pop(app_field, None)

        if summary_present and description_present:
            return update_fields

        # Fetch current summary/description so we can include them when the caller omits
        # mandatory fields from the update payload.
        assert self._http is not None
        response = await self._http.get(
            f"{JIRA_API_BASE}/issue/{issue_key}",
            params={"fields": "summary,description"},
            expected_status=[200],
        )
        current = response.json().get("fields", {}) if hasattr(response, "json") else {}

        if not summary_present:
            current_summary = current.get("summary")
            update_fields["summary"] = "" if current_summary is None else str(current_summary)

        if not description_present:
            current_description = current.get("description")
            update_fields["description"] = self._coerce_description(current_description)

        return update_fields

    @staticmethod
    def _env_flag(name: str) -> bool:
        value = os.getenv(name, "").strip().lower()
        return value in {"1", "true", "yes", "on"}

    @staticmethod
    def _to_adf(text: str) -> Dict[str, Any]:
        normalized = text.strip("\n")
        if not normalized:
            return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": []}]}

        content: List[Dict[str, Any]] = []
        for line in normalized.splitlines():
            if not line.strip():
                content.append({"type": "paragraph", "content": []})
                continue
            content.append(
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": line,
                        }
                    ],
                }
            )
        return {"type": "doc", "version": 1, "content": content}

    async def create_waiver_ticket(
        self,
        summary: str,
        description: str,
        expiry: datetime,
        status: str,
        custom_fields: Optional[Dict[str, Any]] = None,
    ) -> JiraTicketResult:
        await self._ensure_client()
        assert self._http is not None

        fields: Dict[str, Any] = {
            "project": {"key": self._project_key},
            "issuetype": {"id": self._waiver_issue_type_id},
            "summary": summary,
            "description": description,
            "customfield_10083": expiry.strftime("%Y-%m-%d"),
            "customfield_10084": {"value": status},
        }
        if custom_fields:
            fields.update(custom_fields)

        response = await self._http.post(
            f"{JIRA_API_BASE}/issue",
            json={"fields": fields},
            expected_status=[201],
        )
        data = response.json()
        self_url = data.get("self") or f"{self._base_url}/rest/api/3/issue/{data['id']}"
        browse_url = f"{self._base_url}/browse/{data['key']}"
        return JiraTicketResult(
            issue_id=data["id"], issue_key=data["key"], self_url=self_url, browse_url=browse_url
        )

    async def get_issue_fields(self, issue_key: str, *, fields: Optional[List[str]] = None) -> Dict[str, Any]:
        await self._ensure_client()
        assert self._http is not None

        params: Dict[str, str] = {}
        if fields:
            params["fields"] = ",".join(fields)

        response = await self._http.get(
            f"{JIRA_API_BASE}/issue/{issue_key}",
            params=params,
            expected_status=[200],
        )
        return response.json()

    async def find_user_account_id(self, email: str) -> Optional[str]:
        if not email:
            return None
        normalized = email.strip().lower()
        if not normalized:
            return None
        if normalized in self._user_cache:
            return self._user_cache[normalized]

        await self._ensure_client()
        assert self._http is not None
        try:
            response = await self._http.get(
                f"{JIRA_API_BASE}/user/search",
                params={"query": normalized, "maxResults": 1},
                expected_status=[200],
            )
        except httpx.HTTPStatusError:
            logger.warning("Failed to search Jira user for %s", normalized)
            self._user_cache[normalized] = None
            return None

        users = response.json() if hasattr(response, "json") else []
        account_id = None
        if isinstance(users, list) and users:
            account_id = users[0].get("accountId")
        self._user_cache[normalized] = account_id
        return account_id


__all__ = ["JiraTicketClient", "JiraTicketData", "JiraTicketResult"]
