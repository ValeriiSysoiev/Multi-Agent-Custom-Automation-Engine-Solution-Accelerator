import json
import os
from pathlib import Path

import pytest

from services.qualys_client import QualysIngestionService

ARTIFACT_DIR = Path(__file__).resolve().parent / "../../.." / "artifacts" / "qualys"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("QUALYS_BASE_URL")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_qualys_ingestion_smoke():
    if not BASE_URL:
        pytest.skip("QUALYS_BASE_URL not configured")

    service = QualysIngestionService(base_url=BASE_URL)
    try:
        result = await service.ingest()
        assert result.processed >= 0
    finally:
        await service.close()

    with (ARTIFACT_DIR / "recent_counts.json").open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "ingested": result.processed,
                "enrichable": len(result.canonical_findings),
            },
            fh,
            indent=2,
        )
