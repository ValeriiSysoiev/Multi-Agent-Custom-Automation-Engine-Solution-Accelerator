"""Service responsible for exporting reporting datasets and triggering Power BI refreshes."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import ContentSettings

from helpers.azure_credential_utils import (
    get_azure_credential_async,
    resolve_managed_identity_client_id,
)
from models.messages_kernel import AgentType, RunEventRecord
from repositories.asset_repository import AssetRepository
from repositories.canonical_finding_repository import CanonicalFindingRepository
from repositories.enrichment_repository import EnrichmentRepository
from repositories.remediation_unit_repository import RemediationUnitRepository
from repositories.run_event_repository import RunEventRepository
from repositories.ticket_repository import TicketRepository
from repositories.triage_repository import TriageRepository
from repositories.waiver_repository import WaiverRepository
from services.key_vault import KeyVaultService
from services.powerbi_client import PowerBIClient
from services.reporting_config import load_reporting_config

logger = logging.getLogger(__name__)


class ReportingExportService:
    """Collects Cosmos data, writes reporting extracts, and refreshes Power BI."""

    def __init__(
        self,
        config: Optional[Dict[str, str]] = None,
        canonical_repo: Optional[CanonicalFindingRepository] = None,
        enrichment_repo: Optional[EnrichmentRepository] = None,
        triage_repo: Optional[TriageRepository] = None,
        remediation_repo: Optional[RemediationUnitRepository] = None,
        ticket_repo: Optional[TicketRepository] = None,
        waiver_repo: Optional[WaiverRepository] = None,
        asset_repo: Optional[AssetRepository] = None,
        run_repo: Optional[RunEventRepository] = None,
        blob_service: Optional[BlobServiceClient] = None,
        key_vault: Optional[KeyVaultService] = None,
        powerbi_client: Optional[PowerBIClient] = None,
    ) -> None:
        self._config = config or load_reporting_config()
        self._storage_account = (self._config.get("storage_account") or "").strip()
        self._storage_container = (self._config.get("storage_container") or "").strip()
        self._export_format = (self._config.get("export_format") or "parquet").lower()
        tenant_override = (
            os.getenv("PBI_TENANT_ID")
            or os.getenv("POWERBI_TENANT_ID")
            or os.getenv("AZURE_TENANT_ID")
        )
        tenant_cfg = self._config.get("tenant_id") if isinstance(self._config, dict) else None
        self._tenant_id = (tenant_override or tenant_cfg or "").strip()
        client_id_cfg = self._config.get("client_id") if isinstance(self._config, dict) else None
        self._client_id = (client_id_cfg or os.getenv("AZURE_CLIENT_ID", "")).strip()
        identity_cfg = (
            self._config.get("managed_identity_client_id")
            if isinstance(self._config, dict)
            else None
        )
        self._managed_identity_client_id = resolve_managed_identity_client_id(identity_cfg)
        self._workspace_id = self._config.get("workspace_id")
        self._dataset_id = (self._config.get("dataset_id") or "").strip()
        self._push_dataset_enabled = bool(self._config.get("push_dataset_enabled", False))

        self._canonical_repo = canonical_repo or CanonicalFindingRepository()
        self._enrichment_repo = enrichment_repo or EnrichmentRepository()
        self._triage_repo = triage_repo or TriageRepository()
        self._remediation_repo = remediation_repo or RemediationUnitRepository()
        self._ticket_repo = ticket_repo or TicketRepository()
        self._waiver_repo = waiver_repo or WaiverRepository()
        self._asset_repo = asset_repo or AssetRepository()
        self._run_repo = run_repo or RunEventRepository()

        self._blob_service = blob_service
        self._blob_credential = None
        self._key_vault = key_vault
        self._powerbi_client = powerbi_client

    async def close(self) -> None:
        if self._blob_service:
            await self._blob_service.close()
            self._blob_service = None
        credential = self._blob_credential
        self._blob_credential = None
        if credential and hasattr(credential, "close"):
            result = credential.close()
            if asyncio.iscoroutine(result):
                await result
        if self._key_vault:
            await self._key_vault.close()
            self._key_vault = None

    async def export(
        self,
        *,
        date_key: Optional[str] = None,
        refresh_powerbi: bool = False,
    ) -> Dict[str, int]:
        correlation_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        metrics: Dict[str, int] = {}
        await self._run_repo.upsert_event(
            self._build_run_event(
                correlation_id=correlation_id,
                status="started",
                started_at=started_at,
                metrics=metrics,
            )
        )

        status = "completed"
        error_message: Optional[str] = None
        try:
            frames = await self._gather_frames()
            metrics.update({name: len(frame) for name, frame in frames.items()})

            if self._storage_account and self._storage_account.lower() != "tbd" and frames:
                date_segment = date_key or started_at.strftime("%Y%m%d")
                uploaded = await self._upload_frames(date_segment, frames)
                metrics.update({f"uploaded_{name}": count for name, count in uploaded.items()})
            else:
                if not self._storage_account or self._storage_account.lower() == "tbd":
                    logger.info("Reporting export skipping blob upload; storage account not configured")

            push_metrics = await self._push_to_powerbi_dataset(frames)
            metrics.update(push_metrics)

            if (
                refresh_powerbi
                and not self._push_dataset_enabled
                and self._dataset_id
                and self._dataset_id.lower() != "tbd"
            ):
                refreshed = await self._trigger_powerbi_refresh()
                metrics["powerbi_refresh_triggered"] = 1 if refreshed else 0
            elif refresh_powerbi:
                logger.info("Power BI dataset id not configured; skipping refresh trigger")
        except Exception as exc:  # pragma: no cover - defensive logging
            status = "failed"
            error_message = str(exc)
            logger.exception("Reporting export failed")
            raise
        finally:
            completed_at = datetime.now(timezone.utc)
            await self._run_repo.upsert_event(
                self._build_run_event(
                    correlation_id=correlation_id,
                    status=status,
                    started_at=started_at,
                    completed_at=completed_at,
                    metrics=metrics,
                    error=error_message,
                )
            )
        return metrics

    async def _gather_frames(self) -> Dict[str, List[dict]]:
        datasets: Dict[str, List[dict]] = {}

        canonical = await self._canonical_repo.list_all()
        datasets["facts_findings"] = self._to_records(canonical)

        enrichments = await self._enrichment_repo.list_all()
        datasets["facts_enrichment"] = self._to_records(enrichments)

        triage = await self._triage_repo.list_all()
        datasets["facts_triage"] = self._to_records(triage)

        remediation_units = await self._remediation_repo.list_all()
        datasets["facts_remediation_units"] = self._to_records(remediation_units)

        tickets = await self._ticket_repo.list_all()
        datasets["facts_tickets"] = self._to_records(tickets)

        waivers = await self._waiver_repo.list_all()
        datasets["facts_waivers"] = self._to_records(waivers)

        assets = await self._asset_repo.list_all()
        datasets["dim_assets"] = self._to_records(assets)

        return datasets

    async def _upload_frames(self, date_segment: str, frames: Dict[str, List[dict]]) -> Dict[str, int]:
        container = await self._ensure_container_client()
        metrics: Dict[str, int] = {}
        for name, records in frames.items():
            blob_name = f"reports/aivm/{date_segment}/{name}.{self._export_format}"
            payload, content_type = self._serialize_records(records)
            await container.upload_blob(
                name=blob_name,
                data=payload,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
            metrics[name] = len(records)
        return metrics

    async def _ensure_container_client(self):
        if not self._blob_service:
            if not self._storage_account:
                raise RuntimeError("Storage account is not configured for reporting export")
            managed_identity_client_id = resolve_managed_identity_client_id(
                self._managed_identity_client_id
            )
            credential = await get_azure_credential_async(client_id=managed_identity_client_id)
            self._blob_credential = credential
            account_url = f"https://{self._storage_account}.blob.core.windows.net"
            self._blob_service = BlobServiceClient(account_url=account_url, credential=credential)
        container_client = self._blob_service.get_container_client(self._storage_container)
        try:
            await container_client.create_container()
        except ResourceExistsError:
            pass
        return container_client

    async def _trigger_powerbi_refresh(self) -> bool:
        client = await self._ensure_powerbi_client()
        if not client:
            return False
        return await client.trigger_refresh(self._workspace_id, self._dataset_id)

    async def _push_to_powerbi_dataset(self, frames: Dict[str, List[dict]]) -> Dict[str, int]:
        if not self._push_dataset_enabled:
            return {}
        if not self._workspace_id or not self._dataset_id or self._dataset_id.lower() == "tbd":
            logger.info("Power BI push dataset not configured; skipping push")
            return {}

        client = await self._ensure_powerbi_client()
        if not client:
            return {}

        rows_map = self._build_push_rows(frames)
        metrics: Dict[str, int] = {}
        for table, rows in rows_map.items():
            await client.replace_rows(self._workspace_id, self._dataset_id, table, rows)
            metrics[f"pbi_rows_{table}"] = len(rows)
        return metrics

    async def _ensure_powerbi_client(self) -> Optional[PowerBIClient]:
        if self._powerbi_client:
            return self._powerbi_client

        if not self._tenant_id or not self._client_id:
            logger.info("Power BI tenant/client not configured; skipping")
            return None

        secret: Optional[str] = None
        vault = self._key_vault or KeyVaultService()
        try:
            secret = await vault.get_secret("POWERBI-CLIENT-SECRET")
        except ResourceNotFoundError as exc:
            fallback = os.getenv("POWERBI_CLIENT_SECRET")
            if not fallback:
                raise
            logger.warning(
                "POWERBI-CLIENT-SECRET not found in Key Vault; falling back to environment variable"
            )
            secret = fallback
        if secret is None:
            raise RuntimeError("Power BI client secret is not configured")

        if self._key_vault is None:
            self._key_vault = vault

        client = PowerBIClient(self._tenant_id, self._client_id, secret)
        self._powerbi_client = client
        return client

    def _build_push_rows(self, frames: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
        table_names = [
            "facts_findings",
            "facts_enrichment",
            "facts_triage",
            "facts_remediation_units",
            "facts_tickets",
            "facts_waivers",
            "dim_assets",
        ]
        rows: Dict[str, List[dict]] = {name: [] for name in table_names}

        def add(table: str, row: dict) -> None:
            rows.setdefault(table, []).append(row)

        for record in frames.get("facts_findings", []):
            if not isinstance(record, dict):
                continue
            add(
                "facts_findings",
                {
                    "canonical_id": record.get("canonical_id"),
                    "asset_id": record.get("asset_id"),
                    "risk_tier": record.get("risk_tier"),
                    "severity": record.get("severity"),
                    "status": record.get("status"),
                    "remediation_bucket": record.get("remediation_bucket"),
                    "remediation_unit_id": record.get("remediation_unit_id"),
                    "first_observed": self._format_datetime(record.get("first_observed")),
                    "last_observed": self._format_datetime(record.get("last_observed")),
                    "ownership_status": record.get("ownership_status"),
                },
            )

        for record in frames.get("facts_enrichment", []):
            if not isinstance(record, dict):
                continue
            context = record.get("application_context") or {}
            exposure = record.get("exposure") or {}
            add(
                "facts_enrichment",
                {
                    "canonical_id": record.get("canonical_id"),
                    "asset_id": record.get("asset_id"),
                    "application": context.get("application"),
                    "owner": context.get("owner"),
                    "environment": context.get("environment"),
                    "criticality": context.get("criticality"),
                    "internet_facing": self._safe_bool(exposure.get("internet_facing")),
                    "timestamp": self._format_datetime(record.get("timestamp")),
                },
            )

        for record in frames.get("facts_triage", []):
            if not isinstance(record, dict):
                continue
            residual = record.get("residual_risk") or {}
            add(
                "facts_triage",
                {
                    "triage_id": record.get("triage_id"),
                    "canonical_id": record.get("canonical_id"),
                    "risk_score": self._safe_int(record.get("risk_score")),
                    "risk_tier": record.get("risk_tier"),
                    "likelihood": self._safe_int(record.get("likelihood")),
                    "impact": self._safe_int(record.get("impact")),
                    "treatment": record.get("treatment"),
                    "created_by": record.get("created_by"),
                    "timestamp": self._format_datetime(record.get("timestamp")),
                },
            )

        for record in frames.get("facts_remediation_units", []):
            if not isinstance(record, dict):
                continue
            add(
                "facts_remediation_units",
                {
                    "remediation_unit_id": record.get("remediation_unit_id"),
                    "name": record.get("name"),
                    "bucket": record.get("bucket"),
                    "risk_tier": record.get("risk_tier"),
                    "status": record.get("status"),
                    "target_due_date": self._format_datetime(record.get("target_due_date")),
                    "owner": record.get("owner"),
                },
            )

        for record in frames.get("facts_tickets", []):
            if not isinstance(record, dict):
                continue
            add(
                "facts_tickets",
                {
                    "ticket_id": record.get("ticket_id"),
                    "remediation_unit_id": record.get("remediation_unit_id"),
                    "status": record.get("status"),
                    "due_at": self._format_datetime(record.get("due_at")),
                    "ack_due": self._format_datetime(record.get("ack_due")),
                    "verify_due": self._format_datetime(record.get("verify_due")),
                    "sla_breached": self._safe_bool(record.get("sla_breached")),
                    "assigned_to": record.get("assigned_to"),
                },
            )

        for record in frames.get("facts_waivers", []):
            if not isinstance(record, dict):
                continue
            add(
                "facts_waivers",
                {
                    "waiver_id": record.get("waiver_id"),
                    "remediation_unit_id": record.get("remediation_unit_id"),
                    "risk_tier": record.get("risk_tier"),
                    "status": record.get("status"),
                    "expires_at": self._format_datetime(record.get("expires_at")),
                    "requested_at": self._format_datetime(record.get("requested_at")),
                    "requested_by": record.get("requested_by"),
                },
            )

        for record in frames.get("dim_assets", []):
            if not isinstance(record, dict):
                continue
            context = record.get("application_context") or {}
            add(
                "dim_assets",
                {
                    "asset_id": record.get("asset_id"),
                    "application": context.get("application"),
                    "owner": context.get("owner"),
                    "environment": context.get("environment"),
                    "criticality": context.get("criticality"),
                    "ownership_status": record.get("ownership_status"),
                },
            )

        return rows

    @staticmethod
    def _format_datetime(value) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, datetime):
            dt = value.astimezone(timezone.utc)
            return dt.replace(microsecond=0).isoformat()
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
            except ValueError:
                return value
        return str(value)

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"true", "1", "yes", "y"}
        return bool(value)

    def _serialize_records(self, records: List[dict]) -> Tuple[bytes, str]:
        export_format = self._export_format
        if export_format == "parquet":
            try:
                import pyarrow as pa  # type: ignore
                import pyarrow.parquet as pq  # type: ignore
            except ImportError:  # pragma: no cover - optional dependency
                logger.warning("pyarrow not installed; falling back to CSV export for reporting dataset")
                export_format = "csv"
            else:
                table = pa.Table.from_pylist(records) if records else pa.table({})
                buffer = io.BytesIO()
                pq.write_table(table, buffer)
                return buffer.getvalue(), "application/octet-stream"

        if export_format == "csv":
            buffer = io.StringIO()
            if records:
                fieldnames = sorted({key for record in records for key in record.keys()})
                writer = csv.DictWriter(buffer, fieldnames=fieldnames)
                writer.writeheader()
                for record in records:
                    writer.writerow(record)
            else:
                buffer.write("")
            return buffer.getvalue().encode("utf-8"), "text/csv"

        raise ValueError(f"Unsupported export format: {export_format}")

    @staticmethod
    def _to_records(models) -> List[dict]:
        return [ReportingExportService._normalize_record(model.model_dump(mode="json")) for model in models]

    @staticmethod
    def _normalize_record(value):
        if isinstance(value, dict):
            if not value:
                return None
            return {key: ReportingExportService._normalize_record(val) for key, val in value.items()}
        if isinstance(value, list):
            return [ReportingExportService._normalize_record(item) for item in value]
        return value

    def _build_run_event(
        self,
        *,
        correlation_id: str,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        metrics: Optional[Dict[str, int]] = None,
        error: Optional[str] = None,
    ) -> RunEventRecord:
        record = RunEventRecord(
            id=correlation_id,
            correlation_id=correlation_id,
            agent_name=AgentType.REPORTING.value,
            run_type="reporting_export",
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics or {},
            error=error,
        )
        record.timestamp = completed_at or started_at or datetime.now(timezone.utc)
        return record


__all__ = ["ReportingExportService"]
