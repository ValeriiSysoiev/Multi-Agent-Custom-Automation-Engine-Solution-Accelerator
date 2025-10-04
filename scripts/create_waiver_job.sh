#!/usr/bin/env bash
# Helper to create/update the waiver-expiry Container Apps job.

set -euo pipefail

: "${AZURE_ENV_NAME:?Set via 'azd env set AZURE_ENV_NAME <name>'}"
: "${CONTAINERAPPS_ENV_NAME:=$AZURE_ENV_NAME}"
: "${AZURE_RESOURCE_GROUP:?Set via 'azd env set AZURE_RESOURCE_GROUP <name>'}"
: "${WAIVER_JOB_NAME:=aivm-waiver-expiry-job}"
: "${WAIVER_IMAGE:?Provide container image (e.g. <acr>.azurecr.io/aivm-prod-backend:latest).}"
: "${CRON_EXPRESSION:=0 1 * * *}"

get_azd_value() {
  local key="$1"
  local value=""
  if value=$(azd env get-value "$key" 2>/dev/null); then
    printf '%s' "$value"
  fi
}

KEYVAULT_URI=$(azd env get-value KEYVAULT_URI)
COSMOSDB_ENDPOINT=$(azd env get-value COSMOSDB_ENDPOINT)
COSMOSDB_DATABASE=$(azd env get-value COSMOSDB_DATABASE)
AZURE_OPENAI_ENDPOINT_VALUE=${AZURE_OPENAI_ENDPOINT:-$(get_azd_value AZURE_OPENAI_ENDPOINT)}
AZURE_OPENAI_API_VERSION_VALUE=${AZURE_OPENAI_API_VERSION:-$(get_azd_value AZURE_OPENAI_API_VERSION)}
AZURE_OPENAI_DEPLOYMENT_NAME_VALUE=${AZURE_OPENAI_DEPLOYMENT_NAME:-$(get_azd_value AZURE_OPENAI_DEPLOYMENT_NAME)}
AZURE_CLIENT_ID_VALUE=${AZURE_CLIENT_ID:-$(get_azd_value AZURE_CLIENT_ID)}
AZURE_AI_SUBSCRIPTION_ID_VALUE=${AZURE_AI_SUBSCRIPTION_ID:-$(get_azd_value AZURE_AI_SUBSCRIPTION_ID)}
AZURE_AI_RESOURCE_GROUP_VALUE=${AZURE_AI_RESOURCE_GROUP:-$(get_azd_value AZURE_AI_RESOURCE_GROUP)}
AZURE_AI_PROJECT_NAME_VALUE=${AZURE_AI_PROJECT_NAME:-$(get_azd_value AZURE_AI_PROJECT_NAME)}
AZURE_AI_AGENT_ENDPOINT_VALUE=${AZURE_AI_AGENT_ENDPOINT:-$(get_azd_value AZURE_AI_AGENT_ENDPOINT)}
AZURE_MANAGED_IDENTITY_CLIENT_ID_VALUE=${AZURE_MANAGED_IDENTITY_CLIENT_ID:-$(get_azd_value AZURE_MANAGED_IDENTITY_CLIENT_ID)}
WAIVER_MONITOR_WINDOWS_VALUE=${WAIVER_MONITOR_WINDOWS:-$(get_azd_value WAIVER_MONITOR_WINDOWS)}
WAIVER_EXPIRY_LIMIT_VALUE=${WAIVER_EXPIRY_LIMIT:-200}
JIRA_BASE_URL_VALUE=${JIRA_BASE_URL:-$(get_azd_value JIRA_BASE_URL)}
JIRA_USER_EMAIL_VALUE=${JIRA_USER_EMAIL:-$(get_azd_value JIRA_USER_EMAIL)}
LOG_ANALYTICS_WORKSPACE_ID_VALUE=${LOG_ANALYTICS_WORKSPACE_ID:-$(get_azd_value LOG_ANALYTICS_WORKSPACE_ID)}
LOG_ANALYTICS_LOG_TYPE_VALUE=${LOG_ANALYTICS_LOG_TYPE:-$(get_azd_value LOG_ANALYTICS_LOG_TYPE)}
LOG_ANALYTICS_SHARED_KEY_SECRET_NAME_VALUE=${LOG_ANALYTICS_SHARED_KEY_SECRET_NAME:-$(get_azd_value LOG_ANALYTICS_SHARED_KEY_SECRET_NAME)}

: "${LOG_ANALYTICS_SHARED_KEY_SECRET_NAME_VALUE:?Set LOG_ANALYTICS_SHARED_KEY_SECRET_NAME in the shell or via 'azd env set-secret'}"

: "${JIRA_BASE_URL_VALUE:?Set JIRA_BASE_URL in the shell or via 'azd env set'}"
: "${JIRA_USER_EMAIL_VALUE:?Set JIRA_USER_EMAIL in the shell or via 'azd env set'}"

REGISTRY_SERVER=${REGISTRY_SERVER:-$(printf '%s' "$WAIVER_IMAGE" | cut -d'/' -f1)}
USER_ASSIGNED_IDENTITY_RESOURCE_ID=${USER_ASSIGNED_IDENTITY_RESOURCE_ID:-"/subscriptions/66e84420-9ef4-4264-aedb-7beacbfe9e81/resourcegroups/RG-AIVM/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-aivmprodcliu3"}

registry_args=()
if [[ -n "${REGISTRY_USERNAME:-}" && -n "${REGISTRY_PASSWORD:-}" ]]; then
  registry_args+=(--registry-server "$REGISTRY_SERVER" --registry-username "$REGISTRY_USERNAME" --registry-password "$REGISTRY_PASSWORD")
