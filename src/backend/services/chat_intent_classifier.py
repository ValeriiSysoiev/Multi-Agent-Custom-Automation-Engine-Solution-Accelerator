"""Intent resolution helpers for chat queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class ChatIntentResult:
    intent: str
    filters: Dict[str, object]


class ChatIntentClassifier:
    """Very lightweight classifier mapping natural language to query intents."""

    DEFAULT_INTENT = "open_findings"

    def classify(self, question: str) -> ChatIntentResult:
        text = (question or "").lower()

        if any(keyword in text for keyword in {"waiver", "exception", "accept"}):
            days = 30
            if "next week" in text:
                days = 7
            elif "today" in text:
                days = 1
            return ChatIntentResult(
                intent="waivers_due",
                filters={"days": days},
            )

        if any(keyword in text for keyword in {"ticket", "jira", "issue"}):
            statuses = ["open", "in_progress"]
            if "resolved" in text or "closed" in text:
                statuses = ["resolved", "verified"]
            return ChatIntentResult(
                intent="tickets_by_status",
                filters={"statuses": statuses},
            )

        if any(keyword in text for keyword in {"kev", "known exploited", "cisa"}):
            risk_tiers = []
            if "critical" in text:
                risk_tiers.append("critical")
            if "high" in text:
                risk_tiers.append("high")
            return ChatIntentResult(
                intent="kev_exposures",
                filters={"risk_tiers": risk_tiers},
            )

        if any(keyword in text for keyword in {"summary", "overview", "executive", "trend"}):
            return ChatIntentResult(
                intent="executive_summary",
                filters={},
            )

        risk_tiers = []
        if "critical" in text:
            risk_tiers.extend(["critical"])
        if "high" in text:
            risk_tiers.extend(["high"])
        if not risk_tiers:
            risk_tiers = ["critical", "high"]

        return ChatIntentResult(
            intent=self.DEFAULT_INTENT,
            filters={"risk_tiers": risk_tiers},
        )


__all__ = ["ChatIntentClassifier", "ChatIntentResult"]
