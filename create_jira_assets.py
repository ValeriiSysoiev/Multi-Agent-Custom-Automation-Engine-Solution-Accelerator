#!/usr/bin/env python3
import requests
import subprocess
import base64
import json
from datetime import datetime

# Get Jira PAT from Key Vault
result = subprocess.run(
    ["az", "keyvault", "secret", "show", "--vault-name", "kv-aivm-core", "--name", "JIRA-PAT", "--query", "value", "-o", "tsv"],
    capture_output=True, text=True
)
JIRA_TOKEN = result.stdout.strip()

JIRA_BASE_URL = "https://cyberairnd.atlassian.net"
EMAIL = "valeriisysoiev@cyberairnd.onmicrosoft.com"

# Create proper Basic auth with email:token
auth_string = f"{EMAIL}:{JIRA_TOKEN}"
auth_bytes = auth_string.encode('ascii')
auth_b64 = base64.b64encode(auth_bytes).decode('ascii')

headers = {
    "Authorization": f"Basic {auth_b64}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

print("Testing authentication...")
response = requests.get(f"{JIRA_BASE_URL}/rest/api/3/myself", headers=headers)
print(f"Auth response: {response.status_code}")

if response.status_code == 200:
    user = response.json()
    print(f"✅ Authenticated as: {user.get('displayName')}")
    
    # Create issues in a project to represent assets
    print("\nSearching for suitable project...")
    proj_resp = requests.get(f"{JIRA_BASE_URL}/rest/api/3/project", headers=headers)
    
    if proj_resp.status_code == 200:
        projects = proj_resp.json()
        print(f"Found {len(projects)} projects")
        
        if projects:
            # Use first available project
            project = projects[0]
            project_key = project['key']
            print(f"Using project: {project['name']} ({project_key})")
            
            # Get issue types for the project
            issue_types_resp = requests.get(
                f"{JIRA_BASE_URL}/rest/api/3/project/{project_key}/statuses", 
                headers=headers
            )
            
            # Define VM assets data
            vms = [
                {
                    "hostname": "vm-vuln-test-01",
                    "os": "Windows Server 2019",
                    "ip": "10.0.1.10",
                    "resource_id": "/subscriptions/66e84420-9ef4-4264-aedb-7beacbfe9e81/resourceGroups/RG-AIVM-VulnTest/providers/Microsoft.Compute/virtualMachines/vm-vuln-test-01",
                    "criticality": "High",
                    "environment": "Test",
                    "business_unit": "IT Security",
                    "data_classification": "Confidential",
                    "compliance": "PCI-DSS, SOC2",
                    "service_tier": "Tier 1",
                    "exposure": "Internal"
                },
                {
                    "hostname": "vm-vuln-linux-01", 
                    "os": "Ubuntu 22.04 LTS",
                    "ip": "10.0.1.11",
                    "resource_id": "/subscriptions/66e84420-9ef4-4264-aedb-7beacbfe9e81/resourceGroups/RG-AIVM-VulnTest/providers/Microsoft.Compute/virtualMachines/vm-vuln-linux-01",
                    "criticality": "Medium",
                    "environment": "Test",
                    "business_unit": "DevOps",
                    "data_classification": "Internal",
                    "compliance": "SOC2",
                    "service_tier": "Tier 2",
                    "exposure": "DMZ"
                }
            ]
            
            # Create issues for each VM
            for vm in vms:
                issue_data = {
                    "fields": {
                        "project": {"key": project_key},
                        "summary": f"[ASSET] {vm['hostname']} - {vm['os']}",
                        "description": {
                            "type": "doc",
                            "version": 1,
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": "Asset Information:"}
                                    ]
                                },
                                {
                                    "type": "bulletList",
                                    "content": [
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Hostname: {vm['hostname']}"}]}]},
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Operating System: {vm['os']}"}]}]},
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"IP Address: {vm['ip']}"}]}]},
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Azure Resource ID: {vm['resource_id']}"}]}]},
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Criticality: {vm['criticality']}"}]}]},
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Environment: {vm['environment']}"}]}]},
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Business Unit: {vm['business_unit']}"}]}]},
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Data Classification: {vm['data_classification']}"}]}]},
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Compliance: {vm['compliance']}"}]}]},
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Service Tier: {vm['service_tier']}"}]}]},
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Network Exposure: {vm['exposure']}"}]}]},
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Owner: {user.get('displayName', 'Unknown')}"}]}]}
                                    ]
                                }
                            ]
                        },
                        "issuetype": {"name": "Task"},
                        "labels": [
                            "CMDB",
                            "Asset",
                            "VM",
                            vm['environment'],
                            vm['criticality'],
                            vm['os'].replace(" ", "_")
                        ]
                    }
                }
                
                print(f"\nCreating asset record for {vm['hostname']}...")
                create_resp = requests.post(
                    f"{JIRA_BASE_URL}/rest/api/3/issue",
                    headers=headers,
                    json=issue_data
                )
                
                if create_resp.status_code == 201:
                    created = create_resp.json()
                    print(f"✅ Created: {created['key']} - {vm['hostname']}")
                    print(f"   URL: {JIRA_BASE_URL}/browse/{created['key']}")
                else:
                    print(f"❌ Failed to create asset for {vm['hostname']}: {create_resp.status_code}")
                    print(f"   Error: {create_resp.text[:200]}")
    else:
        print(f"Failed to get projects: {proj_resp.status_code}")
else:
    print(f"Authentication failed: {response.status_code}")
    print(f"Error: {response.text[:200]}")
