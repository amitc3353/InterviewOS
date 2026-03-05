"""Error monitoring dashboard, alert rules, and notification channels for InterviewOS."""

from .dashboard import (
    DashboardPanel,
    DashboardConfig,
    PanelType,
    get_default_dashboard,
)
from .alert_rules import (
    AlertRule,
    AlertSeverity,
    AlertCondition,
    AlertAction,
    get_default_alert_rules,
)
from .notification_channels import (
    NotificationChannel,
    ChannelType,
    NotificationRouter,
    get_default_channels,
)

__all__ = [
    "DashboardPanel",
    "DashboardConfig",
    "PanelType",
    "get_default_dashboard",
    "AlertRule",
    "AlertSeverity",
    "AlertCondition",
    "AlertAction",
    "get_default_alert_rules",
    "NotificationChannel",
    "ChannelType",
    "NotificationRouter",
    "get_default_channels",
]
