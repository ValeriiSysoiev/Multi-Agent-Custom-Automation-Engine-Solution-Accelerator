"""Entrypoint to execute remediation planning and ticketing."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from typing import Optional

from services.remediation_service import RemediationService

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AI VM remediation batch")
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("REMEDIATION_BATCH_LIMIT", "50")),
        help="Maximum number of canonical findings to remediate in one run (default: 50).",
    )
    parser.add_argument(
        "--actor",
        default=os.getenv("REMEDIATION_ACTOR", "Remediation_Agent"),
        help="Actor identifier recorded in remediation units (default: Remediation_Agent).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON summary instead of text",
    )
    return parser.parse_args(argv)


async def _run(limit: int, actor: str, emit_json: bool) -> int:
    service = RemediationService()
    try:
        result = await service.plan_and_create(limit=limit, actor=actor)
    finally:
        await service.close()

    summary = {
        "units_created": result.unit_count,
        "tickets_created": result.ticket_count,
        "skipped": result.skipped,
    }

    if emit_json:
        print(json.dumps(summary))
    else:
        logger.info(
            "Remediation run complete: units=%d tickets=%d skipped=%d",
            summary["units_created"],
            summary["tickets_created"],
            len(summary["skipped"]),
        )
        if summary["skipped"]:
            logger.info("Skipped canonical IDs: %s", ", ".join(summary["skipped"].keys()))

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)
    return asyncio.run(_run(args.limit, args.actor, args.json))


if __name__ == "__main__":
    raise SystemExit(main())
