#!/usr/bin/env python3
"""Purge demo data from Cosmos DB containers.

This script deletes all documents from the standard vulnerability-management containers
used by the solution accelerator so you can re-run the end-to-end workflow from a clean
state. Containers are *not* dropped; only their contents are removed.

Usage:
    python3 scripts/clear_cosmos_demo_data.py --account cosmos-aivmprodcliu3 \
        --database macae --resource-group RG-AIVM --yes

Authentication:
    Uses DefaultAzureCredential, so ensure you are logged in with `az login` or have
    appropriate environment variables set.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

# Default container -> partition key field mapping
DEFAULT_CONTAINERS: Dict[str, str] = {
    "findings_raw": "scanner_id",
    "findings_canonical": "asset_id",
    "enrichments": "asset_id",
    "triage_items": "canonical_id",
    "remediation_units": "remediation_unit_id",
    "tickets": "remediation_unit_id",
    "waivers": "remediation_unit_id",
    "runs_events": "agent_name",
    "assets": "asset_id",
    "risk_treatments": "workflow",
    "evidence": "canonical_id",
    "sync_state": "scanner_id",
    "memory": "session_id",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clear Cosmos DB demo data")
    parser.add_argument("--account", required=True, help="Cosmos DB account name")
    parser.add_argument("--resource-group", required=True, help="Resource group")
    parser.add_argument("--database", required=True, help="Database name")
    parser.add_argument(
        "--containers",
        nargs="*",
        help="Optional list of containers to wipe (default: all known vulnerability containers)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List item counts without deleting")
    parser.add_argument(
        "--yes",
        action="store_true",
        dest="assume_yes",
        help="Skip confirmation prompt",
    )
    return parser.parse_args()


def confirm(prompt: str) -> bool:
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def main() -> int:
    args = parse_args()

    containers = DEFAULT_CONTAINERS.copy()
    if args.containers:
        missing = [name for name in args.containers if name not in containers]
        if missing:
            print(f"Unknown containers: {', '.join(missing)}", file=sys.stderr)
            return 1
        containers = {name: containers[name] for name in args.containers}

    note = "NOTE: Dry run only" if args.dry_run else "This will permanently delete documents."
    summary = ", ".join(containers.keys())
    if not args.assume_yes:
        if not confirm(f"About to clear containers [{summary}] in database '{args.database}'. {note}"):
            print("Aborted.")
            return 0

    endpoint = f"https://{args.account}.documents.azure.com"
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
    client = CosmosClient(endpoint, credential=credential)
    database = client.get_database_client(args.database)

    total_deleted = 0
    for container_name, pk_field in containers.items():
        container = database.get_container_client(container_name)
        print(f"Processing {container_name} (partition key: {pk_field})...")
        deleted = 0
        for item in container.read_all_items():
            pk_value = item.get(pk_field)
            if pk_value is None:
                continue
            if args.dry_run:
                deleted += 1
                continue
            container.delete_item(item=item["id"], partition_key=pk_value)
            deleted += 1
        total_deleted += deleted
        action = "Identified" if args.dry_run else "Deleted"
        print(f"  {action} {deleted} documents")

    final_msg = "Dry run complete." if args.dry_run else f"Done. Deleted {total_deleted} documents."
    print(final_msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
