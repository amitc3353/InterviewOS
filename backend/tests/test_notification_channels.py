"""Tests for notification channel management — 18 tests, zero network calls."""

from unittest.mock import patch

import pytest

from backend.monitoring.notification_channels import (
    ChannelType,
    NotificationChannel,
    NotificationRouter,
    _mask_sensitive,
    get_default_channels,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_channel(channel_id: str = "test_channel", **kwargs) -> NotificationChannel:
    """Build a minimal NotificationChannel for testing."""
    defaults = {
        "channel_id": channel_id,
        "name": "Test Channel",
        "channel_type": ChannelType.DISCORD,
        "target": "https://discord.com/api/webhooks/123/abc",
    }
    defaults.update(kwargs)
    return NotificationChannel(**defaults)


# ---------------------------------------------------------------------------
# Tests: NotificationChannel
# ---------------------------------------------------------------------------

def test_channel_to_dict():
    """NotificationChannel serializes correctly with masked target."""
    channel = _make_channel(severity_filter="high")
    result = channel.to_dict()

    assert result["id"] == "test_channel"
    assert result["name"] == "Test Channel"
    assert result["type"] == "discord"
    assert result["enabled"] is True
    assert result["severity_filter"] == "high"
    # Target should be masked (only last 8 chars visible)
    assert result["target"].startswith("...")


def test_channel_validate_valid():
    """Valid channel passes validation."""
    channel = _make_channel()
    assert channel.validate() == []


def test_channel_validate_missing_id():
    """Channel validation catches empty ID."""
    channel = _make_channel(channel_id="")
    errors = channel.validate()
    assert any("Channel ID" in e for e in errors)


def test_channel_validate_missing_target():
    """Channel validation catches empty target."""
    channel = _make_channel(target="")
    errors = channel.validate()
    assert any("target is required" in e for e in errors)


def test_channel_validate_invalid_discord_url():
    """Channel validation catches invalid Discord webhook URL."""
    channel = _make_channel(
        channel_type=ChannelType.DISCORD,
        target="https://example.com/webhook",
    )
    errors = channel.validate()
    assert any("Discord webhook URL" in e for e in errors)


def test_channel_validate_invalid_email():
    """Channel validation catches invalid email address."""
    channel = _make_channel(
        channel_type=ChannelType.EMAIL,
        target="not-an-email",
    )
    errors = channel.validate()
    assert any("email address" in e for e in errors)


def test_channel_validate_valid_email():
    """Channel validation passes for valid email."""
    channel = _make_channel(
        channel_type=ChannelType.EMAIL,
        target="alerts@example.com",
    )
    assert channel.validate() == []


# ---------------------------------------------------------------------------
# Tests: NotificationRouter
# ---------------------------------------------------------------------------

def test_router_add_channel():
    """NotificationRouter.add_channel adds a channel."""
    router = NotificationRouter()
    router.add_channel(_make_channel())

    assert len(router.channels) == 1


def test_router_add_channel_rejects_duplicate():
    """NotificationRouter.add_channel raises ValueError on duplicate ID."""
    router = NotificationRouter()
    router.add_channel(_make_channel("ch1"))

    with pytest.raises(ValueError, match="already exists"):
        router.add_channel(_make_channel("ch1"))


def test_router_remove_channel():
    """NotificationRouter.remove_channel removes channel and returns True."""
    router = NotificationRouter()
    router.add_channel(_make_channel("ch1"))

    assert router.remove_channel("ch1") is True
    assert len(router.channels) == 0


def test_router_remove_nonexistent():
    """NotificationRouter.remove_channel returns False for missing channel."""
    router = NotificationRouter()
    assert router.remove_channel("nonexistent") is False


def test_router_get_channel():
    """NotificationRouter.get_channel returns channel by ID."""
    router = NotificationRouter()
    router.add_channel(_make_channel("ch1", name="My Channel"))

    channel = router.get_channel("ch1")
    assert channel is not None
    assert channel.name == "My Channel"


def test_router_get_channels_for_severity_all():
    """Channels without severity filter receive all severities."""
    router = NotificationRouter()
    router.add_channel(_make_channel("ch1", severity_filter=None))

    assert len(router.get_channels_for_severity("info")) == 1
    assert len(router.get_channels_for_severity("critical")) == 1


def test_router_get_channels_for_severity_filtered():
    """Channels with severity filter only receive matching or higher severities."""
    router = NotificationRouter()
    router.add_channel(_make_channel("ch_critical", severity_filter="critical"))
    router.add_channel(_make_channel("ch_low", severity_filter="low"))

    # Low severity — only ch_low matches
    low_channels = router.get_channels_for_severity("low")
    assert len(low_channels) == 1
    assert low_channels[0].channel_id == "ch_low"

    # Critical severity — both match
    critical_channels = router.get_channels_for_severity("critical")
    assert len(critical_channels) == 2


def test_router_get_channels_excludes_disabled():
    """Disabled channels are excluded from routing."""
    router = NotificationRouter()
    router.add_channel(_make_channel("ch1", enabled=True, severity_filter=None))
    router.add_channel(_make_channel("ch2", enabled=False, severity_filter=None))

    assert len(router.get_channels_for_severity("critical")) == 1


def test_router_validate_all():
    """NotificationRouter.validate_all returns errors for invalid channels."""
    router = NotificationRouter()
    router.add_channel(_make_channel("valid"))
    router.add_channel(_make_channel("invalid", target=""))

    errors = router.validate_all()
    assert "valid" not in errors
    assert "invalid" in errors
    assert len(errors["invalid"]) > 0


def test_router_to_dict():
    """NotificationRouter.to_dict serializes router state."""
    router = NotificationRouter()
    router.add_channel(_make_channel("ch1", enabled=True))
    router.add_channel(_make_channel("ch2", enabled=False))

    result = router.to_dict()
    assert result["total_channels"] == 2
    assert result["enabled_channels"] == 1
    assert len(result["channels"]) == 2


# ---------------------------------------------------------------------------
# Tests: _mask_sensitive
# ---------------------------------------------------------------------------

def test_mask_discord_url():
    """Discord webhook URLs are masked to show only last 8 chars."""
    url = "https://discord.com/api/webhooks/123456/long_token_here"
    masked = _mask_sensitive(url)
    assert "123456" not in masked
    assert masked.startswith("...")


def test_mask_email():
    """Email addresses are partially masked."""
    masked = _mask_sensitive("alerts@example.com")
    assert "example.com" in masked
    assert "alerts" not in masked


def test_mask_empty_string():
    """Empty string returns empty string."""
    assert _mask_sensitive("") == ""


# ---------------------------------------------------------------------------
# Tests: get_default_channels()
# ---------------------------------------------------------------------------

@patch.dict('os.environ', {
    'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/123/abc',
    'ALERT_EMAIL': 'alerts@example.com',
})
def test_get_default_channels_with_both_configured():
    """Default channels includes both Discord and email when configured."""
    router = get_default_channels()

    assert len(router.channels) == 4  # 2 Discord + 2 Email

    types = {ch.channel_type for ch in router.channels}
    assert ChannelType.DISCORD in types
    assert ChannelType.EMAIL in types


@patch.dict('os.environ', {'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/123/abc'}, clear=True)
def test_get_default_channels_discord_only():
    """Default channels creates only Discord channels when no email."""
    router = get_default_channels()

    assert len(router.channels) == 2
    assert all(ch.channel_type == ChannelType.DISCORD for ch in router.channels)


@patch.dict('os.environ', {}, clear=True)
def test_get_default_channels_no_config():
    """Default channels returns empty router when nothing configured."""
    router = get_default_channels()
    assert len(router.channels) == 0
