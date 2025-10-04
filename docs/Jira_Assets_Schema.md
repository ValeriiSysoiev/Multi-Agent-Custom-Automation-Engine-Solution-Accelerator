# Jira Assets Schema Documentation

## Overview
This document describes the exact schema for Host and Application/Service types in the Jira Assets CMDB configuration used by the vulnerability management system.

## Host Type (ID: 13)

### Required Attributes
- **Key** - System-generated unique identifier
- **Created** - System timestamp for creation
- **Updated** - System timestamp for last update
- **Hostname** - Host name of the server (user-editable, indexed)

### Identity Attributes (Used for Asset Matching)
- **IP** - IP Address of the host
- **ResourceID** - Azure Resource ID
- **MAC Address** - MAC Address of the host
- **Hostname** - Host name (also serves as identity)

### Business Context Attributes
- **Owner** - Owner of the asset
- **Owner Email** - Owner email address
- **Owner Group** - Team responsible
- **Business Unit** - Business unit owning the asset
- **Service Tier** - Service tier classification
- **Data Classification** - Data sensitivity level
- **Business Criticality** - Business criticality level
- **Criticality** - Criticality level (alias)

### Technical Attributes
- **Environment** - Environment (Test/Prod/Dev)
- **Platform** - Platform/Cloud provider
- **Operating System** - OS type and version
- **Status** - Current status
- **Location** - Physical/Region location

### Application Linkage Attributes
- **Application** (Type: 1 - Reference) - References Application/Service type (ID: 11)
- **Application / Service** - Application or service name (text field)
- **Business Service** - Business service name
- **Service** - Service name (alias)

## Application / Service Type (ID: 11)

### Required Attributes
- **Key** - System-generated unique identifier
- **Created** - System timestamp for creation
- **Updated** - System timestamp for last update
- **Name** - Application name (user-editable, indexed)

### Ownership Attributes
- **Owner** (Type: 2 - User) - Application owner (Jira user reference)
- **Service Owner** - Service owner (text alias)
- **Business Owner** - Business owner (text alias)

### Business Context Attributes
- **Business Service** - Business service this app supports
- **Business Unit** - Owning business unit
- **Business Criticality** - Business criticality
- **Criticality** - Criticality (alias)
- **Data Classification** - Data sensitivity

### Technical Attributes
- **Environment** - Deployment environment
- **Platform** - Platform/technology
- **Service** - Service name (alias)

### Security/Exposure Attributes
- **Internet Facing** - Exposed to internet
- **Authentication Required** - Requires authentication

## Attribute Type Codes
- **Type 0** - Text/String field
- **Type 1** - Object Reference (links to another object)
- **Type 2** - User Reference (links to Jira user)

## Key Observations

### Asset Identification Strategy
The system uses multiple attributes to identify and link assets:
1. **Primary identifiers**: ResourceID (Azure), Hostname, IP, MAC Address
2. **Fallback matching**: Uses broader searches when specific type searches fail

### Application Linkage
Hosts can be linked to Applications in two ways:
1. **Direct reference**: Via the "Application" field (Type 1 reference to Application/Service object)
2. **Text fields**: Via "Application / Service", "Business Service", or "Service" text fields

### Data Duplication for Flexibility
Several attributes appear in both Host and Application/Service types:
- Business Criticality
- Environment
- Platform
- Business Unit
- Data Classification

This allows for:
- Independent tracking when assets aren't linked
- Override capabilities at different levels
- Fallback values when linkage is incomplete

### Enrichment Context Mapping
The enrichment service uses these attributes to build:
- **ApplicationContext**: Owner, Business Unit, Service Tier, Data Classification
- **ExposureSurface**: Internet Facing, Authentication Required
- **OwnershipStatus**: Based on presence of owner/email fields
- **LinkageReviewInfo**: When host can't be found or linked

## Integration Notes

### Field Matching in Code
The `jira_assets_client.py` uses these mappings:
```python
ATTRIBUTE_NAME_MAP = {
    AssetIdentifierType.CLOUD_RESOURCE_ID: ("ResourceID", "Resource Id", "Resource ID", "Azure Resource ID"),
    AssetIdentifierType.HOSTNAME: ("Hostname", "Host Name", "FQDN", "Device Name"),
    AssetIdentifierType.IP_ADDRESS: ("IP", "IP Address", "IPv4", "IPv6"),
    AssetIdentifierType.MAC_ADDRESS: ("MAC Address", "MAC", "Mac Address"),
    AssetIdentifierType.SCANNER_AGENT_ID: ("Scanner Agent Id", "Qualys Host ID", "Agent ID")
}
```

### Application Link Attributes
The system looks for application references in these fields (from environment config):
- JIRA_ASSETS_APPLICATION_LINK_ATTRIBUTES = "Application,Application / Service"

### Critical Fields for Enrichment Success
For successful enrichment and triage:
1. **Host must have**: At least one identifier (ResourceID, Hostname, IP, or MAC)
2. **Application linkage**: Via "Application" reference or text fields
3. **Business context**: Owner/Owner Email for ownership determination
4. **Criticality data**: Business Criticality or Criticality fields

## Data Quality Recommendations

1. **Ensure hosts have ResourceID** populated for Azure resources
2. **Link hosts to applications** using the Application reference field
3. **Populate owner information** to avoid LINKAGE_REVIEW status
4. **Set Business Criticality** for proper risk assessment
5. **Mark Internet Facing** applications for exposure tracking