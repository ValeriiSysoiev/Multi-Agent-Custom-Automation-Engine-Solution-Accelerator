"""Entrypoint to process waiver expiry checks."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from services.waiver_service import WaiverService
from services.log_analytics_client import LogAnalyticsClient

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run waiver expiry sweep")
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("WAIVER_EXPIRY_LIMIT", "200")),
        help="Maximum number of active waivers to scan per run (default: 200).",
    )
    parser.add_argument(
        "--monitor-windows",
        nargs="*",
        type=int,
        default=None,
        help="Days-before-expiry thresholds for renewal monitoring (default: 7 3 1).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON summary",
    )
    return parser.parse_args(argv)


def _resolve_windows(env_value: Optional[str], cli_values: Optional[List[int]]) -> List[int]:
    if cli_values is not None and len(cli_values) > 0:
        return cli_values
    if env_value:
        try:
            return [int(value.strip()) for value in env_value.split(",") if value.strip()]
        except ValueError:
            logger.warning("Invalid WAIVER_MONITOR_WINDOWS value '%s'; falling back to defaults", env_value)
    return [7, 3, 1]


async def _run(limit: int, windows: List[int], emit_json: bool) -> int:
    service = WaiverService()
    try:
        expired = await service.expire_waivers(limit=limit)
        metrics = await service.monitor_waivers(renewal_windows=windows, limit=limit)
    finally:
        await service.close()

    result = {"expired": expired, **metrics}
    await _send_metrics_to_log_analytics(result, windows)

    if emit_json:
        print(json.dumps(result))
    else:
        logger.info("Waiver checks complete: %s", result)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)
    env_windows = os.getenv("WAIVER_MONITOR_WINDOWS")
    windows = _resolve_windows(env_windows, args.monitor_windows)
    return asyncio.run(_run(args.limit, windows, args.json))


def _create_log_analytics_client() -> Optional[LogAnalyticsClient]:
    workspace_id = os.getenv("LOG_ANALYTICS_WORKSPACE_ID")
    shared_key = os.getenv("LOG_ANALYTICS_SHARED_KEY")
    if not workspace_id or not shared_key:
        return None

    log_type = os.getenv("LOG_ANALYTICS_LOG_TYPE", "WaiverMonitorMetrics")
    try:
        return LogAnalyticsClient(workspace_id, shared_key, log_type)
    except ValueError as exc:  # pragma: no cover - configuration guard
        logger.warning("Invalid Log Analytics configuration: %s", exc)
        return None


async def _send_metrics_to_log_analytics(result: Dict[str, int], windows: List[int]) -> None:
    client = _create_log_analytics_client()
    if not client:
        logger.info("Skipping Log Analytics publish; configuration not provided")
        return

    record = _build_log_record(result, windows)
    logger.info("Publishing waiver metrics to Log Analytics run_id=%s", record.get("RunId_s"))
    await client.send([record])


def _build_log_record(result: Dict[str, int], windows: List[int]) -> Dict[str, object]:
    run_id = str(uuid4())
    record: Dict[str, object] = {
        "RunId_s": run_id,
        "RunTimestamp": datetime.now(timezone.utc),
        "RenewalWindows": windows,
    }

    for key, value in result.items():
        record[_normalize_field_name(key)] = value

    record["HasPendingDecision"] = bool(result.get("pending_decision", 0))
    record["Source"] = "waiver_monitor"
    return record


def _normalize_field_name(name: str) -> str:
    parts = [part for part in name.split("_") if part]
    if not parts:
        return name

    normalized = "".join(part[:1].upper() + part[1:] for part in parts)
    if normalized and normalized[0].isdigit():
        normalized = f"_{normalized}"
    return normalized


if __name__ == "__main__":
    raise SystemExit(main())
