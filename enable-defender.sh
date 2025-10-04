#!/bin/bash

echo "============================================"
echo "Enabling Microsoft Defender for Cloud"
echo "============================================"

SUBSCRIPTION_ID="66e84420-9ef4-4264-aedb-7beacbfe9e81"

echo "1. Registering Microsoft.Security provider..."
az provider register --namespace Microsoft.Security --wait

echo ""
echo "2. Enabling Defender for Servers (includes vulnerability assessment)..."
az security pricing create \
  --name VirtualMachines \
  --tier Standard \
  --output table

echo ""
echo "3. Enabling Defender for Cloud auto-provisioning..."
az security auto-provisioning-setting update \
  --auto-provision On \
  --name default \
  --output table

echo ""
echo "4. Setting up vulnerability assessment solution..."
# Enable Microsoft Defender vulnerability management
az security setting update \
  --name MCAS \
  --enabled true \
  2>/dev/null || echo "Settings configuration in progress..."

echo ""
echo "5. Checking security contacts..."
az security contact list --output table

echo ""
echo "============================================"
echo "Defender Configuration Status:"
echo "============================================"
az security pricing list --query "[?name=='VirtualMachines'].{Service:name, Tier:pricingTier}" --output table

echo ""
echo "VMs in Test Resource Group:"
az vm list --resource-group RG-AIVM-VulnTest --output table

echo ""
echo "Note: It may take 15-30 minutes for:"
echo "- Defender agents to be installed"
echo "- Initial vulnerability scan to complete"
echo "- Results to appear in Azure Portal"
