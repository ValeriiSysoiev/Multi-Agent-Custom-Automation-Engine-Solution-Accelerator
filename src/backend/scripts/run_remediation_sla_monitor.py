"""Execute remediation SLA monitoring and emit telemetry."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Sequence

from services.remediation_sla_monitor import RemediationSlaMonitor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remediation SLA monitoring")
    parser.add_argument(
        "--ack-windows",
        type=int,
        nargs="*",
        default=[1, 3],
        help="Ack deadline windows in days (default: 1 3)",
    )
    parser.add_argument(
        "--verify-windows",
        type=int,
        nargs="*",
        default=[3, 7],
        help="Verification deadline windows in days (default: 3 7)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit metrics as JSON to stdout",
    )
    return parser.parse_args()


async def _main(*, ack_windows: Sequence[int], verify_windows: Sequence[int], output_json: bool) -> int:
    monitor = RemediationSlaMonitor()
    metrics = await monitor.evaluate(
        ack_windows=ack_windows,
        verify_windows=verify_windows,
    )
    if output_json:
        print(json.dumps({"status": "ok", "metrics": metrics}, indent=2))
    return 0


def main() -> int:
    args = parse_args()
    return asyncio.run(
        _main(
            ack_windows=args.ack_windows,
            verify_windows=args.verify_windows,
            output_json=args.json,
        )
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
