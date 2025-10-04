#!/bin/bash
# Script to assign Key Vault Secrets User role to Container App managed identity
# Usage: ./assign_keyvault_role.sh <CONTAINER_APP_NAME>

CONTAINER_APP_NAME=$1
RESOURCE_GROUP="RG-AIVM"
KEYVAULT_NAME="kv-aivm-core"

if [ -z "$CONTAINER_APP_NAME" ]; then
    echo "Usage: $0 <CONTAINER_APP_NAME>"
    echo "This script will assign the Key Vault Secrets User role to the Container App's managed identity"
    exit 1
fi

echo "Getting managed identity for Container App: $CONTAINER_APP_NAME"
IDENTITY_ID=$(az containerapp show --name "$CONTAINER_APP_NAME" --resource-group "$RESOURCE_GROUP" --query "identity.principalId" -o tsv 2>/dev/null)

if [ -z "$IDENTITY_ID" ]; then
    echo "No managed identity found for Container App $CONTAINER_APP_NAME"
    echo "Make sure the Container App exists and has a system-assigned managed identity enabled"
    exit 1
fi

echo "Found managed identity: $IDENTITY_ID"

# Get Key Vault resource ID
KEYVAULT_ID=$(az keyvault show --name "$KEYVAULT_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)

echo "Assigning Key Vault Secrets User role..."
az role assignment create \
    --role "Key Vault Secrets User" \
    --assignee "$IDENTITY_ID" \
    --scope "$KEYVAULT_ID" \
    --output json

if [ $? -eq 0 ]; then
    echo "Successfully assigned Key Vault Secrets User role to $CONTAINER_APP_NAME's managed identity"
else
    echo "Failed to assign role. Please check the error message above."
    exit 1
fi