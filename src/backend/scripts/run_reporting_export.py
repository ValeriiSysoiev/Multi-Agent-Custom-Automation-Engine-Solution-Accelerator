"""Entrypoint for reporting dataset exports."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Optional

from services.reporting_export_service import ReportingExportService

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run reporting dataset export")
    parser.add_argument(
        "--date",
        dest="date_key",
        help="Override export date segment (default: current UTC YYYYMMDD)",
    )
    parser.add_argument(
        "--refresh-powerbi",
        action="store_true",
        help="Trigger Power BI dataset refresh after export",
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


async def _run(date_key: Optional[str], refresh_powerbi: bool, emit_json: bool) -> int:
    service = ReportingExportService()
    try:
        metrics = await service.export(date_key=date_key, refresh_powerbi=refresh_powerbi)
    finally:
        await service.close()
    if emit_json:
        print(json.dumps(metrics))
    else:
        logger.info("Reporting export complete: %s", metrics)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)
    return asyncio.run(_run(args.date_key, args.refresh_powerbi, args.json))


if __name__ == "__main__":
    raise SystemExit(main())
