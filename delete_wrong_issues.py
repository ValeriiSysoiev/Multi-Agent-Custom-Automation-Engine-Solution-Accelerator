#!/usr/bin/env python3
import requests
import subprocess
import base64

# Get auth
result = subprocess.run(
    ["az", "keyvault", "secret", "show", "--vault-name", "kv-aivm-core", "--name", "JIRA-PAT", "--query", "value", "-o", "tsv"],
    capture_output=True, text=True
)
JIRA_TOKEN = result.stdout.strip()

JIRA_BASE_URL = "https://cyberairnd.atlassian.net"
EMAIL = "valeriisysoiev@cyberairnd.onmicrosoft.com"

auth_string = f"{EMAIL}:{JIRA_TOKEN}"
auth_b64 = base64.b64encode(auth_string.encode()).decode()
headers = {
    "Authorization": f"Basic {auth_b64}",
    "Accept": "application/json"
}

print("Cleaning up incorrectly created issues...")

# Delete the wrong issues
issues_to_delete = ["CYB-5", "CYB-6"]

for issue_key in issues_to_delete:
    delete_url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    response = requests.delete(delete_url, headers=headers)
    
    if response.status_code == 204:
        print(f"✅ Deleted {issue_key}")
    else:
        print(f"❌ Could not delete {issue_key}: {response.status_code}")
        
print("\nCleanup complete!")
