# Deduplication & Enrichment Design

This document outlines how the ingestion layer (Qualys, Defender) will feed canonical findings, the deduplication service that merges raw records, and the enrichment service that attaches business/threat context. It also identifies orchestration touchpoints for later phases.

## Goals
1. Ensure each “vulnerability on asset” exists once per canonical ID, regardless of scanner/source.
2. Maintain provenance (source references, severities, timestamps) for audit and reporting.
3. Enrich canonical records with business ownership, exposure information, and threat signals according to the AI VM governance policies.

## Data Flow Overview
```
Scanner API -> RawFinding (findings_raw)
            -> DeduplicationService -> CanonicalFinding (findings_canonical)
                                      + SyncStateRecord (sync_state)
CanonicalFinding -> EnrichmentService -> EnrichmentRecord (enrichments)
                                      -> AssetRecord (assets)
```

### Canonical ID Strategy
- `canonical_id = hash(asset_key | vuln_key | location_signature)`.
- Asset key is the highest precedence identifier (cloud resource ID, agent ID, hostname, etc.).
- Vuln key is CVE (preferred) or vendor QID.
- Location signature combines port/protocol/service/version where relevant.

## Deduplication Service
### Responsibilities
- Read new `RawFinding` items and upsert `CanonicalFinding` objects.
- Merge source metadata (severity, first_seen/last_seen, raw IDs) into existing canonical records.
- Update lifecycle status based on scanner status (open/reopened/resolved).
- Maintain `last_seen_timestamp` in `SyncStateRecord`.

### Implementation Notes
- Triggered after each ingestion run (Defender/Qualys) or as part of ingestion service.
- Use `CanoninalFindingRepository` abstractions for upsert/read.
- Handling duplicates:
  1. Generate canonical ID from incoming record.
  2. If existing record present, update sources array (merge by scanner ID/external ID).
  3. Update `severity` if new severity is higher; update `last_observed`.
  4. Manage lifecycle: `resolved` only if all sources report Fixed/Healthy.
- Store dedup telemetry in `RunEventRecord` for monitoring.

### Edge Cases
- Conflicting asset identifiers: maintain full list; `asset_id` remains highest precedence identifier.
- Multiple findings for same asset/vuln but different ports: location signature differentiates canonical ID.
- Soft delete: set status to RESOLVED when scanner reports fixed; do not remove record (respect TTLs/legal holds).

## Enrichment Service
### Responsibilities
- Fetch business ownership and asset metadata (Jira Assets CMDB).
- Mark exposure attributes (internet-facing, WAF/ACL coverage).
- Pull threat intel (Defender TI, KEV, NVD) and map CVE flags.
- Write `EnrichmentRecord` and update/insert `AssetRecord` for each canonical finding.

### Workflow
1. Collect canonical IDs needing enrichment (new or outdated). Criteria: missing enrichment record, stale `enrichment_version`, or new source data.
2. Resolve asset/application IDs via Jira Asset queries (`Application / Service`, `Host`).
3. Populate `ApplicationContext` fields: owner, criticality, environment, tags, completeness.
4. Compute `ExposureSurface`: internet flag from CMDB tags or service mapping; control coverage from WAF/EDR metadata.
5. Fetch threat signals: KEV API, Defender TI, NVD (EPSS if available). Assign confidence levels.
6. Persist enrichment record and update `AssetRecord` ownership status.
7. Queue Linkage Review if ownership unresolved after heuristics.

### Data Freshness
- Default TTLs: align with `enrichments` container (24 months). Use `enrichment_version` to flag reprocessing when source configuration changes.
- Cache CMDB lookups where feasible (Key Vault/stored secrets not required).
- Record enrichment job telemetry in `RunEventRecord`.

## Orchestration Touchpoints
- **Planner / GroupChatManager**: will trigger dedup + enrichment sequentially before triage.
- **RunEvent Metrics**: each service logs start/end/metrics; feed into reporting.
- **SyncState**: ingestion updates watermark; dedup uses canonical updates; enrichment may track `last_enriched_at` (add field later).

## Next Steps
1. Implement `DeduplicationService` class (using repositories and canonical helpers).
2. Implement `EnrichmentService` to call Jira Assets, Defender TI, KEV/NVD.
3. Extend integration tests to validate dedup/enrichment behaviour (real data) once services are in place.
4. Update orchestration (Planner/GroupChatManager) to invoke dedup → enrichment → triage.
