#!/usr/bin/env bash
# Helper to create/update the reporting export Container Apps job.

set -euo pipefail

: "${AZURE_ENV_NAME:?Set via 'azd env set AZURE_ENV_NAME <name>'}"
: "${CONTAINERAPPS_ENV_NAME:=$AZURE_ENV_NAME}"
: "${AZURE_RESOURCE_GROUP:?Set via 'azd env set AZURE_RESOURCE_GROUP <name>'}"
: "${REPORTING_JOB_NAME:=aivm-reporting-job}"
: "${REPORTING_IMAGE:?Provide container image (e.g. <acr>.azurecr.io/aivm-prod-backend:latest).}"
: "${CRON_EXPRESSION:=0 2 * * *}"

KEYVAULT_URI=$(azd env get-value KEYVAULT_URI)
COSMOSDB_ENDPOINT=$(azd env get-value COSMOSDB_ENDPOINT)
COSMOSDB_DATABASE=$(azd env get-value COSMOSDB_DATABASE)
AZURE_OPENAI_ENDPOINT=$(azd env get-value AZURE_OPENAI_ENDPOINT)
AZURE_OPENAI_DEPLOYMENT_NAME=$(azd env get-value AZURE_OPENAI_DEPLOYMENT_NAME 2>/dev/null || echo "")
AZURE_OPENAI_API_VERSION=$(azd env get-value AZURE_OPENAI_API_VERSION 2>/dev/null || echo "")
AZURE_AI_SUBSCRIPTION_ID=$(azd env get-value AZURE_AI_SUBSCRIPTION_ID 2>/dev/null || echo "")
AZURE_AI_RESOURCE_GROUP=$(azd env get-value AZURE_AI_RESOURCE_GROUP 2>/dev/null || echo "")
AZURE_AI_PROJECT_NAME=$(azd env get-value AZURE_AI_PROJECT_NAME 2>/dev/null || echo "")
AZURE_AI_AGENT_ENDPOINT=$(azd env get-value AZURE_AI_AGENT_ENDPOINT 2>/dev/null || echo "")
AZURE_CLIENT_ID_VALUE=${AZURE_CLIENT_ID:-$(azd env get-value AZURE_CLIENT_ID 2>/dev/null || echo "")}
AZURE_MANAGED_IDENTITY_CLIENT_ID_VALUE=${AZURE_MANAGED_IDENTITY_CLIENT_ID:-$(azd env get-value AZURE_MANAGED_IDENTITY_CLIENT_ID 2>/dev/null || echo "")}
REPORTING_MANAGED_IDENTITY_CLIENT_ID=${REPORTING_MANAGED_IDENTITY_CLIENT_ID:-$AZURE_MANAGED_IDENTITY_CLIENT_ID_VALUE}
PBI_WORKSPACE_ID_VALUE=${PBI_WORKSPACE_ID:-$(azd env get-value PBI_WORKSPACE_ID 2>/dev/null || echo "")}
PBI_DATASET_ID_VALUE=${PBI_DATASET_ID:-$(azd env get-value PBI_DATASET_ID 2>/dev/null || echo "")}
PBI_CLIENT_ID_VALUE=${PBI_CLIENT_ID:-$(azd env get-value PBI_CLIENT_ID 2>/dev/null || echo "")}
PBI_CLIENT_SECRET_SECRET_NAME_VALUE=${PBI_CLIENT_SECRET_SECRET_NAME:-$(azd env get-value PBI_CLIENT_SECRET_SECRET_NAME 2>/dev/null || echo "")}
KV_BASE=${KEYVAULT_URI%/}

: "${PBI_CLIENT_SECRET_SECRET_NAME_VALUE:?Set PBI_CLIENT_SECRET_SECRET_NAME in the shell or via 'azd env set-secret'}"

env_args=(
  KEYVAULT_URI="$KEYVAULT_URI"
  COSMOSDB_ENDPOINT="$COSMOSDB_ENDPOINT"
  COSMOSDB_DATABASE="$COSMOSDB_DATABASE"
  AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT"
)

