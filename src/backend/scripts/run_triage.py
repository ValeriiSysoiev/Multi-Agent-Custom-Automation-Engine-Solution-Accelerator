"""Entrypoint to execute a triage batch outside the agent framework."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from typing import Optional

from services.triage_service import TriageService

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AI VM triage batch")
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("TRIAGE_BATCH_LIMIT", "50")),
        help="Maximum number of canonical findings to triage in one run (default: 50).",
    )
    parser.add_argument(
        "--actor",
        default=os.getenv("TRIAGE_ACTOR", "Triage_Agent"),
        help="Actor identifier recorded in triage records (default: Triage_Agent).",
    )
    parser.add_argument(
        "--disable-llm",
        action="store_true",
        help="Disable LLM reasoning even if configured (forces deterministic scoring only).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON summary instead of human-readable text",
    )
    return parser.parse_args(argv)


async def _run(limit: int, actor: str, disable_llm: bool, emit_json: bool) -> int:
    service = TriageService(enable_llm=not disable_llm)
    try:
        records = await service.triage_findings(limit=limit, actor=actor)
    finally:
        await service.close()

    summary = {
        "triaged_count": len(records),
        "triage_ids": [record.triage_id for record in records],
    }

    if emit_json:
        print(json.dumps(summary))
    else:
        logger.info(
            "Triage run complete: processed %d findings", summary["triaged_count"]
        )
        if summary["triaged_count"]:
            logger.info("Triaged IDs: %s", ", ".join(summary["triage_ids"]))

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)
    return asyncio.run(_run(args.limit, args.actor, args.disable_llm, args.json))


if __name__ == "__main__":
    raise SystemExit(main())
