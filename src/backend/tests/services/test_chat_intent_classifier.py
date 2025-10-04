import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example-openai")
os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
os.environ.setdefault("AZURE_OPENAI_API_VERSION", "2024-11-20")

from services.chat_intent_classifier import ChatIntentClassifier


def test_classify_waiver_intent():
    classifier = ChatIntentClassifier()
    result = classifier.classify("Which waivers will expire next week?")
    assert result.intent == "waivers_due"
    assert result.filters["days"] == 7


def test_classify_ticket_intent():
    classifier = ChatIntentClassifier()
    result = classifier.classify("Show me resolved Jira tickets")
    assert result.intent == "tickets_by_status"
    assert "resolved" in result.filters["statuses"]


def test_classify_default_open_findings():
    classifier = ChatIntentClassifier()
    result = classifier.classify("List high and critical findings for customer web")
    assert result.intent == "open_findings"
    assert "critical" in result.filters["risk_tiers"]
