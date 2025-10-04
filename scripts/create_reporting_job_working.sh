#!/usr/bin/env bash
# Create reporting export Container Apps job with our new ACR

set -euo pipefail

# Configuration
AZURE_RESOURCE_GROUP="RG-AIVM"
REPORTING_JOB_NAME="aivm-reporting-job"
REPORTING_IMAGE="acraivmprod.azurecr.io/macaebackend:latest"
CRON_EXPRESSION="0 2 * * *"  # Daily at 2 AM
ENVIRONMENT_NAME="cae-aivmprodcliu3"
IDENTITY_ID="/subscriptions/66e84420-9ef4-4264-aedb-7beacbfe9e81/resourcegroups/RG-AIVM/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-aivmprodcliu3"

# Environment values
KEYVAULT_URI="https://kv-aivm-core.vault.azure.net/"
COSMOSDB_ENDPOINT="https://cosmos-aivmprodcliu3.documents.azure.com:443/"
COSMOSDB_DATABASE="macae"
AZURE_OPENAI_ENDPOINT="https://aif-aivmprodcliu3.openai.azure.com/"
AZURE_CLIENT_ID="c6c2af5b-d1c9-4b02-9b8e-5894e89cb9cd"
PBI_WORKSPACE_ID="8f802077-e058-4aac-ae18-0335bbbf59ab"
PBI_DATASET_ID="acc0156b-8e36-474b-8324-5d1f32359fc9"

echo "Creating Container Apps Job: $REPORTING_JOB_NAME"
echo "Using image: $REPORTING_IMAGE"
echo "Environment: $ENVIRONMENT_NAME"
echo "Schedule: $CRON_EXPRESSION (Daily at 2 AM UTC)"

# Create the job - first with basic config
echo "Step 1: Creating job with basic configuration..."
az containerapp job create \
  --name "$REPORTING_JOB_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --environment "$ENVIRONMENT_NAME" \
  --trigger-type Schedule \
  --cron-expression "$CRON_EXPRESSION" \
  --parallelism 1 \
  --replica-timeout 3600 \
  --replica-retry-limit 1 \
  --mi-user-assigned "$IDENTITY_ID" \
  --registry-server acraivmprod.azurecr.io \
  --registry-identity "$IDENTITY_ID" \
  --output none

echo "✓ Job created"

# Now update with the full configuration using YAML
echo "Step 2: Updating job with complete configuration..."
cat > /tmp/job-config.yaml <<EOF
properties:
  configuration:
    registries:
    - server: acraivmprod.azurecr.io
      identity: $IDENTITY_ID
  template:
    containers:
    - name: $REPORTING_JOB_NAME
      image: $REPORTING_IMAGE
      command:
      - /bin/sh
      args:
      - -c
      - python -m scripts.run_reporting_export --refresh-powerbi --json
      resources:
        cpu: 0.5
        memory: 1Gi
      env:
      - name: KEYVAULT_URI
        value: $KEYVAULT_URI
      - name: COSMOSDB_ENDPOINT
        value: $COSMOSDB_ENDPOINT
      - name: COSMOSDB_DATABASE
        value: $COSMOSDB_DATABASE
      - name: AZURE_OPENAI_ENDPOINT
        value: $AZURE_OPENAI_ENDPOINT
      - name: AZURE_CLIENT_ID
        value: $AZURE_CLIENT_ID
      - name: PBI_WORKSPACE_ID
        value: $PBI_WORKSPACE_ID
      - name: PBI_DATASET_ID
        value: $PBI_DATASET_ID
EOF

az containerapp job update \
  --name "$REPORTING_JOB_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --yaml /tmp/job-config.yaml \
  --output none

echo "✓ Job updated with full configuration"

echo ""
echo "Job created successfully!"
echo "Starting the job for immediate execution..."

# Start the job immediately
az containerapp job start \
  --name "$REPORTING_JOB_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --output json | jq -r '.name'

echo ""
echo "Job started. Monitor execution with:"
echo "az containerapp job execution list --name $REPORTING_JOB_NAME --resource-group $AZURE_RESOURCE_GROUP --output table"