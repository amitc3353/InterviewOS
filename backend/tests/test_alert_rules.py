"""Tests for alert rule definitions — 18 tests, zero network calls."""

import pytest

from backend.monitoring.alert_rules import (
    ActionType,
    AlertAction,
    AlertCondition,
    AlertRule,
    AlertSeverity,
    get_default_alert_rules,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_condition(**kwargs) -> AlertCondition:
    """Build a minimal AlertCondition for testing."""
    defaults = {
        "error_count": 5,
        "time_window_minutes": 5,
    }
    defaults.update(kwargs)
    return AlertCondition(**defaults)


def _make_action(**kwargs) -> AlertAction:
    """Build a minimal AlertAction for testing."""
    defaults = {
        "action_type": ActionType.DISCORD_WEBHOOK,
        "target": "https://discord.com/api/webhooks/123/abc",
    }
    defaults.update(kwargs)
    return AlertAction(**defaults)


def _make_rule(**kwargs) -> AlertRule:
    """Build a minimal AlertRule for testing."""
    defaults = {
        "rule_id": "test_rule",
        "name": "Test Rule",
        "description": "Test rule description",
        "severity": AlertSeverity.HIGH,
        "condition": _make_condition(),
    }
    defaults.update(kwargs)
    return AlertRule(**defaults)


# ---------------------------------------------------------------------------
# Tests: AlertCondition
# ---------------------------------------------------------------------------

def test_condition_to_dict():
    """AlertCondition serializes correctly."""
    condition = _make_condition(error_count=10, time_window_minutes=2)
    result = condition.to_dict()

    assert result["error_count"] == 10
    assert result["time_window_minutes"] == 2
    assert result["error_level"] == "error"
    assert result["environment"] == "production"


def test_condition_to_dict_includes_tag_filters():
    """AlertCondition includes tag filters in serialization."""
    condition = _make_condition(tag_filters={"event_type": "stt_error"})
    result = condition.to_dict()

    assert result["tag_filters"] == {"event_type": "stt_error"}


def test_condition_validate_valid():
    """Valid condition passes validation."""
    condition = _make_condition()
    assert condition.validate() == []


def test_condition_validate_zero_error_count():
    """Condition validation catches zero error count."""
    condition = _make_condition(error_count=0)
    errors = condition.validate()
    assert any("error_count" in e for e in errors)


def test_condition_validate_zero_time_window():
    """Condition validation catches zero time window."""
    condition = _make_condition(time_window_minutes=0)
    errors = condition.validate()
    assert any("time_window_minutes" in e for e in errors)


def test_condition_validate_invalid_error_level():
    """Condition validation catches invalid error level."""
    condition = _make_condition(error_level="invalid")
    errors = condition.validate()
    assert any("error_level" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests: AlertAction
# ---------------------------------------------------------------------------

def test_action_to_dict():
    """AlertAction serializes correctly."""
    action = _make_action(rate_limit_minutes=15)
    result = action.to_dict()

    assert result["type"] == "discord_webhook"
    assert "discord.com" in result["target"]
    assert result["rate_limit_minutes"] == 15


def test_action_validate_valid():
    """Valid action passes validation."""
    action = _make_action()
    assert action.validate() == []


def test_action_validate_empty_target():
    """Action validation catches empty target."""
    action = _make_action(target="")
    errors = action.validate()
    assert any("target is required" in e for e in errors)


def test_action_validate_zero_rate_limit():
    """Action validation catches zero rate limit."""
    action = _make_action(rate_limit_minutes=0)
    errors = action.validate()
    assert any("rate_limit_minutes" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests: AlertRule
# ---------------------------------------------------------------------------

def test_rule_to_dict():
    """AlertRule serializes correctly."""
    rule = _make_rule()
    rule.add_action(_make_action())
    result = rule.to_dict()

    assert result["id"] == "test_rule"
    assert result["name"] == "Test Rule"
    assert result["severity"] == "high"
    assert result["enabled"] is True
    assert len(result["actions"]) == 1
    assert "condition" in result


def test_rule_add_action():
    """AlertRule.add_action adds action to rule."""
    rule = _make_rule()
    rule.add_action(_make_action())

    assert len(rule.actions) == 1


def test_rule_validate_valid():
    """Valid rule with action passes validation."""
    rule = _make_rule()
    rule.add_action(_make_action())
    assert rule.validate() == []


def test_rule_validate_missing_rule_id():
    """Rule validation catches empty rule ID."""
    rule = _make_rule(rule_id="")
    rule.add_action(_make_action())
    errors = rule.validate()
    assert any("Rule ID" in e for e in errors)


def test_rule_validate_no_actions():
    """Rule validation catches rule with no actions."""
    rule = _make_rule()
    errors = rule.validate()
    assert any("action" in e.lower() for e in errors)


def test_rule_validate_propagates_condition_errors():
    """Rule validation includes condition validation errors."""
    rule = _make_rule(condition=_make_condition(error_count=0))
    rule.add_action(_make_action())
    errors = rule.validate()
    assert any("error_count" in e for e in errors)


def test_rule_validate_propagates_action_errors():
    """Rule validation includes action validation errors."""
    rule = _make_rule()
    rule.add_action(_make_action(target=""))
    errors = rule.validate()
    assert any("Action 0" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests: get_default_alert_rules()
# ---------------------------------------------------------------------------

def test_default_rules_returns_rules():
    """Default rules returns non-empty list."""
    rules = get_default_alert_rules(
        discord_webhook_url="https://discord.com/api/webhooks/123/abc",
        alert_email="alerts@example.com",
    )
    assert len(rules) >= 5


def test_default_rules_with_discord_adds_discord_actions():
    """Default rules include Discord actions when URL provided."""
    rules = get_default_alert_rules(
        discord_webhook_url="https://discord.com/api/webhooks/123/abc",
    )

    discord_actions = []
    for rule in rules:
        for action in rule.actions:
            if action.action_type == ActionType.DISCORD_WEBHOOK:
                discord_actions.append(action)

    assert len(discord_actions) > 0


def test_default_rules_without_targets_have_no_actions():
    """Default rules without Discord/email have no actions."""
    rules = get_default_alert_rules()

    for rule in rules:
        assert len(rule.actions) == 0


def test_default_rules_include_critical_rule():
    """Default rules include a critical severity rule."""
    rules = get_default_alert_rules(
        discord_webhook_url="https://discord.com/api/webhooks/123/abc",
    )

    critical_rules = [r for r in rules if r.severity == AlertSeverity.CRITICAL]
    assert len(critical_rules) >= 1


def test_default_rules_include_pipeline_rules():
    """Default rules include STT, TTS, and LLM pipeline rules."""
    rules = get_default_alert_rules(
        discord_webhook_url="https://discord.com/api/webhooks/123/abc",
    )

    rule_ids = {r.rule_id for r in rules}
    assert "stt_pipeline_errors" in rule_ids
    assert "tts_pipeline_errors" in rule_ids
    assert "llm_errors" in rule_ids


def test_default_rules_use_environment():
    """Default rules use the provided environment."""
    rules = get_default_alert_rules(environment="staging")

    for rule in rules:
        assert rule.condition.environment == "staging"
