# Qualys VMDR API Schema Documentation

## Overview
Qualys Vulnerability Management, Detection & Response (VMDR) provides comprehensive vulnerability detection and management through REST APIs. This document provides complete schema details and integration specifications.

## API Endpoints

### Base URLs
- **US Platform 1**: `https://qualysapi.qualys.com`
- **US Platform 2**: `https://qualysapi.qualys.eu`
- **US Platform 3**: `https://qualysapi.qg3.apps.qualys.com`
- **EU Platform 1**: `https://qualysapi.qualys.eu`
- **EU Platform 2**: `https://qualysapi.qg2.apps.qualys.eu`

### Core Endpoints

#### 1. Host VM Detections
```
GET /api/2.0/fo/asset/host/vm/detection/
Parameters:
  action=list
  vm_scan_since=YYYY-MM-DD
  truncation_limit=N (max 10000)
  show_results=0|1
  show_reopened_info=0|1
  status=New,Active,Fixed,Re-Opened
```

#### 2. Knowledge Base
```
GET /api/2.0/fo/knowledge_base/vuln/
Parameters:
  action=list
  details=Basic|All|None
  ids=QID1,QID2,...
  id_min=N
  id_max=N
  last_modified_after=YYYY-MM-DD
  last_modified_before=YYYY-MM-DD
  published_after=YYYY-MM-DD
  published_before=YYYY-MM-DD
  show_patchable=0|1
  show_pci_flag=0|1
  show_disabled_flag=0|1
  show_qid_change_log=0|1
```

#### 3. Host List
```
GET /api/2.0/fo/asset/host/
Parameters:
  action=list
  details=Basic|All|None
  ips=IP1,IP2,...
  ag_ids=ID1,ID2,...
  ids=HOSTID1,HOSTID2,...
  no_vm_scan_since=YYYY-MM-DD
  vm_scan_since=YYYY-MM-DD
  compliance_enabled=0|1
```

## Authentication
- **Method**: HTTP Basic Authentication
- **Headers**:
  ```
  Authorization: Basic base64(username:password)
  X-Requested-With: Curl (recommended)
  ```

## Response Formats
Qualys API supports both XML and JSON responses, though JSON support varies by endpoint.

### Content Negotiation
- **JSON Request**:
  ```
  Accept: application/json
  Content-Type: application/json
  ```
- **XML Request** (default):
  ```
  Accept: application/xml
  Content-Type: application/xml
  ```

### JSON Fallback Strategy
1. Try JSON with `Accept: application/json`
2. On 406/415 or invalid JSON, fallback to XML
3. Parse XML response if JSON unavailable

## Response Schemas

### Host VM Detection Response (XML)
```xml
<HOST_LIST_VM_DETECTION_OUTPUT>
  <RESPONSE>
    <DATETIME>ISO8601</DATETIME>
    <HOST_LIST>
      <HOST>
        <ID>integer</ID>
        <IP>string</IP>
        <TRACKING_METHOD>IP|DNS|NETBIOS|AGENT</TRACKING_METHOD>
        <OS>string</OS>
        <OS_CPE>string</OS_CPE>
        <DNS>string</DNS>
        <DNS_DATA>
          <HOSTNAME>string</HOSTNAME>
          <DOMAIN>string</DOMAIN>
          <FQDN>string</FQDN>
        </DNS_DATA>
        <NETBIOS>string</NETBIOS>
        <QG_HOSTID>string</QG_HOSTID>
        <LAST_SCAN_DATETIME>ISO8601</LAST_SCAN_DATETIME>
        <LAST_VM_SCANNED_DATE>ISO8601</LAST_VM_SCANNED_DATE>
        <LAST_VM_AUTH_SCANNED_DATE>ISO8601</LAST_VM_AUTH_SCANNED_DATE>
        <DETECTION_LIST>
          <DETECTION>
            <UNIQUE_VULN_ID>integer</UNIQUE_VULN_ID>
            <QID>integer</QID>
            <TYPE>Confirmed|Potential</TYPE>
            <SEVERITY>1-5</SEVERITY>
            <PORT>integer</PORT>
            <PROTOCOL>tcp|udp|icmp</PROTOCOL>
            <SERVICE>string</SERVICE>
            <FQDN>string</FQDN>
            <SSL>0|1</SSL>
            <INSTANCE>string</INSTANCE>
            <RESULTS>CDATA</RESULTS>
            <STATUS>New|Active|Fixed|Re-Opened</STATUS>
            <FIRST_FOUND_DATETIME>ISO8601</FIRST_FOUND_DATETIME>
            <LAST_FOUND_DATETIME>ISO8601</LAST_FOUND_DATETIME>
            <TIMES_FOUND>integer</TIMES_FOUND>
            <LAST_TEST_DATETIME>ISO8601</LAST_TEST_DATETIME>
            <LAST_UPDATE_DATETIME>ISO8601</LAST_UPDATE_DATETIME>
            <LAST_FIXED_DATETIME>ISO8601</LAST_FIXED_DATETIME>
            <IS_IGNORED>0|1</IS_IGNORED>
            <IS_DISABLED>0|1</IS_DISABLED>
            <AFFECT_RUNNING_KERNEL>0|1</AFFECT_RUNNING_KERNEL>
            <AFFECT_RUNNING_SERVICE>0|1</AFFECT_RUNNING_SERVICE>
            <AFFECT_EXPLOITABLE_CONFIG>0|1</AFFECT_EXPLOITABLE_CONFIG>
          </DETECTION>
        </DETECTION_LIST>
      </HOST>
    </HOST_LIST>
  </RESPONSE>
</HOST_LIST_VM_DETECTION_OUTPUT>
```