fi

env_var_args=(
  KEYVAULT_URI="$KEYVAULT_URI"
  COSMOSDB_ENDPOINT="$COSMOSDB_ENDPOINT"
  COSMOSDB_DATABASE="$COSMOSDB_DATABASE"
  WAIVER_EXPIRY_LIMIT="$WAIVER_EXPIRY_LIMIT_VALUE"
  WAIVER_MONITOR_WINDOWS="$WAIVER_MONITOR_WINDOWS_VALUE"
  AZURE_MANAGED_IDENTITY_CLIENT_ID="$AZURE_MANAGED_IDENTITY_CLIENT_ID_VALUE"
  JIRA_BASE_URL="$JIRA_BASE_URL_VALUE"
  JIRA_USER_EMAIL="$JIRA_USER_EMAIL_VALUE"
  LOG_ANALYTICS_WORKSPACE_ID="$LOG_ANALYTICS_WORKSPACE_ID_VALUE"
  LOG_ANALYTICS_LOG_TYPE="$LOG_ANALYTICS_LOG_TYPE_VALUE"
)

[[ -n "$AZURE_OPENAI_ENDPOINT_VALUE" ]] && env_var_args+=(AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT_VALUE")
[[ -n "$AZURE_OPENAI_API_VERSION_VALUE" ]] && env_var_args+=(AZURE_OPENAI_API_VERSION="$AZURE_OPENAI_API_VERSION_VALUE")
[[ -n "$AZURE_OPENAI_DEPLOYMENT_NAME_VALUE" ]] && env_var_args+=(AZURE_OPENAI_DEPLOYMENT_NAME="$AZURE_OPENAI_DEPLOYMENT_NAME_VALUE")
[[ -n "$AZURE_CLIENT_ID_VALUE" ]] && env_var_args+=(AZURE_CLIENT_ID="$AZURE_CLIENT_ID_VALUE")
[[ -n "$AZURE_AI_SUBSCRIPTION_ID_VALUE" ]] && env_var_args+=(AZURE_AI_SUBSCRIPTION_ID="$AZURE_AI_SUBSCRIPTION_ID_VALUE")
[[ -n "$AZURE_AI_RESOURCE_GROUP_VALUE" ]] && env_var_args+=(AZURE_AI_RESOURCE_GROUP="$AZURE_AI_RESOURCE_GROUP_VALUE")
[[ -n "$AZURE_AI_PROJECT_NAME_VALUE" ]] && env_var_args+=(AZURE_AI_PROJECT_NAME="$AZURE_AI_PROJECT_NAME_VALUE")
[[ -n "$AZURE_AI_AGENT_ENDPOINT_VALUE" ]] && env_var_args+=(AZURE_AI_AGENT_ENDPOINT="$AZURE_AI_AGENT_ENDPOINT_VALUE")

filtered_env_vars=()
for entry in "${env_var_args[@]}"; do
  value=${entry#*=}
  if [[ -n "$value" ]]; then
    filtered_env_vars+=("$entry")
  fi
done

secret_specs=()
if [[ -n "$LOG_ANALYTICS_SHARED_KEY_SECRET_NAME_VALUE" ]]; then
  secret_specs+=(log-analytics-shared-key=kvref:${KEYVAULT_URI%/}/secrets/${LOG_ANALYTICS_SHARED_KEY_SECRET_NAME_VALUE})
  filtered_env_vars+=(LOG_ANALYTICS_SHARED_KEY="secretref:log-analytics-shared-key")
fi

create_args=(
  az containerapp job create
  --name "$WAIVER_JOB_NAME"
  --resource-group "$AZURE_RESOURCE_GROUP"
  --environment "$CONTAINERAPPS_ENV_NAME"
  --trigger-type Schedule
  --cron-expression "$CRON_EXPRESSION"
  --image "$WAIVER_IMAGE"
  --parallelism 1
  --replica-timeout 1800
  --replica-retry-limit 1
  --mi-user-assigned "$USER_ASSIGNED_IDENTITY_RESOURCE_ID"
  --command "python"
  --args "-m" "scripts.run_waiver_expiry" "--json"
  --env-vars "${filtered_env_vars[@]}"
)

if [[ ${#registry_args[@]} -gt 0 ]]; then
  create_args+=("${registry_args[@]}")
fi

if [[ ${#secret_specs[@]} -gt 0 ]]; then
  create_args+=(--secrets)
  create_args+=("${secret_specs[@]}")
fi

if ! az containerapp job show --name "$WAIVER_JOB_NAME" --resource-group "$AZURE_RESOURCE_GROUP" >/dev/null 2>&1; then
  "${create_args[@]}"
fi

update_args=(
  az containerapp job update
  --name "$WAIVER_JOB_NAME"
  --resource-group "$AZURE_RESOURCE_GROUP"
  --container-name "$WAIVER_JOB_NAME"
  --image "$WAIVER_IMAGE"
  --cron-expression "$CRON_EXPRESSION"
  --parallelism 1
  --replica-timeout 1800
  --replica-retry-limit 1
  --command "python"
  --args "-m" "scripts.run_waiver_expiry" "--json"
  --set-env-vars "${filtered_env_vars[@]}"
)

if [[ ${#secret_specs[@]} -gt 0 ]]; then
  update_args+=(--secrets)
  update_args+=("${secret_specs[@]}")
fi

"${update_args[@]}"

az containerapp job start --name "$WAIVER_JOB_NAME" --resource-group "$AZURE_RESOURCE_GROUP"
