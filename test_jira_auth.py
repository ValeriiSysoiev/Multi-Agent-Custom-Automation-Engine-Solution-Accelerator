#!/usr/bin/env python3
import requests
import subprocess
import base64

# Get Jira PAT from Key Vault
result = subprocess.run(
    ["az", "keyvault", "secret", "show", "--vault-name", "kv-aivm-core", "--name", "JIRA-PAT", "--query", "value", "-o", "tsv"],
    capture_output=True, text=True
)
JIRA_PAT = result.stdout.strip()

JIRA_BASE_URL = "https://cyberairnd.atlassian.net"

# Check if PAT is already base64 encoded or needs email:token format
print(f"PAT length: {len(JIRA_PAT)}")
print(f"PAT starts with: {JIRA_PAT[:10]}...")

# Try different authentication methods
print("\n1. Testing with PAT as Bearer token...")
headers = {
    "Authorization": f"Bearer {JIRA_PAT}",
    "Accept": "application/json"
}
response = requests.get(f"{JIRA_BASE_URL}/rest/api/3/myself", headers=headers)
print(f"Bearer auth response: {response.status_code}")

print("\n2. Testing with PAT in Basic auth directly...")
headers = {
    "Authorization": f"Basic {JIRA_PAT}",
    "Accept": "application/json"
}
response = requests.get(f"{JIRA_BASE_URL}/rest/api/3/myself", headers=headers)
print(f"Basic auth (direct) response: {response.status_code}")

if response.status_code == 200:
    user_info = response.json()
    print(f"Authenticated as: {user_info.get('displayName', 'Unknown')}")
    print(f"Email: {user_info.get('emailAddress', 'Unknown')}")
    
    # Now test access to different APIs
    print("\n3. Testing Project API access...")
    proj_response = requests.get(f"{JIRA_BASE_URL}/rest/api/3/project", headers=headers)
    print(f"Projects response: {proj_response.status_code}")
    if proj_response.status_code == 200:
        projects = proj_response.json()
        print(f"Found {len(projects)} projects")
        if projects:
            print(f"First project: {projects[0].get('name', 'Unknown')}")
else:
    print(f"Authentication failed: {response.text[:200]}")

# Test if we need email:token format
print("\n4. Checking if we need email:token format...")
# First get email from environment or guess
email = "valeriisysoiev@cyberairnd.onmicrosoft.com"  # Based on the resource group info
print(f"Trying with email: {email}")
