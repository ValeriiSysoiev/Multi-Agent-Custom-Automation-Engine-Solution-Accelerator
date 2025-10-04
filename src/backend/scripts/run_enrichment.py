"""Entrypoint to execute enrichment for canonical findings."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from typing import Optional

from repositories.canonical_finding_repository import CanonicalFindingRepository
from services.enrichment_service import EnrichmentService

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run enrichment for canonical findings")
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("ENRICHMENT_BATCH_LIMIT", "100")),
        help="Maximum number of canonical findings to consider (default: 100).",
    )
    parser.add_argument(
        "--actor",
        default=os.getenv("ENRICHMENT_ACTOR", "Enrichment_Service"),
        help="Actor identifier for logging (unused in enrichment but captured in output).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON summary instead of human-readable logs",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


async def _run(limit: int, emit_json: bool) -> int:
    canonical_repo = CanonicalFindingRepository()
    service = EnrichmentService()
    try:
        candidates = await canonical_repo.list_pending_triage(limit=limit)
        if not candidates:
            summary = {"processed": 0, "enriched": 0}
            if emit_json:
                print(json.dumps(summary))
            else:
                logger.info("No canonical findings pending enrichment")
            return 0

        logger.info("Processing %d candidate findings for enrichment", len(candidates))
        enriched_records = await service.enrich_findings(candidates)
        summary = {
            "processed": len(candidates),
            "enriched": len(enriched_records),
            "canonical_ids": [record.canonical_id for record in enriched_records],
        }

        if emit_json:
            print(json.dumps(summary))
        else:
            logger.info(
                "Enrichment run complete: processed=%d enriched=%d",
                summary["processed"],
                summary["enriched"],
            )
            if summary["enriched"]:
                logger.info("Enriched canonical IDs: %s", ", ".join(summary["canonical_ids"]))
    finally:
        await service.close()

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)
    return asyncio.run(_run(args.limit, args.json))


if __name__ == "__main__":
    raise SystemExit(main())
