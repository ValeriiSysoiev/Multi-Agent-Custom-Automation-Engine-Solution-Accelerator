#!/bin/bash

# Variables for test environment
TEST_RG="RG-AIVM-VulnTest"
LOCATION="canadacentral"
VM_NAME="vm-vuln-test-01"
VM_SIZE="Standard_B2s"
IMAGE="Win2019Datacenter"
ADMIN_USER="testadmin"
ADMIN_PASS="VulnTest@2024!Sec"

echo "============================================"
echo "Creating Test Environment for Vulnerability Scanning"
echo "============================================"

# Create dedicated resource group for vulnerability testing
echo "1. Creating resource group: $TEST_RG"
az group create \
  --name $TEST_RG \
  --location $LOCATION \
  --tags Environment=Test Purpose=VulnerabilityScanning Solution=AIVM

echo ""
echo "2. Creating Windows VM with potential vulnerabilities..."
# Create Windows Server 2019 (older version = more vulnerabilities)
az vm create \
  --resource-group $TEST_RG \
  --name $VM_NAME \
  --location $LOCATION \
  --image $IMAGE \
  --size $VM_SIZE \
  --admin-username $ADMIN_USER \
  --admin-password "$ADMIN_PASS" \
  --public-ip-sku Standard \
  --nsg-rule RDP \
  --tags Environment=Test Purpose=DefenderTarget \
  --output table

echo ""
echo "3. Creating Ubuntu Linux VM for additional scanning..."
LINUX_VM_NAME="vm-vuln-linux-01"
az vm create \
  --resource-group $TEST_RG \
  --name $LINUX_VM_NAME \
  --location $LOCATION \
  --image "UbuntuLTS" \
  --size $VM_SIZE \
  --admin-username $ADMIN_USER \
  --admin-password "$ADMIN_PASS" \
  --public-ip-sku Standard \
  --nsg-rule SSH \
  --tags Environment=Test Purpose=DefenderTarget \
  --output table

echo ""
echo "============================================"
echo "Test resources created successfully!"
echo "Resource Group: $TEST_RG"
echo "Windows VM: $VM_NAME"
echo "Linux VM: $LINUX_VM_NAME"
echo "============================================"
echo ""
echo "These VMs will have vulnerabilities for testing:"
echo "- Unpatched OS (Windows Server 2019, Ubuntu)"
echo "- Open ports (RDP, SSH)"
echo "- Default configurations"
echo "- No additional hardening applied"
echo ""
echo "Next steps:"
echo "1. Enable Microsoft Defender for Cloud"
echo "2. Wait for vulnerability assessment"
echo "3. Use findings for AIVM testing"
