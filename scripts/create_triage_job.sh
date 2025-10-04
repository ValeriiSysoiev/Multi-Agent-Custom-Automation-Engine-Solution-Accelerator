#!/usr/bin/env bash
# Helper to create/update the triage Container Apps job.
# Requires az CLI logged into the subscription and azd env values set.

set -euo pipefail

: "${AZURE_ENV_NAME:?Use 'azd env set AZURE_ENV_NAME <name>' to populate.}"
: "${AZURE_RESOURCE_GROUP:?Use 'azd env set AZURE_RESOURCE_GROUP <name>' to populate.}"
: "${TRIAGE_JOB_NAME:=aivm-triage-job}"
: "${TRIAGE_IMAGE:?Set TRIAGE_IMAGE to the backend container image (e.g. <acr>.azurecr.io/aivm-prod-backend:latest).}"
: "${CRON_EXPRESSION:=0 * * * *}"

KEYVAULT_URI=$(azd env get-value KEYVAULT_URI)
COSMOSDB_ENDPOINT=$(azd env get-value COSMOSDB_ENDPOINT)
COSMOSDB_DATABASE=$(azd env get-value COSMOSDB_DATABASE)
AZURE_OPENAI_ENDPOINT=$(azd env get-value AZURE_OPENAI_ENDPOINT)

az containerapp job create \
  --name "$TRIAGE_JOB_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --environment "$AZURE_ENV_NAME" \
  --trigger-type Scheduled \
  --cron-expression "$CRON_EXPRESSION" \
  --image "$TRIAGE_IMAGE" \
  --parallelism 1 \
  --replica-timeout 1800 \
  --replica-retry-limit 1 \
  --command "/bin/sh" "-c" "python -m scripts.run_triage --limit ${TRIAGE_BATCH_LIMIT:-100} --json" \
  --env-vars \
    KEYVAULT_URI="$KEYVAULT_URI" \
    COSMOSDB_ENDPOINT="$COSMOSDB_ENDPOINT" \
    COSMOSDB_DATABASE="$COSMOSDB_DATABASE" \
    AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
    TRIAGE_BATCH_LIMIT="${TRIAGE_BATCH_LIMIT:-100}" \
    TRIAGE_ACTOR="${TRIAGE_ACTOR:-Triage_Agent}"

az containerapp job start --name "$TRIAGE_JOB_NAME" --resource-group "$AZURE_RESOURCE_GROUP"
