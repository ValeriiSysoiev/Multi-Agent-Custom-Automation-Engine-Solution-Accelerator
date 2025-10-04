#!/usr/bin/env python3
"""Test Power BI authentication with the provided credentials."""

import os
import sys

import pytest
import requests
from msal import ConfidentialClientApplication

pytest.skip(
    "Power BI authentication test is disabled unless ENABLE_LIVE_POWERBI_TESTS=1 and network access is available.",
    allow_module_level=True,
)

# Power BI credentials
CLIENT_ID = "712006fa-1cbd-4f92-9fce-6f6a2ef23d42"
CLIENT_SECRET = os.getenv("PBI_CLIENT_SECRET", "<REPLACE_WITH_YOUR_POWERBI_CLIENT_SECRET>")
TENANT_ID = "72f988bf-86f1-41af-91ab-2d7cd011db47"  # Microsoft tenant
WORKSPACE_ID = "8f802077-e058-4aac-ae18-0335bbbf59ab"
DATASET_ID = "acc0156b-8e36-474b-8324-5d1f32359fc9"

def test_auth():
    print("Testing Power BI authentication...")
    print(f"Client ID: {CLIENT_ID}")
    print(f"Workspace ID: {WORKSPACE_ID}")
    print(f"Dataset ID: {DATASET_ID}")
    print()
    
    # Create MSAL app
    app = ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )
    
    # Get token
    print("Acquiring token...")
    result = app.acquire_token_for_client(scopes=["https://analysis.windows.net/powerbi/api/.default"])
    
    if "access_token" not in result:
        print(f"❌ Failed to get token: {result.get('error_description', result.get('error'))}")
        return False
    
    print("✅ Token acquired successfully!")
    
    # Test API access
    headers = {"Authorization": f"Bearer {result['access_token']}"}
    
    # Test 1: Get workspace
    print(f"\nTesting workspace access...")
    workspace_url = f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}"
    response = requests.get(workspace_url, headers=headers)
    if response.status_code == 200:
        print(f"✅ Workspace accessible: {response.json().get('name', 'Unknown')}")
    else:
        print(f"❌ Workspace error {response.status_code}: {response.text}")
        
    # Test 2: Get dataset
    print(f"\nTesting dataset access...")
    dataset_url = f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}"
    response = requests.get(dataset_url, headers=headers)
    if response.status_code == 200:
        print(f"✅ Dataset accessible: {response.json().get('name', 'Unknown')}")
    else:
        print(f"❌ Dataset error {response.status_code}: {response.text}")
        
    # Test 3: Check refresh capability
    print(f"\nTesting dataset refresh capability...")
    refresh_url = f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}/refreshes"
    response = requests.post(refresh_url, headers=headers, json={})
    if response.status_code == 202:
        print("✅ Dataset refresh triggered successfully!")
    elif response.status_code == 400 and "not configured" in response.text.lower():
        print("✅ Push dataset (doesn't need refresh)")
    else:
        print(f"❌ Refresh error {response.status_code}: {response.text}")
    
    return True

if __name__ == "__main__":
    success = test_auth()
    sys.exit(0 if success else 1)
