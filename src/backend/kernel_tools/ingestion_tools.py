import json
import os

from semantic_kernel.functions import kernel_function

from models.messages_kernel import AgentType
from services.defender_mdc_client import DefenderIngestionService
from services.qualys_client import QualysIngestionService
from services.vulnerability_pipeline import PipelineRunResult, VulnerabilityPipeline
from .generic_tools import GenericTools


class IngestionTools(GenericTools):
    """Tools that orchestrate scanner ingestion and dedup pipeline."""

    agent_name = AgentType.INGESTION.value

    @staticmethod
    @kernel_function(
        description="Run the vulnerability ingestion pipeline for Defender and Qualys, returning a summary of findings processed."
    )
    async def run_ingestion_cycle() -> str:
        """Execute the ingestion pipeline once and return a JSON summary."""

        subscription_id = os.getenv("SUBSCRIPTION_ID")
        if not subscription_id:
            raise ValueError("SUBSCRIPTION_ID environment variable is required to run the Defender ingestion.")

        qualys_base_url = os.getenv("QUALYS_BASE_URL")

        defender_service = DefenderIngestionService(subscription_id=subscription_id)
        qualys_service = QualysIngestionService(base_url=qualys_base_url)
        pipeline = VulnerabilityPipeline(
            defender_ingestion=defender_service,
            qualys_ingestion=qualys_service,
        )

        try:
            result: PipelineRunResult = await pipeline.run_cycle()
        finally:
            await pipeline.close()

        summary = {
            "total_ingested": result.total_ingested,
            "total_enriched": result.total_enriched,
            "scanners": [
                {
                    "scanner": ingestion.scanner_id,
                    "processed": ingestion.processed,
                    "canonical_count": len(ingestion.canonical_findings),
                }
                for ingestion in result.ingestion_results
            ],
            "enriched_canonical_ids": result.enriched,
        }

        return json.dumps(summary)
