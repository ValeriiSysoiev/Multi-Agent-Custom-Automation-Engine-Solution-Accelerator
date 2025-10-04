# Microsoft Defender for Cloud (MDC) API Schema Documentation

## Overview
Microsoft Defender for Cloud provides security assessments and sub-assessments through Azure Resource Manager (ARM) APIs. This document provides comprehensive schema details and field mappings for integration.

## API Endpoints

### 1. Security Assessments
```
GET https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.Security/assessments?api-version={apiVersion}
```

### 2. Security Sub-Assessments
```
GET https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.Security/assessments/{assessmentName}/subAssessments?api-version={apiVersion}
```

## Supported API Versions
- `2019-01-01-preview` (Primary - most stable)
- `2022-01-01-preview` (Alternative)
- `2023-01-01-preview` (Latest - may have compatibility issues)

## Authentication
- Method: Azure AD OAuth 2.0
- Required: Bearer token from `az account get-access-token`
- Scope: `https://management.azure.com/.default`

## Response Schemas

### Assessment Response Schema
```json
{
  "value": [
    {
      "id": "string",              // Full ARM resource ID
      "name": "string",             // Assessment GUID
      "type": "Microsoft.Security/assessments",
      "properties": {
        "displayName": "string",    // Human-readable name
        "status": {
          "code": "string",         // "Healthy" | "Unhealthy" | "NotApplicable"
          "description": "string",  // Optional status description
          "cause": "string",        // Optional cause of status
          "severity": "string"      // "Low" | "Medium" | "High" | "Critical"
        },
        "resourceDetails": {
          "Id": "string",           // Resource ID being assessed
          "NativeResourceId": "string",
          "Source": "string"        // "Azure" | "AWS" | "GCP"
        },
        "additionalData": {
          "subAssessmentsLink": "string"  // URL to fetch sub-assessments
        },
        "metadata": {
          "category": "string[]",   // Security categories
          "threats": "string[]",    // Related threat types
          "userImpact": "string"    // Impact description
        }
      }
    }
  ],
  "nextLink": "string"              // Pagination link
}
```

### Sub-Assessment Response Schema
```json
{
  "value": [
    {
      "id": "string",               // Full ARM resource ID
      "name": "string",             // Sub-assessment identifier
      "type": "Microsoft.Security/assessments/subAssessments",
      "properties": {
        "id": "string",             // Vulnerability/finding ID (often CVE)
        "displayName": "string",    // Human-readable description
        "status": {
          "code": "string",         // "Healthy" | "Unhealthy" | "NotApplicable"
          "severity": "string"      // "Low" | "Medium" | "High" | "Critical"
        },
        "resourceDetails": {
          "id": "string",           // Full resource ID
          "source": "string"        // "Azure" | "AWS" | "GCP"
        },
        "remediation": {
          "description": "string",  // Remediation instructions
          "scripts": [              // Remediation scripts
            {
              "scriptType": "string",  // "PowerShell" | "Bash" | "Python"
              "script": "string"       // Script content
            }
          ],
          "automated": "boolean"    // Can be auto-remediated
        },
        "timeGenerated": "string",  // ISO 8601 datetime
        "additionalData": {
          "cve": ["string"],        // CVE identifiers
          "cvss": "number",         // CVSS base score (0.0-10.0)
          "cvss3": {
            "baseScore": "number",
            "vector": "string"      // CVSS v3 vector string
          },
          "severity": "string",     // Vendor severity rating
          "patchable": "boolean",   // Patch available
          "vendorReference": "string",  // Vendor advisory ID
          "publishedDate": "string",    // CVE publish date
          "exploitAvailable": "boolean",
          "exploitTypes": ["string"],   // Known exploit types
          "affectedSoftware": [
            {
              "softwareName": "string",
              "version": "string",
              "vendor": "string"
            }
          ],
          "port": "number",         // Network port if applicable
          "protocol": "string",     // Protocol (tcp/udp)
          "softwareName": "string", // Affected software
          "version": "string",      // Affected version
          "evidence": "string",     // Detection evidence
          "detectionMethod": "string",  // How it was detected
          "firstDetected": "string",    // First seen date
          "lastSeen": "string"          // Last seen date
        },
        "category": "string",       // Vulnerability category
        "impact": "string",         // Impact description
        "description": "string"     // Detailed description
      }
    }
  ],
  "nextLink": "string"              // Pagination link
}
```

## Field Mappings to Canonical Schema

### Primary Mappings
| MDC Field | Canonical Field | Type | Description |
|-----------|----------------|------|-------------|
| `properties.additionalData.cve[0]` or `properties.additionalData.vendorReference` | `vuln_key` | string | Primary vulnerability identifier |
| `properties.additionalData.cve` | `cve` | array | All CVE identifiers |
| `properties.additionalData.severity` | `severity` | string | Severity level |
| `properties.additionalData.cvss` | `cvss.baseScore` | number | CVSS base score |
| `properties.resourceDetails.id` | `asset_identifiers.resourceId` | string | Azure resource ID |
| `properties.timeGenerated` | `first_seen`, `last_seen` | datetime | Detection timestamp |
| `properties.status.code` | `status` | string | "Unhealthy"→"open", else→"fixed" |
| `properties.additionalData.patchable` | `patch_available` | boolean | Patch availability |
| `properties.remediation.description` | `solution` | string | Remediation steps |
| `properties.additionalData.evidence` | `evidence` | string | Detection evidence |

