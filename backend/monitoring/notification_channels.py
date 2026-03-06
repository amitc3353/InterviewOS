"""Team notification channel management for InterviewOS error monitoring.

Manages notification channels (Discord, email, webhook) and routes
alerts to the appropriate channels based on severity and configuration.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from backend.structured_logging import get_logger

logger = get_logger(__name__)


class ChannelType(Enum):
    """Notification channel types."""

    DISCORD = "discord"
    EMAIL = "email"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"


@dataclass
class NotificationChannel:
    """A notification channel configuration.

    Attributes:
        channel_id: Unique identifier for the channel
        name: Human-readable channel name
        channel_type: Type of notification channel
        target: Channel-specific target (URL, email address, etc.)
        enabled: Whether the channel is active
        severity_filter: Minimum severity level to send to this channel
        description: Description of the channel's purpose
    """

    channel_id: str
    name: str
    channel_type: ChannelType
    target: str
    enabled: bool = True
    severity_filter: Optional[str] = None
    description: str = ""

    def to_dict(self) -> Dict:
        """Serialize channel to dictionary."""
        return {
            "id": self.channel_id,
            "name": self.name,
            "type": self.channel_type.value,
            "target": _mask_sensitive(self.target),
            "enabled": self.enabled,
            "severity_filter": self.severity_filter,
            "description": self.description,
        }

    def validate(self) -> List[str]:
        """Validate channel configuration. Returns list of error messages."""
        errors: List[str] = []
        if not self.channel_id:
            errors.append("Channel ID is required")
        if not self.name:
            errors.append("Channel name is required")
        if not self.target:
            errors.append("Channel target is required")

        if self.channel_type == ChannelType.DISCORD:
            if not self.target.startswith("https://discord.com/api/webhooks/"):
                errors.append("Discord webhook URL must start with https://discord.com/api/webhooks/")

        if self.channel_type == ChannelType.EMAIL:
            if "@" not in self.target:
                errors.append("Email target must be a valid email address")

        valid_severities = {"critical", "high", "medium", "low", "info", None}
        if self.severity_filter not in valid_severities:
            errors.append(f"severity_filter must be one of: critical, high, medium, low, info")

        return errors


class NotificationRouter:
    """Routes alerts to appropriate notification channels based on severity.

    Manages a collection of channels and determines which channels
    should receive notifications based on alert severity.
    """

    # Severity ordering for comparison
    _SEVERITY_ORDER: Dict[str, int] = {
        "info": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }

    def __init__(self) -> None:
        """Initialize with empty channel list."""
        self._channels: List[NotificationChannel] = []

    @property
    def channels(self) -> List[NotificationChannel]:
        """Get all registered channels."""
        return list(self._channels)

    def add_channel(self, channel: NotificationChannel) -> None:
        """Add a notification channel.

        Raises:
            ValueError: If a channel with the same ID already exists
        """
        existing_ids = {c.channel_id for c in self._channels}
        if channel.channel_id in existing_ids:
            raise ValueError(f"Channel ID '{channel.channel_id}' already exists")
        self._channels.append(channel)

    def remove_channel(self, channel_id: str) -> bool:
        """Remove a channel by ID. Returns True if removed."""
        for i, channel in enumerate(self._channels):
            if channel.channel_id == channel_id:
                self._channels.pop(i)
                return True
        return False

    def get_channel(self, channel_id: str) -> Optional[NotificationChannel]:
        """Get a channel by ID."""
        for channel in self._channels:
            if channel.channel_id == channel_id:
                return channel
        return None

    def get_channels_for_severity(self, severity: str) -> List[NotificationChannel]:
        """Get all enabled channels that should receive alerts at the given severity.

        A channel receives an alert if:
        1. It is enabled
        2. Its severity_filter is at or below the alert severity (or has no filter)

        Args:
            severity: Alert severity level (critical, high, medium, low, info)

        Returns:
            List of channels that should be notified
        """
        severity_level = self._SEVERITY_ORDER.get(severity, 0)
        matching: List[NotificationChannel] = []

        for channel in self._channels:
            if not channel.enabled:
                continue

            if channel.severity_filter is None:
                # No filter means receive all severities
                matching.append(channel)
            else:
                filter_level = self._SEVERITY_ORDER.get(channel.severity_filter, 0)
                if severity_level >= filter_level:
                    matching.append(channel)

        return matching

    def validate_all(self) -> Dict[str, List[str]]:
        """Validate all channels. Returns dict of channel_id -> error list."""
        results: Dict[str, List[str]] = {}
        for channel in self._channels:
            errors = channel.validate()
            if errors:
                results[channel.channel_id] = errors
        return results

    def to_dict(self) -> Dict:
        """Serialize router state to dictionary."""
        return {
            "channels": [ch.to_dict() for ch in self._channels],
            "total_channels": len(self._channels),
            "enabled_channels": len([ch for ch in self._channels if ch.enabled]),
        }


def _mask_sensitive(value: str) -> str:
    """Mask sensitive parts of URLs and emails for safe display."""
    if not value:
        return ""

    if value.startswith("https://discord.com/api/webhooks/"):
        # Show last 8 characters of webhook URL
        return f"...{value[-8:]}" if len(value) > 8 else value

    if "@" in value:
        # Mask email: show first 2 chars and domain
        parts = value.split("@")
        if len(parts) == 2:
            local = parts[0][:2] + "***" if len(parts[0]) > 2 else parts[0]
            return f"{local}@{parts[1]}"

    if value.startswith("https://"):
        # Generic URL: show domain only
        return value.split("/")[2] if len(value.split("/")) > 2 else value

    return value


def get_default_channels() -> NotificationRouter:
    """Create default notification channels from environment variables.

    Reads DISCORD_WEBHOOK_URL and ALERT_EMAIL from environment.

    Returns:
        NotificationRouter with configured channels
    """
    router = NotificationRouter()

    discord_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    alert_email = os.getenv("ALERT_EMAIL", "")

    if discord_url:
        # Primary Discord channel for all critical/high alerts
        router.add_channel(NotificationChannel(
            channel_id="discord_critical",
            name="Discord - Critical Alerts",
            channel_type=ChannelType.DISCORD,
            target=discord_url,
            enabled=True,
            severity_filter="critical",
            description="Immediate Discord notifications for critical errors and outages",
        ))

        # Discord channel for high-severity alerts
        router.add_channel(NotificationChannel(
            channel_id="discord_high",
            name="Discord - High Priority",
            channel_type=ChannelType.DISCORD,
            target=discord_url,
            enabled=True,
            severity_filter="high",
            description="Discord notifications for high-priority errors (STT/TTS/LLM failures)",
        ))

    if alert_email:
        # Email for daily summaries
        router.add_channel(NotificationChannel(
            channel_id="email_daily_summary",
            name="Email - Daily Summary",
            channel_type=ChannelType.EMAIL,
            target=alert_email,
            enabled=True,
            severity_filter="low",
            description="Daily email digest of all error activity",
        ))

        # Email for critical alerts (backup to Discord)
        router.add_channel(NotificationChannel(
            channel_id="email_critical_backup",
            name="Email - Critical Backup",
            channel_type=ChannelType.EMAIL,
            target=alert_email,
            enabled=True,
            severity_filter="critical",
            description="Backup email notifications for critical errors",
        ))

    if not discord_url and not alert_email:
        logger.warning(
            "No notification channels configured. "
            "Set DISCORD_WEBHOOK_URL or ALERT_EMAIL in .env"
        )

    return router
