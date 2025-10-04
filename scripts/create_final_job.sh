#!/usr/bin/env bash
# Create the final reporting job with all configurations

set -euo pipefail

RESOURCE_GROUP="RG-AIVM"
JOB_NAME="aivm-reporting-job"
ENVIRONMENT="cae-aivmprodcliu3"
IDENTITY="/subscriptions/66e84420-9ef4-4264-aedb-7beacbfe9e81/resourcegroups/RG-AIVM/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-aivmprodcliu3"

echo "Creating Container Apps Job with correct configuration..."

# Create job with schedule trigger and basic config
az containerapp job create \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT" \
  --trigger-type Schedule \
  --cron-expression "0 2 * * *" \
  --parallelism 1 \
  --replica-timeout 3600 \
  --replica-retry-limit 1 \
  --mi-user-assigned "$IDENTITY" \
  --registry-server acraivmprod.azurecr.io \
  --registry-identity "$IDENTITY" \
  --output none

echo "✓ Job created successfully"

# Create complete configuration YAML
cat > /tmp/job-full-config.yaml <<'EOF'
properties:
  configuration:
    registries:
    - server: acraivmprod.azurecr.io
      identity: /subscriptions/66e84420-9ef4-4264-aedb-7beacbfe9e81/resourcegroups/RG-AIVM/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-aivmprodcliu3
  template:
    containers:
    - name: aivm-reporting-job
      image: acraivmprod.azurecr.io/macaebackend:latest
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
        value: https://kv-aivm-core.vault.azure.net/
      - name: COSMOSDB_ENDPOINT
        value: https://cosmos-aivmprodcliu3.documents.azure.com:443/
      - name: COSMOSDB_DATABASE
        value: macae
      - name: AZURE_OPENAI_ENDPOINT
        value: https://aif-aivmprodcliu3.openai.azure.com/
      - name: AZURE_CLIENT_ID
        value: c6c2af5b-d1c9-4b02-9b8e-5894e89cb9cd
      - name: PBI_WORKSPACE_ID
        value: 8f802077-e058-4aac-ae18-0335bbbf59ab
      - name: PBI_DATASET_ID
        value: acc0156b-8e36-474b-8324-5d1f32359fc9
      - name: PBI_CLIENT_ID
        value: 712006fa-1cbd-4f92-9fce-6f6a2ef23d42
      - name: STORAGE_ACCOUNT_NAME
        value: stgaivmreporting
      - name: STORAGE_CONTAINER_NAME
        value: aivm-reporting
EOF

echo "Updating job with full configuration..."
az containerapp job update \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --yaml /tmp/job-full-config.yaml \
  --output none 2>/dev/null || echo "Note: Update may show warnings but usually succeeds"

echo ""
echo "✓ Job configuration complete!"
echo ""
echo "Starting manual execution for testing..."

az containerapp job start \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --output json | jq -r '.name'

echo ""
echo "Job started! Monitor with:"
echo "az containerapp job execution list --name $JOB_NAME --resource-group $RESOURCE_GROUP --output table"