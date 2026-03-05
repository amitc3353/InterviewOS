"""Alert rule definitions for InterviewOS error monitoring.

Defines severity-based alert rules with configurable thresholds,
time windows, and notification actions. Rules are designed for
GlitchTip/Sentry alert configuration.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class AlertSeverity(Enum):
    """Alert severity levels, ordered by urgency."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ActionType(Enum):
    """Types of alert notification actions."""

    DISCORD_WEBHOOK = "discord_webhook"
    EMAIL = "email"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"


@dataclass
class AlertCondition:
    """Condition that triggers an alert.

    Attributes:
        error_count: Number of errors required to trigger
        time_window_minutes: Time window in minutes for counting errors
        error_level: Minimum error level to count (error, fatal, etc.)
        environment: Environment filter (production, staging, etc.)
        tag_filters: Additional tag filters as key-value pairs
    """

    error_count: int
    time_window_minutes: int
    error_level: str = "error"
    environment: str = "production"
    tag_filters: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Serialize condition to dictionary."""
        result = {
            "error_count": self.error_count,
            "time_window_minutes": self.time_window_minutes,
            "error_level": self.error_level,
            "environment": self.environment,
        }
        if self.tag_filters:
            result["tag_filters"] = self.tag_filters
        return result

    def validate(self) -> List[str]:
        """Validate condition parameters. Returns list of error messages."""
        errors: List[str] = []
        if self.error_count < 1:
            errors.append("error_count must be at least 1")
        if self.time_window_minutes < 1:
            errors.append("time_window_minutes must be at least 1")
        valid_levels = {"debug", "info", "warning", "error", "fatal"}
        if self.error_level not in valid_levels:
            errors.append(f"error_level must be one of: {', '.join(sorted(valid_levels))}")
        return errors


@dataclass
class AlertAction:
    """Action to take when an alert triggers.

    Attributes:
        action_type: Type of notification to send
        target: Target URL, email, or identifier
        rate_limit_minutes: Minimum minutes between repeated notifications
    """

    action_type: ActionType
    target: str
    rate_limit_minutes: int = 10

    def to_dict(self) -> Dict:
        """Serialize action to dictionary."""
        return {
            "type": self.action_type.value,
            "target": self.target,
            "rate_limit_minutes": self.rate_limit_minutes,
        }

    def validate(self) -> List[str]:
        """Validate action parameters. Returns list of error messages."""
        errors: List[str] = []
        if not self.target:
            errors.append("Action target is required")
        if self.rate_limit_minutes < 1:
            errors.append("rate_limit_minutes must be at least 1")
        return errors


@dataclass
class AlertRule:
    """A complete alert rule with conditions and actions.

    Attributes:
        rule_id: Unique rule identifier
        name: Human-readable rule name
        description: Description of what this rule monitors
        severity: Alert severity level
        condition: Trigger condition
        actions: List of notification actions
        enabled: Whether the rule is active
    """

    rule_id: str
    name: str
    description: str
    severity: AlertSeverity
    condition: AlertCondition
    actions: List[AlertAction] = field(default_factory=list)
    enabled: bool = True

    def add_action(self, action: AlertAction) -> None:
        """Add a notification action to the rule."""
        self.actions.append(action)

    def to_dict(self) -> Dict:
        """Serialize full alert rule to dictionary."""
        return {
            "id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "condition": self.condition.to_dict(),
            "actions": [action.to_dict() for action in self.actions],
            "enabled": self.enabled,
        }

    def validate(self) -> List[str]:
        """Validate the complete alert rule. Returns list of error messages."""
        errors: List[str] = []

        if not self.rule_id:
            errors.append("Rule ID is required")
        if not self.name:
            errors.append("Rule name is required")
        if not self.actions:
            errors.append("At least one action is required")

        errors.extend(self.condition.validate())

        for i, action in enumerate(self.actions):
            action_errors = action.validate()
            for err in action_errors:
                errors.append(f"Action {i}: {err}")

        return errors


def get_default_alert_rules(
    discord_webhook_url: str = "",
    alert_email: str = "",
    environment: str = "production",
) -> List[AlertRule]:
    """Create default alert rules for InterviewOS monitoring.

    Args:
        discord_webhook_url: Discord webhook URL for notifications
        alert_email: Email address for alert notifications
        environment: Target environment

    Returns:
        List of pre-configured AlertRule instances
    """
    rules: List[AlertRule] = []

    # Rule 1: Critical - Service down / crash loop
    critical_rule = AlertRule(
        rule_id="critical_error_spike",
        name="Critical Error Spike",
        description="Fires when more than 10 errors occur in 2 minutes, indicating a possible service crash or outage",
        severity=AlertSeverity.CRITICAL,
        condition=AlertCondition(
            error_count=10,
            time_window_minutes=2,
            error_level="error",
            environment=environment,
        ),
    )
    if discord_webhook_url:
        critical_rule.add_action(AlertAction(
            action_type=ActionType.DISCORD_WEBHOOK,
            target=discord_webhook_url,
            rate_limit_minutes=5,
        ))
    if alert_email:
        critical_rule.add_action(AlertAction(
            action_type=ActionType.EMAIL,
            target=alert_email,
            rate_limit_minutes=5,
        ))
    rules.append(critical_rule)

    # Rule 2: High - Error rate elevated
    high_rule = AlertRule(
        rule_id="high_error_rate",
        name="High Error Rate",
        description="Fires when more than 5 errors occur in 5 minutes, indicating degraded service quality",
        severity=AlertSeverity.HIGH,
        condition=AlertCondition(
            error_count=5,
            time_window_minutes=5,
            error_level="error",
            environment=environment,
        ),
    )
    if discord_webhook_url:
        high_rule.add_action(AlertAction(
            action_type=ActionType.DISCORD_WEBHOOK,
            target=discord_webhook_url,
            rate_limit_minutes=10,
        ))
    rules.append(high_rule)

    # Rule 3: Medium - Sustained errors
    medium_rule = AlertRule(
        rule_id="sustained_errors",
        name="Sustained Error Pattern",
        description="Fires when more than 10 errors occur in 30 minutes, indicating a persistent issue",
        severity=AlertSeverity.MEDIUM,
        condition=AlertCondition(
            error_count=10,
            time_window_minutes=30,
            error_level="error",
            environment=environment,
        ),
    )
    if discord_webhook_url:
        medium_rule.add_action(AlertAction(
            action_type=ActionType.DISCORD_WEBHOOK,
            target=discord_webhook_url,
            rate_limit_minutes=30,
        ))
    rules.append(medium_rule)

    # Rule 4: Low - Daily error summary
    low_rule = AlertRule(
        rule_id="daily_error_threshold",
        name="Daily Error Threshold",
        description="Fires when more than 50 errors occur in 24 hours, for daily review",
        severity=AlertSeverity.LOW,
        condition=AlertCondition(
            error_count=50,
            time_window_minutes=1440,  # 24 hours
            error_level="error",
            environment=environment,
        ),
    )
    if alert_email:
        low_rule.add_action(AlertAction(
            action_type=ActionType.EMAIL,
            target=alert_email,
            rate_limit_minutes=1440,  # Once per day
        ))
    rules.append(low_rule)

    # Rule 5: Fatal errors - any fatal error gets immediate notification
    fatal_rule = AlertRule(
        rule_id="fatal_error_immediate",
        name="Fatal Error - Immediate",
        description="Fires immediately on any fatal error, indicating an unrecoverable failure",
        severity=AlertSeverity.CRITICAL,
        condition=AlertCondition(
            error_count=1,
            time_window_minutes=1,
            error_level="fatal",
            environment=environment,
        ),
    )
    if discord_webhook_url:
        fatal_rule.add_action(AlertAction(
            action_type=ActionType.DISCORD_WEBHOOK,
            target=discord_webhook_url,
            rate_limit_minutes=5,
        ))
    if alert_email:
        fatal_rule.add_action(AlertAction(
            action_type=ActionType.EMAIL,
            target=alert_email,
            rate_limit_minutes=5,
        ))
    rules.append(fatal_rule)

    # Rule 6: STT pipeline errors
    stt_rule = AlertRule(
        rule_id="stt_pipeline_errors",
        name="STT Pipeline Errors",
        description="Fires when speech-to-text errors exceed threshold, affecting interview transcription",
        severity=AlertSeverity.HIGH,
        condition=AlertCondition(
            error_count=3,
            time_window_minutes=5,
            error_level="error",
            environment=environment,
            tag_filters={"event_type": "stt_error"},
        ),
    )
    if discord_webhook_url:
        stt_rule.add_action(AlertAction(
            action_type=ActionType.DISCORD_WEBHOOK,
            target=discord_webhook_url,
            rate_limit_minutes=15,
        ))
    rules.append(stt_rule)

    # Rule 7: TTS pipeline errors
    tts_rule = AlertRule(
        rule_id="tts_pipeline_errors",
        name="TTS Pipeline Errors",
        description="Fires when text-to-speech errors exceed threshold, affecting interviewer voice output",
        severity=AlertSeverity.HIGH,
        condition=AlertCondition(
            error_count=3,
            time_window_minutes=5,
            error_level="error",
            environment=environment,
            tag_filters={"event_type": "tts_error"},
        ),
    )
    if discord_webhook_url:
        tts_rule.add_action(AlertAction(
            action_type=ActionType.DISCORD_WEBHOOK,
            target=discord_webhook_url,
            rate_limit_minutes=15,
        ))
    rules.append(tts_rule)

    # Rule 8: LLM timeout/errors
    llm_rule = AlertRule(
        rule_id="llm_errors",
        name="LLM API Errors",
        description="Fires when Claude API errors or timeouts exceed threshold",
        severity=AlertSeverity.HIGH,
        condition=AlertCondition(
            error_count=3,
            time_window_minutes=5,
            error_level="error",
            environment=environment,
            tag_filters={"event_type": "llm_error"},
        ),
    )
    if discord_webhook_url:
        llm_rule.add_action(AlertAction(
            action_type=ActionType.DISCORD_WEBHOOK,
            target=discord_webhook_url,
            rate_limit_minutes=10,
        ))
    rules.append(llm_rule)

    return rules
