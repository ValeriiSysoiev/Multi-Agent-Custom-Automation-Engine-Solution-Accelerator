# Cosmos Schema & Migration Plan

This document captures the Cosmos DB configuration (containers, partition keys, TTL, indexes) and outlines the steps to transition from the accelerator’s original schema to the AI Vulnerability Management data model.

## 1. Containers & Partitioning
All containers should be provisioned within the Cosmos account in Canada Central (with geo-failover to Canada East) using autoscale throughput where possible.

| Container | Partition Key | TTL (Default) | Notes |
|-----------|---------------|---------------|-------|
| `findings_raw` | `/scanner_id` | 90 days | Append-only; optional nightly export to Blob for 12 m archive. |
| `sync_state` | `/scanner_id` | -1 (no expiry) | Only one item per scanner; small. |
| `findings_canonical` | `/asset_id` | 24 months | Store `canonical_id` as unique key; `remediation_unit_id` links to active remediation work. |
| `enrichments` | `/asset_id` | 24 months | Mirror `canonical_id` via secondary index for quick lookups. |
| `triage_items` | `/canonical_id` | 36 months | Append-only; include composite index on (`canonical_id`, `timestamp`). |
| `remediation_units` | `/remediation_unit_id` | 36 months (align to tickets) | Grouping structure; store canonical list and metadata. |
| `tickets` | `/remediation_unit_id` | 36 months (18 months post-Resolved w/o verification) | Secondary index on `ticket_id` for direct lookups. |
| `evidence` | `/canonical_id` | 60 months | If evidence ties to remediation unit only, store `canonical_id=null` and index on `/remediation_unit_id`. |
| `assets` | `/asset_id` | 24 months | Authoritative identity store; use unique keys for `asset_id`. |
| `runs_events` | `/agent_name` | 180 days | Short-lived telemetry; consider separate diagnostic account if volume high. |
| `waivers` | `/remediation_unit_id` | 36 months | Track approvals/renewals; include composite index on (`remediation_unit_id`, `expires_at`). |
| `risk_treatments` | `/workflow` | 36 months | Queue for accept/transfer follow-ups (waiver or risk-transfer workflows) including justification, compensating controls, proposed expiry, and Jira ticket metadata; index on (`workflow`, `status`). |

### 1.1 Indexing Recommendations
- Enable automatic indexing for all containers.
- Add composite indexes where high cardinality queries exist:
  - `findings_canonical`: composite (`asset_id`, `risk_tier`), (`risk_tier`, `status`).
  - `triage_items`: (`canonical_id`, `timestamp` DESC).
  - `tickets`: (`remediation_unit_id`, `status`), (`status`, `due_at`).
  - `evidence`: (`canonical_id`, `verification_status`), (`remediation_unit_id`, `verification_status`).
- `waivers`: (`remediation_unit_id`, `status`), (`status`, `expires_at`).
- `risk_treatments`: (`workflow`, `status`), (`canonical_id`, `status`).
- Maintain unique constraints at application layer (Cosmos lacks native unique across partitions).

## 2. Migration Strategy
The original accelerator stores sessions, plans, steps, and agent messages in a single container. The AI VM solution introduces multiple domain-specific containers. Migration is staged as follows:

1. **Deploy new containers** with the partition keys and TTLs above. No data migration from old accelerator tables is required (new AI VM data flows will populate new containers).
2. **Update application configuration** to point to the new container names where applicable (future phases will inject the correct container names into repositories).
3. **Retain legacy container** (`memory`) for session/plan history until new flows are implemented. Once new agents no longer depend on legacy structures, archive/export the legacy data and decommission the old schema.
4. **Seed reference data** (if required) for assets or waiver approvers by writing initial `AssetRecord` or `WaiverRecord` entries via management scripts.
5. **Backfill** (optional) sample data for testing by using the migration utility or manual scripts to insert canonical findings, triage records, etc.

## 3. Operational Scripts/Utilities
Create a set of utilities under `scripts/` (future work) to:
- Create containers with specified TTL/index policies (`az cosmosdb sql container create`).
- Export near-expiry items to Blob storage (nightly job).
- Backfill canonical findings for integration testing.
- Perform waiver and evidence clean-up (respect TTL, audit logs).

## 4. Configuration Updates
- Update backend settings (`COSMOSDB_CONTAINER_*` env values or config) to reference individual containers if the application uses separate containers per data type.
- Ensure connection string/endpoint/DB name remain consistent; only container names change.
- Update deployment pipelines (Bicep/azd) once the schema is integrated into infrastructure code. Until then, manual container creation is acceptable for development.

## 5. Validation Checklist
- Containers exist with correct partition keys and TTLs.
- Indexing policies applied; composite indexes tested on expected query patterns.
- Managed identity for backend has Data Contributor rights on new containers.
- Continuous backup (PITR) enabled and verified.
- Backup/restore drill (Quarterly) documented pointing to new containers.
- Blob archival job configured for `findings_raw` and long-term storage.

This document should be updated once infrastructure code (Bicep/Terraform) incorporates the new containers or if policies change.
