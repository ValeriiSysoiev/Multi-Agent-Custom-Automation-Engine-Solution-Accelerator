"""Remove seeded waiver fixtures used for telemetry validation."""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from repositories.waiver_repository import WaiverRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)

WAIVER_IDS: Sequence[str] = (
    "wa-seed-ru-pending",
    "wa-seed-ru-due",
)


async def _delete_seed_waivers() -> None:
    repo = WaiverRepository()
    removed = 0
    for waiver_id in WAIVER_IDS:
        waiver = await repo.get_by_id(waiver_id)
        if waiver is None:
            LOGGER.info("Waiver %s not found", waiver_id)
            continue
        if not waiver.remediation_unit_id:
            LOGGER.warning(
                "Waiver %s has no remediation_unit_id partition key; skipping", waiver_id
            )
            continue
        await repo.delete(waiver.id, waiver.remediation_unit_id)
        LOGGER.info(
            "Deleted waiver %s (partition_key=%s)", waiver_id, waiver.remediation_unit_id
        )
        removed += 1
    LOGGER.info("Cleanup complete; %d waiver records removed", removed)


def main() -> None:
    asyncio.run(_delete_seed_waivers())


if __name__ == "__main__":
    main()