### Knowledge Base Response (XML)
```xml
<KNOWLEDGE_BASE_VULN_LIST_OUTPUT>
  <RESPONSE>
    <VULN_LIST>
      <VULN>
        <QID>integer</QID>
        <VULN_TYPE>Vulnerability|Potential|Information Gathered</VULN_TYPE>
        <SEVERITY_LEVEL>1-5</SEVERITY_LEVEL>
        <TITLE>string</TITLE>
        <CATEGORY>string</CATEGORY>
        <DETECTION_INFO>CDATA</DETECTION_INFO>
        <LAST_SERVICE_MODIFICATION_DATETIME>ISO8601</LAST_SERVICE_MODIFICATION_DATETIME>
        <PUBLISHED_DATETIME>ISO8601</PUBLISHED_DATETIME>
        <BUGTRAQ_LIST>
          <BUGTRAQ>
            <ID>integer</ID>
            <URL>string</URL>
          </BUGTRAQ>
        </BUGTRAQ_LIST>
        <PATCHABLE>0|1</PATCHABLE>
        <SOFTWARE_LIST>
          <SOFTWARE>
            <PRODUCT>string</PRODUCT>
            <VENDOR>string</VENDOR>
          </SOFTWARE>
        </SOFTWARE_LIST>
        <VENDOR_REFERENCE_LIST>
          <VENDOR_REFERENCE>
            <ID>string</ID>
            <URL>string</URL>
          </VENDOR_REFERENCE>
        </VENDOR_REFERENCE_LIST>
        <CVE_LIST>
          <CVE>
            <ID>CVE-YYYY-NNNN</ID>
            <URL>string</URL>
          </CVE>
        </CVE_LIST>
        <CVSS>
          <BASE>0.0-10.0</BASE>
          <TEMPORAL>0.0-10.0</TEMPORAL>
          <VECTOR>
            <ACCESS_VECTOR>string</ACCESS_VECTOR>
            <ACCESS_COMPLEXITY>string</ACCESS_COMPLEXITY>
            <AUTHENTICATION>string</AUTHENTICATION>
            <CONFIDENTIALITY_IMPACT>string</CONFIDENTIALITY_IMPACT>
            <INTEGRITY_IMPACT>string</INTEGRITY_IMPACT>
            <AVAILABILITY_IMPACT>string</AVAILABILITY_IMPACT>
          </VECTOR>
        </CVSS>
        <CVSS_V3>
          <BASE>0.0-10.0</BASE>
          <TEMPORAL>0.0-10.0</TEMPORAL>
          <VECTOR>CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H</VECTOR>
        </CVSS_V3>
        <DIAGNOSIS>CDATA</DIAGNOSIS>
        <CONSEQUENCE>CDATA</CONSEQUENCE>
        <SOLUTION>CDATA</SOLUTION>
        <COMPLIANCE_LIST>
          <COMPLIANCE>
            <TYPE>PCI|HIPAA|SOX|GLBA</TYPE>
            <SECTION>string</SECTION>
            <DESCRIPTION>string</DESCRIPTION>
          </COMPLIANCE>
        </COMPLIANCE_LIST>
        <CORRELATION>
          <EXPLOITS>
            <EXPLT_SRC>
              <SRC_NAME>string</SRC_NAME>
              <EXPLT_LIST>
                <EXPLT>
                  <REF>string</REF>
                  <DESC>string</DESC>
                  <LINK>string</LINK>
                </EXPLT>
              </EXPLT_LIST>
            </EXPLT_SRC>
          </EXPLOITS>
          <MALWARE>
            <MW_SRC>
              <SRC_NAME>string</SRC_NAME>
              <MW_LIST>
                <MW_INFO>
                  <MW_ID>string</MW_ID>
                  <MW_TYPE>string</MW_TYPE>
                  <MW_PLATFORM>string</MW_PLATFORM>
                  <MW_ALIAS>string</MW_ALIAS>
                  <MW_RATING>string</MW_RATING>
                  <MW_LINK>string</MW_LINK>
                </MW_INFO>
              </MW_LIST>
            </MW_SRC>
          </MALWARE>
        </CORRELATION>
        <LAST_CUSTOMIZATION_DATETIME>ISO8601</LAST_CUSTOMIZATION_DATETIME>
      </VULN>
    </VULN_LIST>
  </RESPONSE>
</KNOWLEDGE_BASE_VULN_LIST_OUTPUT>
```

## Field Mappings to Canonical Schema

