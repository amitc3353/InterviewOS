"""Tests for GlitchTip dashboard configuration — 15 tests, zero network calls."""

import pytest

from backend.monitoring.dashboard import (
    DashboardConfig,
    DashboardPanel,
    PanelFilter,
    PanelType,
    get_default_dashboard,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_panel(panel_id: str = "test_panel", **kwargs) -> DashboardPanel:
    """Build a minimal DashboardPanel for testing."""
    defaults = {
        "panel_id": panel_id,
        "title": "Test Panel",
        "panel_type": PanelType.ERROR_COUNT,
        "description": "Test panel description",
    }
    defaults.update(kwargs)
    return DashboardPanel(**defaults)


def _make_dashboard(**kwargs) -> DashboardConfig:
    """Build a minimal DashboardConfig for testing."""
    defaults = {
        "name": "Test Dashboard",
        "description": "Test dashboard description",
    }
    defaults.update(kwargs)
    return DashboardConfig(**defaults)


# ---------------------------------------------------------------------------
# Tests: PanelFilter
# ---------------------------------------------------------------------------

def test_panel_filter_to_query_with_environment():
    """PanelFilter generates correct query string for environment."""
    f = PanelFilter(environment="production")
    assert f.to_query() == "environment:production"


def test_panel_filter_to_query_with_tag():
    """PanelFilter generates correct query string for tag filter."""
    f = PanelFilter(tag_key="phase", tag_value="architecture")
    assert f.to_query() == "phase:architecture"


def test_panel_filter_to_query_with_error_level():
    """PanelFilter generates correct query string for error level."""
    f = PanelFilter(error_level="fatal")
    assert f.to_query() == "level:fatal"


def test_panel_filter_to_query_combined():
    """PanelFilter combines multiple filters in query string."""
    f = PanelFilter(environment="staging", tag_key="phase", tag_value="intro", error_level="error")
    query = f.to_query()
    assert "environment:staging" in query
    assert "phase:intro" in query
    assert "level:error" in query


def test_panel_filter_empty_returns_empty_string():
    """PanelFilter with no criteria returns empty string."""
    f = PanelFilter()
    assert f.to_query() == ""


# ---------------------------------------------------------------------------
# Tests: DashboardPanel
# ---------------------------------------------------------------------------

def test_panel_to_dict():
    """DashboardPanel serializes correctly to dictionary."""
    panel = _make_panel(time_range="1h", position=(2, 1))
    result = panel.to_dict()

    assert result["id"] == "test_panel"
    assert result["title"] == "Test Panel"
    assert result["type"] == "error_count"
    assert result["time_range"] == "1h"
    assert result["position"] == {"row": 2, "col": 1}


def test_panel_to_dict_includes_filters():
    """DashboardPanel includes filter query strings in serialization."""
    panel = _make_panel(filters=[PanelFilter(environment="production")])
    result = panel.to_dict()

    assert result["filters"] == ["environment:production"]


# ---------------------------------------------------------------------------
# Tests: DashboardConfig
# ---------------------------------------------------------------------------

def test_dashboard_add_panel():
    """DashboardConfig.add_panel adds a panel."""
    dashboard = _make_dashboard()
    panel = _make_panel()
    dashboard.add_panel(panel)

    assert len(dashboard.panels) == 1
    assert dashboard.panels[0].panel_id == "test_panel"


def test_dashboard_add_panel_rejects_duplicate_id():
    """DashboardConfig.add_panel raises ValueError on duplicate panel ID."""
    dashboard = _make_dashboard()
    dashboard.add_panel(_make_panel("panel_1"))

    with pytest.raises(ValueError, match="already exists"):
        dashboard.add_panel(_make_panel("panel_1"))


def test_dashboard_remove_panel():
    """DashboardConfig.remove_panel removes panel and returns True."""
    dashboard = _make_dashboard()
    dashboard.add_panel(_make_panel("panel_1"))

    assert dashboard.remove_panel("panel_1") is True
    assert len(dashboard.panels) == 0


def test_dashboard_remove_nonexistent_panel():
    """DashboardConfig.remove_panel returns False for missing panel."""
    dashboard = _make_dashboard()
    assert dashboard.remove_panel("nonexistent") is False


def test_dashboard_get_panel():
    """DashboardConfig.get_panel returns panel by ID."""
    dashboard = _make_dashboard()
    dashboard.add_panel(_make_panel("panel_1", title="My Panel"))

    panel = dashboard.get_panel("panel_1")
    assert panel is not None
    assert panel.title == "My Panel"


def test_dashboard_get_panel_returns_none_for_missing():
    """DashboardConfig.get_panel returns None for missing ID."""
    dashboard = _make_dashboard()
    assert dashboard.get_panel("nonexistent") is None


def test_dashboard_validate_valid():
    """DashboardConfig.validate returns empty list for valid dashboard."""
    dashboard = _make_dashboard()
    dashboard.add_panel(_make_panel())

    errors = dashboard.validate()
    assert errors == []


def test_dashboard_validate_empty_name():
    """DashboardConfig.validate catches empty dashboard name."""
    dashboard = _make_dashboard(name="")
    dashboard.add_panel(_make_panel())

    errors = dashboard.validate()
    assert any("name is required" in e for e in errors)


def test_dashboard_validate_no_panels():
    """DashboardConfig.validate catches dashboard with no panels."""
    dashboard = _make_dashboard()

    errors = dashboard.validate()
    assert any("at least one panel" in e for e in errors)


def test_dashboard_validate_low_refresh_interval():
    """DashboardConfig.validate catches refresh interval below 10 seconds."""
    dashboard = _make_dashboard(refresh_interval_seconds=5)
    dashboard.add_panel(_make_panel())

    errors = dashboard.validate()
    assert any("at least 10 seconds" in e for e in errors)


def test_dashboard_to_dict():
    """DashboardConfig.to_dict serializes full dashboard."""
    dashboard = _make_dashboard()
    dashboard.add_panel(_make_panel("p1"))
    dashboard.add_panel(_make_panel("p2"))

    result = dashboard.to_dict()
    assert result["name"] == "Test Dashboard"
    assert result["environment"] == "production"
    assert len(result["panels"]) == 2


# ---------------------------------------------------------------------------
# Tests: get_default_dashboard()
# ---------------------------------------------------------------------------

def test_get_default_dashboard_has_panels():
    """Default dashboard has at least 6 panels."""
    dashboard = get_default_dashboard()
    assert len(dashboard.panels) >= 6


def test_get_default_dashboard_validates():
    """Default dashboard passes validation."""
    dashboard = get_default_dashboard()
    errors = dashboard.validate()
    assert errors == []


def test_get_default_dashboard_uses_environment():
    """Default dashboard uses provided environment."""
    dashboard = get_default_dashboard(environment="staging")
    assert dashboard.environment == "staging"


def test_get_default_dashboard_has_expected_panels():
    """Default dashboard includes key monitoring panels."""
    dashboard = get_default_dashboard()
    panel_ids = {p.panel_id for p in dashboard.panels}

    assert "error_count_total" in panel_ids
    assert "error_rate_per_minute" in panel_ids
    assert "errors_by_phase" in panel_ids
    assert "top_unresolved_issues" in panel_ids
    assert "critical_errors" in panel_ids
