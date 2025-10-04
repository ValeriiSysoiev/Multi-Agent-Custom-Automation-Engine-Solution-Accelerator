"""CLI to synchronize risk treatment tasks with Jira status."""

from __future__ import annotations

import argparse
import asyncio
import json

from services.risk_treatment_sync import RiskTreatmentSync


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronize risk treatment tasks with Jira")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of tasks to evaluate")
    parser.add_argument("--json", action="store_true", help="Emit JSON metrics to stdout")
    return parser.parse_args()


async def _main(limit: int, emit_json: bool) -> int:
    syncer = RiskTreatmentSync()
    metrics = await syncer.sync(limit=limit)
    if emit_json:
        print(json.dumps({"status": "ok", "metrics": metrics}, indent=2))
    await syncer.close()
    return 0


def main() -> int:
    args = parse_args()
    return asyncio.run(_main(limit=args.limit, emit_json=args.json))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
