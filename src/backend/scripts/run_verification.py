"""Entrypoint to execute verification batches."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from typing import Optional

from services.verification_service import VerificationService

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run verification batch")
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("VERIFICATION_BATCH_LIMIT", "50")),
        help="Maximum number of tickets to evaluate per run (default: 50).",
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


async def _run(limit: int, emit_json: bool) -> int:
    service = VerificationService()
    try:
        metrics = await service.process_pending_tickets(limit=limit)
    finally:
        await service.close()
    if emit_json:
        print(json.dumps(metrics))
    else:
        logger.info(
            "Verification run complete: processed=%d verified=%d reopened=%d",
            metrics["processed"], metrics["verified"], metrics["reopened"],
        )
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)
    return asyncio.run(_run(args.limit, args.json))


if __name__ == "__main__":
    raise SystemExit(main())
