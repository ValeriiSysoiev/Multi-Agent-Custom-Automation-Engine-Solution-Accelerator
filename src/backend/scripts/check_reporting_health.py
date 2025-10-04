"""Health check script for the reporting export job."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob.aio import BlobServiceClient
from azure.core.credentials import AzureNamedKeyCredential

from helpers.azure_credential_utils import (
    get_azure_credential_async,
    resolve_managed_identity_client_id,
)
from models.messages_kernel import AgentType
from repositories.run_event_repository import RunEventRepository
from services.reporting_config import load_reporting_config

logger = logging.getLogger(__name__)


DEFAULT_MAX_AGE_HOURS = 30


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate recent reporting export runs")
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=DEFAULT_MAX_AGE_HOURS,
        help="Maximum allowed age in hours for the latest successful run (default: %(default)s)",
    )
    parser.add_argument(
        "--require-refresh",
        action="store_true",
        help="Fail if the most recent run did not trigger a Power BI refresh",
    )
    parser.add_argument(
        "--check-storage",
        action="store_true",
        help="Validate that blobs exist for the most recent run date segment",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON payload instead of human readable output",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


async def _verify_storage(date_segment: str, config: Dict[str, Any]) -> Dict[str, Any]:
    account = (config.get("storage_account") or "").strip()
    container = (config.get("storage_container") or "").strip()
    if not account or account.lower() == "tbd" or not container:
        return {
            "checked": False,
            "issue": "Storage account or container is not configured",
        }

    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
    credential = None
    if connection_string:
        blob_service = BlobServiceClient.from_connection_string(connection_string)
    else:
        managed_identity_cfg = config.get("managed_identity_client_id")
        client_id = resolve_managed_identity_client_id(managed_identity_cfg)
        if account_key:
            credential = AzureNamedKeyCredential(account, account_key)
        else:
            credential = await get_azure_credential_async(client_id=client_id)
        account_url = f"https://{account}.blob.core.windows.net"
        blob_service = BlobServiceClient(account_url=account_url, credential=credential)
    container_client = blob_service.get_container_client(container)
    prefix = f"reports/aivm/{date_segment}/"
    count = 0
    issue: Optional[str] = None
    try:
        async for _blob in container_client.list_blobs(name_starts_with=prefix):
            count += 1
            if count > 0:
                break
    except ResourceNotFoundError:
        issue = "Storage container not found"
    except Exception as exc:  # pragma: no cover - defensive
        issue = f"Failed to enumerate blobs: {exc}"
    finally:
        await blob_service.close()
        if credential and hasattr(credential, "close"):
            maybe_coro = credential.close()
            if asyncio.iscoroutine(maybe_coro):
                await maybe_coro

    return {
        "checked": True,
        "blob_prefix": prefix,
        "blob_found": count > 0,
        "issue": issue,
    }


async def _run(
    *,
    max_age_hours: int,
    require_refresh: bool,
    check_storage: bool,
    emit_json: bool,
) -> int:
    repo = RunEventRepository()
    events = await repo.list_recent_events(AgentType.REPORTING.value, limit=20)

    now = datetime.now(timezone.utc)
    result: Dict[str, Any] = {
        "status": "ok",
        "issues": [],
        "latest_event": None,
    }

    if not events:
        result["status"] = "failed"
        result["issues"].append("No reporting_export run events found")
        return _emit_result(result, emit_json)

    latest = events[0]
    timestamp = latest.completed_at or latest.started_at or latest.timestamp
    metrics = latest.metrics or {}
    result["latest_event"] = {
        "id": latest.id,
        "status": latest.status,
        "run_type": latest.run_type,
        "started_at": latest.started_at.isoformat() if latest.started_at else None,
        "completed_at": latest.completed_at.isoformat() if latest.completed_at else None,
        "timestamp": timestamp.isoformat() if timestamp else None,
        "metrics": metrics,
        "error": latest.error,
    }

    if latest.status != "completed":
        result["status"] = "failed"
        result["issues"].append(f"Latest run status is {latest.status}")

    if latest.error:
        result["issues"].append("Latest run recorded an error message")

    staleness_issue = None
    if timestamp:
        age = now - timestamp
        result["latest_event"]["age_hours"] = age.total_seconds() / 3600
        if age > timedelta(hours=max_age_hours):
            staleness_issue = f"Latest run is older than {max_age_hours}h"
    else:
        staleness_issue = "Latest run missing timestamp"

    if staleness_issue:
        result["status"] = "failed"
        result["issues"].append(staleness_issue)

    if require_refresh and metrics.get("powerbi_refresh_triggered") != 1:
        result["status"] = "failed"
        result["issues"].append("Power BI refresh was not triggered in the latest run")

    if check_storage:
        date_key = (timestamp or now).strftime("%Y%m%d")
        storage_result = await _verify_storage(date_key, load_reporting_config())
        result["storage_check"] = storage_result
        if storage_result.get("issue"):
            result["issues"].append(storage_result["issue"])
            result["status"] = "failed"
        elif not storage_result.get("blob_found"):
            result["issues"].append("No blobs found for latest run date segment")
            result["status"] = "failed"

    return _emit_result(result, emit_json)


def _emit_result(result: Dict[str, Any], emit_json: bool) -> int:
    if emit_json:
        print(json.dumps(result))
    else:
        status = result.get("status", "unknown")
        issues = result.get("issues", [])
        if issues:
            logger.error("Reporting health check status=%s issues=%s", status, ", ".join(issues))
        else:
            logger.info("Reporting health check status=%s", status)
    return 0 if result.get("status") == "ok" else 1


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)
    return asyncio.run(
        _run(
            max_age_hours=args.max_age_hours,
            require_refresh=args.require_refresh,
            check_storage=args.check_storage,
            emit_json=args.json,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
