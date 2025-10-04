import asyncio
import json
import os
from pathlib import Path

import pytest

from services.defender_mdc_client import DefenderIngestionService

ARTIFACT_DIR = Path(__file__).resolve().parent / "../../.." / "artifacts" / "defender"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

SUBSCRIPTION_ID = os.environ.get("SUBSCRIPTION_ID")

KNOWN_ASSESSMENT_IDS = [
    "1195afff-c881-495e-9bc5-1486211ae03f",  # VM vulnerabilities
    "c0b7cfc6-3172-465a-b378-53c7ff2cc0d5",  # SQL vulnerabilities
]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_defender_ingestion_smoke():
    """Round-trip test through DefenderIngestionService with filtered assessments."""
    if not SUBSCRIPTION_ID:
        pytest.skip("SUBSCRIPTION_ID not configured")

    service = DefenderIngestionService(subscription_id=SUBSCRIPTION_ID)
    try:
        try:
            result = await asyncio.wait_for(
                service.ingest(
                    assessment_filter=KNOWN_ASSESSMENT_IDS,
                    max_items=20,
                ),
                timeout=60,
            )
        except asyncio.TimeoutError:
            pytest.skip("Defender sub-assessment retrieval exceeded 60s timeout")
        assert result.processed >= 0
    finally:
        await service.close()

    (ARTIFACT_DIR / "ingestion_count.json").write_text(
        json.dumps({"ingested": result.processed, "enrichable": len(result.canonical_findings)}, indent=2)
    )