### Primary Mappings
| Qualys Field | Canonical Field | Type | Description |
|--------------|-----------------|------|-------------|
| `QID` | `qid` | string | Qualys ID |
| `CVE_LIST/CVE/ID` or first CVE | `vuln_key` | string | Primary identifier |
| `CVE_LIST/CVE/ID[]` | `cve` | array | All CVE IDs |
| `SEVERITY` | `severity` | string | 1→info, 2→low, 3→medium, 4→high, 5→critical |
| `CVSS/BASE` or `CVSS_V3/BASE` | `cvss.baseScore` | number | CVSS score |
| `CVSS_V3/VECTOR` | `cvss.vector` | string | CVSS v3 vector |
| `IP` | `asset_identifiers.ip` | string | IP address |
| `DNS` or `HOSTNAME` | `asset_identifiers.hostname` | string | Hostname |
| `AGENT_ID` | `asset_identifiers.agentId` | string | Agent ID |
| `FIRST_FOUND_DATETIME` | `first_seen` | datetime | First detection |
| `LAST_FOUND_DATETIME` | `last_seen` | datetime | Last detection |
| `STATUS` | `status` | string | New/Active→open, Fixed→fixed, Re-Opened→reopened |
| `PATCHABLE` | `patch_available` | boolean | Patch availability |
| `SOLUTION` | `solution` | string | Fix instructions |
| `RESULTS` | `evidence` | string | Detection details |

### Location Mappings
| Qualys Field | Canonical Field | Type | Description |
|--------------|-----------------|------|-------------|
| `PORT` | `location.port` | number | Network port |
| `PROTOCOL` | `location.protocol` | string | Protocol |
| `SERVICE` | `location.service` | string | Service name |
| `SOFTWARE_LIST/SOFTWARE/PRODUCT` | `location.softwareName` | string | Software |
| `SOFTWARE_LIST/SOFTWARE/VENDOR` | `location.vendor` | string | Vendor |

### Status Mappings
| Qualys Status | Canonical Status | Description |
|---------------|------------------|-------------|
| `New` | `open` | Newly discovered |
| `Active` | `open` | Active vulnerability |
| `Fixed` | `fixed` | Resolved |
| `Re-Opened` | `reopened` | Previously fixed, found again |

### Severity Mappings
| Qualys Level | Canonical Severity | Description |
|--------------|-------------------|-------------|
| `5` | `critical` | Urgent/Critical |
| `4` | `high` | High severity |
| `3` | `medium` | Medium severity |
| `2` | `low` | Low severity |
| `1` | `info` | Informational |

## Pagination
- Use `truncation_limit` parameter (max 10000)
- For large result sets, use date ranges:
  - `vm_scan_since` and `vm_scan_before`
  - `last_modified_after` and `last_modified_before`

## Rate Limits
- **Default**: 300 API calls per hour
- **Burst**: 10 concurrent requests
- **Headers**: Check `X-RateLimit-Remaining` and `X-RateLimit-Limit`
- **429 Response**: Rate limit exceeded, check `Retry-After` header

## Error Responses
```xml
<SIMPLE_RETURN>
  <RESPONSE>
    <DATETIME>ISO8601</DATETIME>
    <CODE>999</CODE>
    <TEXT>Error message</TEXT>
  </RESPONSE>
</SIMPLE_RETURN>
```

### Common Error Codes
| Code | Description | Resolution |
|------|-------------|------------|
| `999` | Generic error | Check error text |
| `1000` | Invalid credentials | Verify username/password |
| `1001` | Invalid IP | Check IP format |
| `1002` | No data found | Adjust query parameters |
| `1003` | Too many results | Reduce truncation_limit |
| `1004` | Invalid date format | Use YYYY-MM-DD |
| `1005` | Permission denied | Check user permissions |
| `2000` | Invalid parameter | Check parameter names |

## Authentication Requirements
- **User Type**: Manager or Unit Manager role
- **Permissions Required**:
  - API Access enabled
  - VM module access
  - Asset view permissions
  - KB read permissions

## Important Implementation Notes

1. **XML vs JSON**: Most endpoints return XML by default. JSON support is limited and inconsistent.

2. **Date Handling**: Always use `YYYY-MM-DD` format for dates. Times in ISO8601 with timezone.

3. **Detection States**:
   - `New`: First time detected
   - `Active`: Detected multiple times
   - `Fixed`: No longer detected
   - `Re-Opened`: Was fixed, detected again

4. **QID Enrichment**: Join detection QIDs with KB data for complete vulnerability details (CVE, CVSS, solution).

5. **Host Identification**: Use combination of IP, DNS, and AGENT_ID for unique host identification.

6. **CDATA Sections**: Many text fields use CDATA. Strip CDATA tags when parsing.

7. **Batch Processing**:
   - Process hosts in batches
   - Use `truncation_limit` wisely
   - Implement retry logic for timeouts

8. **Caching Strategy**:
   - Cache KB data for 24 hours
   - Cache host list for 1 hour
   - Refresh detections every scan cycle

9. **Performance Tips**:
   - Use `show_results=0` when not needed
   - Filter by date ranges for incremental updates
   - Parallelize host processing

10. **Special Characters**: XML encode special characters in parameters (&amp; &lt; &gt; &quot; &apos;)