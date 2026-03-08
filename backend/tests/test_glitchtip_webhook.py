"""Tests for GlitchTip webhook formatting and delivery — 8 tests, mocked network calls."""

import json
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
import requests

# Add backend to path for imports
import sys
from pathlib import Path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from test_glitchtip_webhook import (
    create_test_alert_payload,
    send_discord_webhook,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_glitchtip_webhook_data() -> dict:
    """Create mock GlitchTip webhook data for testing."""
    return {
        "data": {
            "issue": {
                "title": "ValueError: Test exception",
                "culprit": "backend/agents/interview_agent.py:line 142",
                "web_url": "https://glitchtip.example.com/issues/12345"
            },
            "event": {
                "title": "ValueError: Test exception",
                "level": "error",
                "environment": "production",
                "tags": {
                    "session_id": "test-session-789",
                    "phase": "deep_dive",
                    "turn_number": "12"
                }
            }
        }
    }


# ---------------------------------------------------------------------------
# Tests - Payload Creation
# ---------------------------------------------------------------------------

def test_create_test_alert_payload():
    """Payload has required Discord embed structure."""
    payload = create_test_alert_payload()

    assert "embeds" in payload
    assert len(payload["embeds"]) == 1

    embed = payload["embeds"][0]
    assert "title" in embed
    assert "🚨" in embed["title"]
    assert "description" in embed
    assert "color" in embed
    assert embed["color"] == 16711680  # Red
    assert "fields" in embed
    assert "timestamp" in embed


def test_payload_contains_required_fields():
    """Payload includes all required alert fields."""
    payload = create_test_alert_payload()
    embed = payload["embeds"][0]

    # Extract field names
    field_names = [field["name"] for field in embed["fields"]]

    # Required fields
    assert "Error Count" in field_names
    assert "Environment" in field_names
    assert "Session ID" in field_names
    assert "Phase" in field_names
    assert "Turn Number" in field_names

    # Verify inline formatting
    for field in embed["fields"]:
        assert "inline" in field


def test_payload_timestamp_format():
    """Timestamp is valid ISO 8601 format."""
    payload = create_test_alert_payload()
    timestamp = payload["embeds"][0]["timestamp"]

    # Should parse without error
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert isinstance(parsed, datetime)


# ---------------------------------------------------------------------------
# Tests - Webhook Delivery
# ---------------------------------------------------------------------------

@patch('requests.post')
def test_send_discord_webhook_success(mock_post):
    """Webhook delivery succeeds with HTTP 204."""
    mock_response = Mock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    payload = create_test_alert_payload()
    webhook_url = "https://discord.com/api/webhooks/123/abc"

    result = send_discord_webhook(webhook_url, payload)

    assert result is True
    mock_post.assert_called_once()

    # Verify call parameters
    call_args = mock_post.call_args
    assert call_args.args[0] == webhook_url
    assert call_args.kwargs["json"] == payload
    assert call_args.kwargs["headers"]["Content-Type"] == "application/json"
    assert call_args.kwargs["timeout"] == 10


@patch('requests.post')
def test_send_discord_webhook_accepts_200(mock_post):
    """Webhook delivery succeeds with HTTP 200 (alternative success code)."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    payload = create_test_alert_payload()
    result = send_discord_webhook("https://discord.com/api/webhooks/123/abc", payload)

    assert result is True


@patch('requests.post')
def test_send_discord_webhook_failure_4xx(mock_post):
    """Webhook delivery fails with HTTP 400 Bad Request."""
    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"
    mock_post.return_value = mock_response

    payload = create_test_alert_payload()
    result = send_discord_webhook("https://discord.com/api/webhooks/123/abc", payload)

    assert result is False


@patch('requests.post')
def test_send_discord_webhook_timeout(mock_post):
    """Webhook delivery fails on timeout."""
    mock_post.side_effect = requests.exceptions.Timeout()

    payload = create_test_alert_payload()
    result = send_discord_webhook("https://discord.com/api/webhooks/123/abc", payload)

    assert result is False


@patch('requests.post')
def test_send_discord_webhook_network_error(mock_post):
    """Webhook delivery fails on network error."""
    mock_post.side_effect = requests.exceptions.ConnectionError("Network unreachable")

    payload = create_test_alert_payload()
    result = send_discord_webhook("https://discord.com/api/webhooks/123/abc", payload)

    assert result is False


# ---------------------------------------------------------------------------
# Tests - Webhook Proxy Transformation
# ---------------------------------------------------------------------------

def test_glitchtip_to_discord_transformation():
    """GlitchTip webhook data transforms correctly to Discord format."""
    # Import here to avoid issues if webhook_proxy.py imports fail
    try:
        from webhook_proxy import GlitchTipWebhookHandler
    except ImportError:
        pytest.skip("webhook_proxy.py not available or missing dependencies")

    # BaseHTTPRequestHandler.__init__ calls self.handle() immediately which
    # tries to read from the socket. Bypass __init__ to test _transform_to_discord directly.
    handler = object.__new__(GlitchTipWebhookHandler)
    glitchtip_data = _mock_glitchtip_webhook_data()

    discord_payload = handler._transform_to_discord(glitchtip_data)

    # Verify structure
    assert "embeds" in discord_payload
    assert len(discord_payload["embeds"]) == 1

    embed = discord_payload["embeds"][0]
    assert "title" in embed
    assert "InterviewOS Alert" in embed["title"]
    assert "description" in embed
    assert "ValueError: Test exception" in embed["description"]

    # Verify fields extracted from GlitchTip data
    field_dict = {field["name"]: field["value"] for field in embed["fields"]}
    assert field_dict.get("Session ID") == "test-session-789"
    assert field_dict.get("Phase") == "deep_dive"
    assert field_dict.get("Turn Number") == "12"
    assert field_dict.get("Environment") == "production"
