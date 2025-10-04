#!/bin/bash
echo "Setting up complete environment for local testing..."

# Core Azure settings
export KEYVAULT_URI="https://kv-aivm-core.vault.azure.net/"
export COSMOSDB_ENDPOINT="https://cosmos-aivmprodcliu3.documents.azure.com:443/"
export COSMOSDB_DATABASE="macae"
export AZURE_CLIENT_ID="c6c2af5b-d1c9-4b02-9b8e-5894e89cb9cd"

# Storage settings
export STORAGE_ACCOUNT_NAME="stgaivmreporting"
export STORAGE_CONTAINER_NAME="aivm-reporting"

# OpenAI settings (required by app_config)
export AZURE_OPENAI_ENDPOINT="https://aif-aivmprodcliu3.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4"
export AZURE_OPENAI_API_VERSION="2024-02-15-preview"

# Azure AI Project settings (required by app_config)
export AZURE_AI_PROJECT_CONNECTION_STRING="https://aif-aivmprodcliu3.openai.azure.com/"
export AZURE_AI_PROJECT_NAME="aivm-project"
export AZURE_AI_SUBSCRIPTION_ID="66e84420-9ef4-4264-aedb-7beacbfe9e81"
export AZURE_AI_RESOURCE_GROUP="RG-AIVM"

# Power BI settings
export PBI_WORKSPACE_ID="8f802077-e058-4aac-ae18-0335bbbf59ab"
export PBI_DATASET_ID="acc0156b-8e36-474b-8324-5d1f32359fc9"
export PBI_CLIENT_ID="712006fa-1cbd-4f92-9fce-6f6a2ef23d42"
export PBI_CLIENT_SECRET="<REPLACE_WITH_YOUR_POWERBI_CLIENT_SECRET>"

echo "Environment variables set."
echo "Activating virtual environment..."
source .venv/bin/activate

echo "Running reporting export with verbose output..."
echo "==============================================="
python -m scripts.run_reporting_export --verbose --json 2>&1
EXIT_CODE=$?
echo "==============================================="
echo "Script exited with code: $EXIT_CODE"
