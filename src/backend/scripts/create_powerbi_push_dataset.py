"""Create a Power BI push dataset matching the reporting schema."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from services.powerbi_client import PowerBIClient
from services.key_vault import KeyVaultService
from services.reporting_config import load_reporting_config

DEFAULT_DATASET_NAME = "AI VM Push"
OUTPUT_META = Path("artifacts/powerbi/push_dataset_meta.json")

TABLE_DEFINITIONS = [
    {
        "name": "facts_findings",
        "columns": [
            {"name": "canonical_id", "dataType": "string"},
            {"name": "asset_id", "dataType": "string"},
            {"name": "risk_tier", "dataType": "string"},
            {"name": "severity", "dataType": "string"},
            {"name": "status", "dataType": "string"},
            {"name": "remediation_bucket", "dataType": "string"},
            {"name": "remediation_unit_id", "dataType": "string"},
            {"name": "first_observed", "dataType": "DateTime"},
            {"name": "last_observed", "dataType": "DateTime"},
            {"name": "ownership_status", "dataType": "string"},
        ],
    },
    {
        "name": "facts_enrichment",
        "columns": [
            {"name": "canonical_id", "dataType": "string"},
            {"name": "asset_id", "dataType": "string"},
            {"name": "application", "dataType": "string"},
            {"name": "owner", "dataType": "string"},
            {"name": "environment", "dataType": "string"},
            {"name": "criticality", "dataType": "string"},
            {"name": "internet_facing", "dataType": "bool"},
            {"name": "timestamp", "dataType": "DateTime"},
        ],
    },
    {
        "name": "facts_triage",
        "columns": [
            {"name": "triage_id", "dataType": "string"},
            {"name": "canonical_id", "dataType": "string"},
            {"name": "risk_score", "dataType": "Int64"},
            {"name": "risk_tier", "dataType": "string"},
            {"name": "likelihood", "dataType": "Int64"},
            {"name": "impact", "dataType": "Int64"},
            {"name": "treatment", "dataType": "string"},
            {"name": "created_by", "dataType": "string"},
            {"name": "timestamp", "dataType": "DateTime"},
        ],
    },
    {
        "name": "facts_remediation_units",
        "columns": [
            {"name": "remediation_unit_id", "dataType": "string"},
            {"name": "name", "dataType": "string"},
            {"name": "bucket", "dataType": "string"},
            {"name": "risk_tier", "dataType": "string"},
            {"name": "status", "dataType": "string"},
            {"name": "target_due_date", "dataType": "DateTime"},
            {"name": "owner", "dataType": "string"},
        ],
    },
        {
            "name": "facts_tickets",
            "columns": [
                {"name": "ticket_id", "dataType": "string"},
                {"name": "remediation_unit_id", "dataType": "string"},
                {"name": "status", "dataType": "string"},
                {"name": "due_at", "dataType": "DateTime"},
                {"name": "ack_due", "dataType": "DateTime"},
                {"name": "verify_due", "dataType": "DateTime"},
                {"name": "sla_breached", "dataType": "bool"},
                {"name": "assigned_to", "dataType": "string"},
            ],
        },
    {
        "name": "facts_waivers",
        "columns": [
            {"name": "waiver_id", "dataType": "string"},
            {"name": "remediation_unit_id", "dataType": "string"},
            {"name": "risk_tier", "dataType": "string"},
            {"name": "status", "dataType": "string"},
            {"name": "expires_at", "dataType": "DateTime"},
            {"name": "requested_at", "dataType": "DateTime"},
            {"name": "requested_by", "dataType": "string"},
        ],
    },
    {
        "name": "dim_assets",
        "columns": [
            {"name": "asset_id", "dataType": "string"},
            {"name": "application", "dataType": "string"},
            {"name": "owner", "dataType": "string"},
            {"name": "environment", "dataType": "string"},
            {"name": "criticality", "dataType": "string"},
            {"name": "ownership_status", "dataType": "string"},
        ],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Power BI push dataset")
    parser.add_argument("--dataset-name", default=DEFAULT_DATASET_NAME)
    parser.add_argument(
        "--output",
        default=str(OUTPUT_META),
        help="Optional path to write dataset metadata",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    reporting_cfg = load_reporting_config()

    tenant_id = reporting_cfg.get("tenant_id") or os.getenv("AZURE_TENANT_ID")
    client_id = reporting_cfg.get("client_id") or os.getenv("AZURE_CLIENT_ID")
    workspace_id = reporting_cfg.get("workspace_id") or os.getenv("POWERBI_WORKSPACE_ID")

    if not tenant_id or not client_id or not workspace_id:
        raise RuntimeError(
            "Reporting configuration must include tenant_id, client_id, and workspace_id "
            "(or provide AZURE_TENANT_ID/AZURE_CLIENT_ID/POWERBI_WORKSPACE_ID env vars)."
        )

    vault = KeyVaultService()
    try:
        secret = await vault.get_secret("POWERBI-CLIENT-SECRET")
        client = PowerBIClient(tenant_id, client_id, secret)
        dataset_id = await client.create_push_dataset(
            workspace_id=workspace_id,
            dataset_name=args.dataset_name,
            tables=TABLE_DEFINITIONS,
        )
        logging.info(
            "Created dataset %s with id %s in workspace %s",
            args.dataset_name,
            dataset_id,
            workspace_id,
        )
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({"dataset_id": dataset_id}, indent=2))
        print(dataset_id)
    finally:
        await vault.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
