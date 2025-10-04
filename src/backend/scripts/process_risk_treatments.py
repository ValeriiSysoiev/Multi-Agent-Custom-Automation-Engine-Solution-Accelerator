"""CLI entry point for processing risk treatment tasks."""

from __future__ import annotations

import argparse
import asyncio
import json

from services.risk_treatment_processor import RiskTreatmentProcessor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process risk treatment follow-up tasks")
    parser.add_argument("--limit", type=int, default=25, help="Maximum number of tasks to evaluate")
    parser.add_argument("--json", action="store_true", help="Emit metrics as JSON")
    return parser.parse_args()


async def _main(limit: int, emit_json: bool) -> int:
    processor = RiskTreatmentProcessor()
    metrics = await processor.process(limit=limit)
    if emit_json:
        print(json.dumps({"status": "ok", "metrics": metrics}, indent=2))
    await processor.close()
    return 0


def main() -> int:
    args = parse_args()
    return asyncio.run(_main(limit=args.limit, emit_json=args.json))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
