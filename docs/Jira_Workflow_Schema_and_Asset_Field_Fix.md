# Jira Workflow Schema Documentation and Asset Field Configuration

## Issue Identified

The **Asset(s)** field (customfield_10065) in Jira is currently configured as a **multi-select list** with predefined options. This causes problems for the remediation agent because:

1. The field expects specific option IDs from a predefined list
2. The remediation agent tries to populate it with dynamic asset IDs from Jira Assets
3. Since the asset IDs don't match the predefined options, ticket creation fails

## Current Field Configuration

```json
{
  "id": "customfield_10065",
  "name": "Asset(s)",
  "type": "array",
  "items": "option",
  "schema": {
    "type": "array",
    "items": "option",
    "custom": "com.atlassian.jira.plugin.system.customfieldtypes:multiselect",
    "customId": 10065
  }
}
```

## Affected Workflows

The Asset(s) field appears in the following issue types:
1. **Vulnerability Remediation Workflow**
2. **Risk Acceptance (Waiver)**
3. **Ownership/Linkage Review**

## Solution: Convert Asset(s) Field to Text

### Option 1: Single-Line Text Field (Recommended)

Convert the field to a single-line text field that can accept comma-separated asset names or IDs.

**Steps to implement:**

1. **Access Jira Administration:**
   - Go to Jira Settings > Issues > Custom fields
   - Search for "Asset(s)" field (customfield_10065)

2. **Change Field Type:**
   - Click on the field configuration
   - Change type from "Select List (multiple choices)" to "Text Field (single line)"
   - This allows free-text entry of asset information

3. **Update Field Context:**
   - Configure the field to be available for:
     - Vulnerability Remediation Workflow
     - Risk Acceptance (Waiver)
     - Ownership/Linkage Review

4. **Update Field Description:**
   - Add help text: "Enter asset names or IDs, separated by commas (e.g., HOST-123, APP-456)"

### Option 2: Multi-Line Text Field

If more detailed asset information is needed:

1. Change to "Text Field (multi-line)"
2. This allows listing multiple assets with additional context:
   ```
   Assets:
   - HOST-123 (Production Server)
   - APP-456 (Customer Portal)
   ```

### Option 3: Use Jira Assets Object Field (Advanced)

If you want to maintain linkage to Jira Assets objects:

1. Install/enable Jira Assets app integration
2. Create a new field of type "Assets Object"
3. Configure it to search/select from Host and Application/Service types
4. This maintains referential integrity but requires Jira Assets license

## Code Changes Required

After changing the field to text, update the remediation agent code:

### Current Code (for array field):
```python
def _format_asset_refs(asset_ids: Iterable[str]) -> List[Dict[str, str]]:
    refs: List[Dict[str, str]] = []
    for value in asset_ids:
        if value:
            refs.append({"objectId": str(value)})
    return refs
```

### Updated Code (for text field):
```python
def _format_asset_refs(asset_ids: Iterable[str]) -> str:
    """Format asset IDs as comma-separated string for text field."""
    return ", ".join(str(aid) for aid in asset_ids if aid)
```

### Update in jira_ticket_client.py:

```python
# In update_issue_fields method, change:
if asset_refs:
    update_fields["customfield_10065"] = asset_refs  # Old: array

# To:
if asset_refs:
    update_fields["customfield_10065"] = asset_refs  # New: string
```

## Testing After Change

1. **Manual Test:**
   - Create a test ticket in each workflow type
   - Enter sample asset data: "HOST-001, APP-002"
   - Verify the field accepts and displays the text correctly

2. **API Test:**
   ```python
   # Test creating ticket with new text field
   fields = {
       "customfield_10065": "HOST-001, APP-002",  # Text string
       # ... other fields
   }
   ```

3. **Integration Test:**
   - Run the remediation agent with test data
   - Verify tickets are created successfully with asset information

## Benefits of Text Field

1. **Flexibility:** Can accept any asset identifier format
2. **No Maintenance:** No need to maintain predefined option lists
3. **Dynamic Content:** Remediation agent can populate with actual asset IDs
4. **Human Readable:** Can include asset names alongside IDs
5. **Searchable:** Jira text search will find tickets by asset names/IDs

## Migration Considerations

1. **Existing Tickets:** The multi-select values in existing tickets will be converted to text
2. **Reports:** Update any reports/dashboards that rely on the field
3. **Automation:** Review any automation rules using this field
4. **JQL Queries:** Update saved filters that query this field:
   - Old: `"Asset(s)" in (option1, option2)`
   - New: `"Asset(s)" ~ "HOST-001"`

## Alternative: Add New Text Field

If you can't modify the existing field:

1. Create a new custom field: "Asset Names" (customfield_100XX)
2. Configure it as text field
3. Add to the same issue types
4. Update code to use the new field ID
5. Gradually migrate from old to new field

## Recommended Action Plan

1. **Immediate:** Document current field usage and dependencies
2. **Short-term:** Create new text field for testing in development environment
3. **Testing:** Validate remediation agent works with text field
4. **Migration:** Schedule field type change during maintenance window
5. **Update:** Modify remediation agent code to use text format
6. **Monitor:** Track ticket creation success rate after change

## Contact for Field Changes

Since field type changes require Jira admin permissions:

1. Contact your Jira administrator
2. Share this documentation
3. Request field type change for customfield_10065
4. Alternatively, request creation of new text field for assets

## Summary

The current multi-select list configuration of the Asset(s) field prevents dynamic population by the remediation agent. Converting it to a text field will resolve the issue and allow the agent to create tickets with proper asset references. This is a one-time configuration change that will significantly improve the automation workflow.