[[ -n "$AZURE_OPENAI_DEPLOYMENT_NAME" ]] && env_args+=(AZURE_OPENAI_DEPLOYMENT_NAME="$AZURE_OPENAI_DEPLOYMENT_NAME")
[[ -n "$AZURE_OPENAI_API_VERSION" ]] && env_args+=(AZURE_OPENAI_API_VERSION="$AZURE_OPENAI_API_VERSION")
[[ -n "$AZURE_AI_SUBSCRIPTION_ID" ]] && env_args+=(AZURE_AI_SUBSCRIPTION_ID="$AZURE_AI_SUBSCRIPTION_ID")
[[ -n "$AZURE_AI_RESOURCE_GROUP" ]] && env_args+=(AZURE_AI_RESOURCE_GROUP="$AZURE_AI_RESOURCE_GROUP")
[[ -n "$AZURE_AI_PROJECT_NAME" ]] && env_args+=(AZURE_AI_PROJECT_NAME="$AZURE_AI_PROJECT_NAME")
[[ -n "$AZURE_AI_AGENT_ENDPOINT" ]] && env_args+=(AZURE_AI_AGENT_ENDPOINT="$AZURE_AI_AGENT_ENDPOINT")
[[ -n "$AZURE_CLIENT_ID_VALUE" ]] && env_args+=(AZURE_CLIENT_ID="$AZURE_CLIENT_ID_VALUE")
[[ -n "$AZURE_MANAGED_IDENTITY_CLIENT_ID_VALUE" ]] && env_args+=(AZURE_MANAGED_IDENTITY_CLIENT_ID="$AZURE_MANAGED_IDENTITY_CLIENT_ID_VALUE")
[[ -n "$REPORTING_MANAGED_IDENTITY_CLIENT_ID" ]] && env_args+=(REPORTING_MANAGED_IDENTITY_CLIENT_ID="$REPORTING_MANAGED_IDENTITY_CLIENT_ID")
[[ -n "$PBI_WORKSPACE_ID_VALUE" ]] && env_args+=(PBI_WORKSPACE_ID="$PBI_WORKSPACE_ID_VALUE")
[[ -n "$PBI_DATASET_ID_VALUE" ]] && env_args+=(PBI_DATASET_ID="$PBI_DATASET_ID_VALUE")
[[ -n "$PBI_CLIENT_ID_VALUE" ]] && env_args+=(PBI_CLIENT_ID="$PBI_CLIENT_ID_VALUE")

secret_args=()
if [[ -n "$PBI_CLIENT_SECRET_SECRET_NAME_VALUE" ]]; then
  secret_args+=(pbi-client-secret=kvref:${KV_BASE}/secrets/${PBI_CLIENT_SECRET_SECRET_NAME_VALUE})
  env_args+=(PBI_CLIENT_SECRET="secretref:pbi-client-secret")
fi

if [[ ${#secret_args[@]} -gt 0 ]]; then
  az containerapp job create \
    --name "$REPORTING_JOB_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENV_NAME" \
    --trigger-type Schedule \
    --cron-expression "$CRON_EXPRESSION" \
    --image "$REPORTING_IMAGE" \
    --parallelism 1 \
    --replica-timeout 3600 \
    --replica-retry-limit 1 \
    --command "python" \
    --args "-m scripts.run_reporting_export --refresh-powerbi --json" \
    --secrets "${secret_args[@]}" \
    --env-vars "${env_args[@]}"
else
  az containerapp job create \
    --name "$REPORTING_JOB_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENV_NAME" \
    --trigger-type Schedule \
    --cron-expression "$CRON_EXPRESSION" \
    --image "$REPORTING_IMAGE" \
    --parallelism 1 \
    --replica-timeout 3600 \
    --replica-retry-limit 1 \
    --command "python" \
    --args "-m scripts.run_reporting_export --refresh-powerbi --json" \
    --env-vars "${env_args[@]}"
fi

if [[ ${#secret_args[@]} -gt 0 ]]; then
  az containerapp job update \
    --name "$REPORTING_JOB_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --container-name "$REPORTING_JOB_NAME" \
    --image "$REPORTING_IMAGE" \
    --cron-expression "$CRON_EXPRESSION" \
    --parallelism 1 \
    --replica-timeout 3600 \
    --replica-retry-limit 1 \
    --command "python" \
    --args "-m scripts.run_reporting_export --refresh-powerbi --json" \
    --secrets "${secret_args[@]}" \
    --set-env-vars "${env_args[@]}"
else
  az containerapp job update \
    --name "$REPORTING_JOB_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --container-name "$REPORTING_JOB_NAME" \
    --image "$REPORTING_IMAGE" \
    --cron-expression "$CRON_EXPRESSION" \
    --parallelism 1 \
    --replica-timeout 3600 \
    --replica-retry-limit 1 \
    --command "python" \
    --args "-m scripts.run_reporting_export --refresh-powerbi --json" \
    --set-env-vars "${env_args[@]}"
fi

az containerapp job start --name "$REPORTING_JOB_NAME" --resource-group "$AZURE_RESOURCE_GROUP"
