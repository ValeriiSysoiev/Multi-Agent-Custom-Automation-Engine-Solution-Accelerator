"""Modified JiraTicketClient to support Asset(s) as text field instead of multi-select.

This is the updated version that should be used after changing customfield_10065
from a multi-select list to a text field in Jira configuration.
"""

from typing import Any, Dict, Iterable, List, Optional


class JiraTicketClientTextFieldUpdate:
    """Code changes needed for text field support."""

    @staticmethod
    def _format_asset_refs_for_text(asset_ids: Iterable[str]) -> str:
        """
        Format asset IDs as comma-separated string for text field.

        Args:
            asset_ids: Iterable of asset IDs from Jira Assets

        Returns:
            Comma-separated string of asset IDs
        """
        return ", ".join(str(aid) for aid in asset_ids if aid)

    @staticmethod
    def _normalize_asset_field_text(value: Any) -> str:
        """
        Normalize asset field value to text string.

        Args:
            value: Raw value from asset field (could be list, dict, or string)

        Returns:
            Normalized text string
        """
        if not value:
            return ""

        if isinstance(value, str):
            return value

        if isinstance(value, list):
            # Handle list of asset references
            asset_names = []
            for item in value:
                if isinstance(item, dict):
                    # Try to extract ID or name from dict
                    asset_id = item.get("objectId") or item.get("id") or item.get("name")
                    if asset_id:
                        asset_names.append(str(asset_id))
                elif item:
                    asset_names.append(str(item))
            return ", ".join(asset_names)

        return str(value)

    def update_issue_fields_text_version(self, issue_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updated version of update_issue_fields that handles Asset(s) as text field.

        This replaces the array handling with text string handling.
        """
        update_fields = dict(payload)

        # Handle Asset(s) field as text instead of array
        if "asset_ids" in payload:
            asset_refs = self._format_asset_refs_for_text(payload["asset_ids"])
            if asset_refs:
                update_fields["customfield_10065"] = asset_refs  # Now a string
            update_fields.pop("asset_ids", None)

        # If customfield_10065 is already in the payload, ensure it's text
        if "customfield_10065" in update_fields:
            normalized_assets = self._normalize_asset_field_text(update_fields["customfield_10065"])
            if normalized_assets:
                update_fields["customfield_10065"] = normalized_assets
            else:
                update_fields.pop("customfield_10065", None)

        return update_fields


# Example usage after field conversion:
def example_usage():
    """
    Example of how to use the text field version.
    """

    # Sample asset IDs from enrichment
    asset_ids = ["HOST-123", "HOST-456", "APP-789"]

    # Format for text field
    client = JiraTicketClientTextFieldUpdate()
    asset_text = client._format_asset_refs_for_text(asset_ids)
    print(f"Asset field value: {asset_text}")
    # Output: "HOST-123, HOST-456, APP-789"

    # Create ticket with text field
    ticket_fields = {
        "summary": "Vulnerability on multiple assets",
        "customfield_10065": asset_text,  # Text string instead of array
        # ... other fields
    }

    return ticket_fields


# Migration helper to convert existing tickets
def migrate_existing_tickets_to_text(old_value: List[Dict[str, str]]) -> str:
    """
    Helper to migrate existing multi-select values to text.

    Args:
        old_value: Current multi-select array value

    Returns:
        Text representation for the new field
    """
    if not old_value:
        return ""

    asset_ids = []
    for item in old_value:
        if isinstance(item, dict):
            asset_id = item.get("value") or item.get("objectId") or item.get("id")
            if asset_id:
                asset_ids.append(str(asset_id))

    return ", ".join(asset_ids)


# Patch to apply to existing jira_ticket_client.py
PATCH_FOR_TEXT_FIELD = """
--- a/services/jira_ticket_client.py
+++ b/services/jira_ticket_client.py
@@ -276,11 +276,9 @@ class JiraTicketClient:

     @staticmethod
     def _format_asset_refs(asset_ids: Iterable[str]) -> str:
-        refs: List[Dict[str, str]] = []
-        for value in asset_ids:
-            if value:
-                refs.append({"objectId": str(value)})
-        return refs
+        \"\"\"Format asset IDs as comma-separated string for text field.\"\"\"
+        return ", ".join(str(aid) for aid in asset_ids if aid)

     def _normalize_asset_field(self, value: Any) -> str:
+        \"\"\"Normalize asset field value to text string.\"\"\"
         if not value:
-            return []
+            return ""
+
+        if isinstance(value, str):
+            return value
+
         if isinstance(value, list):
-            candidate_ids: List[str] = []
+            asset_names = []
             for item in value:
                 if isinstance(item, dict):
-                    object_id = item.get("objectId") or item.get("id")
-                    if object_id:
-                        candidate_ids.append(str(object_id))
-                elif isinstance(item, str):
-                    candidate_ids.append(item)
-            return self._format_asset_refs(candidate_ids)
-        return []
+                    asset_id = item.get("objectId") or item.get("id") or item.get("name")
+                    if asset_id:
+                        asset_names.append(str(asset_id))
+                elif item:
+                    asset_names.append(str(item))
+            return ", ".join(asset_names)
+
+        return str(value)
"""