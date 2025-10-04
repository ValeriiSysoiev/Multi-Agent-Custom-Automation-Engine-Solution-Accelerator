#!/usr/bin/env python3
import requests
import subprocess
import base64
import json

# Get Jira PAT
result = subprocess.run(
    ["az", "keyvault", "secret", "show", "--vault-name", "kv-aivm-core", "--name", "JIRA-PAT", "--query", "value", "-o", "tsv"],
    capture_output=True, text=True
)
JIRA_TOKEN = result.stdout.strip()

JIRA_BASE_URL = "https://cyberairnd.atlassian.net"
EMAIL = "valeriisysoiev@cyberairnd.onmicrosoft.com"

# Create auth
auth_string = f"{EMAIL}:{JIRA_TOKEN}"
auth_b64 = base64.b64encode(auth_string.encode()).decode()
headers = {
    "Authorization": f"Basic {auth_b64}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

print("=" * 60)
print("CONNECTING TO JIRA ASSETS (CMDB)")
print("=" * 60)

# First, let's find the workspace ID
workspace_url = f"{JIRA_BASE_URL}/gateway/api/jsm/assets/workspace/survey"
workspace_resp = requests.get(workspace_url, headers=headers)
print(f"\n1. Checking Assets workspace...")
print(f"   Response: {workspace_resp.status_code}")

if workspace_resp.status_code == 200:
    workspace_data = workspace_resp.json()
    print(f"   Workspace available: {workspace_data}")

# Try the Insight API (older name for Assets)
print("\n2. Trying Insight/Assets REST API...")
insight_schema_url = f"{JIRA_BASE_URL}/rest/insight/1.0/objectschema/list"
schema_resp = requests.get(insight_schema_url, headers=headers)
print(f"   Schema list response: {schema_resp.status_code}")

if schema_resp.status_code == 200:
    schemas = schema_resp.json()
    print(f"   Found {len(schemas)} schemas")
    
    if schemas:
        # Use the first schema
        schema = schemas[0]
        schema_id = schema['id']
        schema_name = schema['name']
        print(f"   Using schema: {schema_name} (ID: {schema_id})")
        
        # Get object types in this schema
        types_url = f"{JIRA_BASE_URL}/rest/insight/1.0/objecttype/flat/{schema_id}"
        types_resp = requests.get(types_url, headers=headers)
        
        if types_resp.status_code == 200:
            object_types = types_resp.json()
            print(f"\n3. Available object types:")
            for ot in object_types:
                print(f"   - {ot['name']} (ID: {ot['id']})")
                
            # Look for Server/VM type
            server_type = next((ot for ot in object_types if 'server' in ot['name'].lower() or 'vm' in ot['name'].lower()), None)
            
            if server_type:
                print(f"\n4. Found Server/VM object type: {server_type['name']}")
                type_id = server_type['id']
                
                # Get attributes for this object type
                attrs_url = f"{JIRA_BASE_URL}/rest/insight/1.0/objecttype/{type_id}/attributes"
                attrs_resp = requests.get(attrs_url, headers=headers)
                
                if attrs_resp.status_code == 200:
                    attributes = attrs_resp.json()
                    print(f"\n5. Available attributes:")
                    for attr in attributes[:10]:  # Show first 10
                        print(f"   - {attr['name']} (ID: {attr['id']}, Type: {attr.get('type', 'Unknown')})")
            else:
                print("\n4. No Server/VM object type found. Available types:")
                for ot in object_types[:10]:
                    print(f"   - {ot['name']} (ID: {ot['id']})")
        else:
            print(f"   Failed to get object types: {types_resp.status_code}")
else:
    # Try newer Assets API
    print("\n3. Trying newer Assets API...")
    assets_url = f"{JIRA_BASE_URL}/rest/assets/1.0/workspace"
    assets_resp = requests.get(assets_url, headers=headers)
    print(f"   Response: {assets_resp.status_code}")
    
    if assets_resp.status_code == 200:
        print("   Assets API is available")
        workspaces = assets_resp.json()
        print(f"   Workspaces: {json.dumps(workspaces, indent=2)[:500]}")

# Try to access the Assets gateway API
print("\n4. Checking Assets Gateway API...")
gateway_url = f"{JIRA_BASE_URL}/gateway/api/jsm/assets/workspace"
gateway_resp = requests.get(gateway_url, headers=headers)
print(f"   Response: {gateway_resp.status_code}")

if gateway_resp.status_code == 200:
    gateway_data = gateway_resp.json()
    print(f"   Gateway data: {json.dumps(gateway_data, indent=2)[:500]}")
    
    if 'workspaceId' in gateway_data:
        workspace_id = gateway_data['workspaceId']
        print(f"\n✅ Found workspace ID: {workspace_id}")
        
        # Try to get schemas in this workspace
        schemas_url = f"{JIRA_BASE_URL}/gateway/api/jsm/assets/workspace/{workspace_id}/v1/objectschema"
        schemas_resp = requests.get(schemas_url, headers=headers)
        print(f"\n5. Getting schemas in workspace...")
        print(f"   Response: {schemas_resp.status_code}")
        
        if schemas_resp.status_code == 200:
            schemas_data = schemas_resp.json()
            print(f"   Schemas: {json.dumps(schemas_data, indent=2)[:500]}")

print("\n" + "=" * 60)
print("NEXT STEPS:")
print("=" * 60)
print("Please check https://cyberairnd.atlassian.net/jira/assets")
print("and let me know:")
print("1. What object schemas you have")
print("2. What object types exist (e.g., Server, VM, Application)")
print("3. What attributes are configured")
print("\nThen I can create the proper asset objects!")
