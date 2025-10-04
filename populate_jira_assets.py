#!/usr/bin/env python3
import requests
import json
import subprocess
import base64

# Get Jira PAT from Key Vault
result = subprocess.run(
    ["az", "keyvault", "secret", "show", "--vault-name", "kv-aivm-core", "--name", "JIRA-PAT", "--query", "value", "-o", "tsv"],
    capture_output=True, text=True
)
JIRA_PAT = result.stdout.strip()

# Jira configuration
JIRA_BASE_URL = "https://cyberairnd.atlassian.net"
headers = {
    "Authorization": f"Basic {JIRA_PAT}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# First, let's search for existing workspace/schema
print("Searching for Assets workspace...")
workspace_url = f"{JIRA_BASE_URL}/rest/servicedeskapi/assets/workspace"
response = requests.get(workspace_url, headers=headers)
print(f"Workspace response: {response.status_code}")

if response.status_code == 200:
    workspaces = response.json().get("values", [])
    if workspaces:
        workspace_id = workspaces[0]["workspaceId"]
        print(f"Found workspace ID: {workspace_id}")
        
        # Get object schemas
        schema_url = f"{JIRA_BASE_URL}/rest/assets/1.0/objectschema/list"
        schema_response = requests.get(schema_url, headers=headers)
        print(f"Schema response: {schema_response.status_code}")
        if schema_response.status_code == 200:
            schemas = schema_response.json().get("objectschemas", [])
            if schemas:
                print(f"Available schemas: {[s['name'] for s in schemas]}")
            else:
                print("No schemas found")
        else:
            print(f"Schema error: {schema_response.text}")
    else:
        print("No workspaces found")
else:
    print(f"Error: {response.text}")

# Try alternative API endpoint for Jira Assets
print("\nTrying Insight API...")
insight_url = f"{JIRA_BASE_URL}/rest/insight/1.0/objectschema/list"
insight_response = requests.get(insight_url, headers=headers)
print(f"Insight response: {insight_response.status_code}")
if insight_response.status_code == 200:
    print("Insight API available")
else:
    print("Insight API not available")