### Location Data Mappings
| MDC Field | Canonical Field | Type | Description |
|-----------|----------------|------|-------------|
| `properties.additionalData.port` | `location.port` | number | Network port |
| `properties.additionalData.protocol` | `location.protocol` | string | Network protocol |
| `properties.additionalData.softwareName` | `location.softwareName` | string | Affected software |
| `properties.additionalData.version` | `location.version` | string | Software version |

### Status Code Mappings
| MDC Status | Canonical Status | Description |
|------------|-----------------|-------------|
| `Unhealthy` | `open` | Active vulnerability |
| `Healthy` | `fixed` | Resolved/mitigated |
| `NotApplicable` | `not_applicable` | Not relevant to resource |

### Severity Mappings
| MDC Severity | Canonical Severity | CVSS Range |
|--------------|-------------------|------------|
| `Critical` | `critical` | 9.0-10.0 |
| `High` | `high` | 7.0-8.9 |
| `Medium` | `medium` | 4.0-6.9 |
| `Low` | `low` | 0.1-3.9 |
| `Informational` | `info` | 0.0 |

## Sample API Requests

### 1. List All Assessments
```bash
curl -X GET \
  "https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.Security/assessments?api-version=2019-01-01-preview" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json"
```

### 2. Get Sub-Assessments for Specific Assessment
```bash
curl -X GET \
  "https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.Security/assessments/{assessmentName}/subAssessments?api-version=2019-01-01-preview" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json"
```

### 3. Using Azure CLI
```bash
# Get assessments
az rest --method GET \
  --url "https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.Security/assessments?api-version=2019-01-01-preview"

# Get sub-assessments
az rest --method GET \
  --url "https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.Security/assessments/{assessmentName}/subAssessments?api-version=2019-01-01-preview"
```

## Pagination
- Responses may include `nextLink` for pagination
- Follow `nextLink` URLs to retrieve all results
- Default page size: 100 items
- Maximum page size: 1000 items

## Rate Limits
- Default: 1200 requests per minute
- Burst: 2000 requests
- Headers: `x-ms-ratelimit-remaining-subscription-reads`

## Error Responses
```json
{
  "error": {
    "code": "string",           // Error code
    "message": "string",        // Error message
    "details": [                // Additional details
      {
        "code": "string",
        "message": "string"
      }
    ]
  }
}
```

### Common Error Codes
| Code | Description | Resolution |
|------|-------------|------------|
| `InvalidApiVersionParameter` | Unsupported API version | Use supported versions |
| `ResourceNotFound` | Assessment not found | Verify assessment name |
| `AuthorizationFailed` | Insufficient permissions | Check RBAC permissions |
| `SubscriptionNotRegistered` | Provider not registered | Register Microsoft.Security |

## Required Azure RBAC Permissions
- Minimum: `Security Reader` role
- Recommended: `Security Admin` for full access
- Scope: Subscription or Management Group level

## Important Notes for Codex

1. **API Version Probing**: Always probe API versions in order (2019-01-01-preview first) as availability varies by region and subscription.

2. **Empty Sub-Assessments**: Many assessments have no sub-assessments. This is normal for policy-based assessments.

3. **Resource Types**: Sub-assessments are typically available for:
   - Virtual Machines (vulnerability assessments)
   - Container registries (image scanning)
   - SQL databases (vulnerability assessments)
   - Storage accounts (security misconfigurations)

4. **Field Availability**: Not all fields are present in all responses:
   - CVE data only for vulnerability findings
   - Port/protocol only for network findings
   - Patch information varies by finding type

5. **Timestamp Handling**:
   - `timeGenerated` is when finding was created
   - Use for both `first_seen` and `last_seen` unless `additionalData` has specific dates

6. **Status Determination**:
   - Primary indicator: `properties.status.code`
   - "Unhealthy" = active issue requiring action
   - "Healthy" = resolved or mitigated
   - "NotApplicable" = not relevant to resource

7. **Severity Priority**:
   1. Check `properties.additionalData.severity` first
   2. Fall back to `properties.status.severity`
   3. Derive from CVSS score if available

8. **Resource Identification**:
   - Primary: `properties.resourceDetails.id`
   - Format: `/subscriptions/{subId}/resourceGroups/{rg}/providers/{provider}/{type}/{name}`
   - Parse for granular identification

9. **Batch Processing**:
   - Process assessments in parallel
   - Limit concurrent sub-assessment requests to 10
   - Implement exponential backoff for rate limiting

10. **Caching Strategy**:
    - Cache assessment list for 1 hour
    - Cache sub-assessments for 15 minutes
    - Invalidate on resource changes