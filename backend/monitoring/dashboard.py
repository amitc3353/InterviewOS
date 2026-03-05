"""GlitchTip dashboard configuration for InterviewOS error monitoring.

Defines dashboard panels, layout, and default configuration for monitoring
interview session errors, performance metrics, and system health.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class PanelType(Enum):
    """Dashboard panel visualization types."""

    ERROR_COUNT = "error_count"
    ERROR_RATE = "error_rate"
    ERROR_BREAKDOWN = "error_breakdown"
    TOP_ISSUES = "top_issues"
    RESPONSE_TIME = "response_time"
    SESSION_HEALTH = "session_health"


@dataclass
class PanelFilter:
    """Filter criteria for dashboard panels."""

    environment: Optional[str] = None
    tag_key: Optional[str] = None
    tag_value: Optional[str] = None
    error_level: Optional[str] = None

    def to_query(self) -> str:
        """Convert filter to GlitchTip/Sentry query string."""
        parts: List[str] = []
        if self.environment:
            parts.append(f"environment:{self.environment}")
        if self.tag_key and self.tag_value:
            parts.append(f"{self.tag_key}:{self.tag_value}")
        if self.error_level:
            parts.append(f"level:{self.error_level}")
        return " ".join(parts)


@dataclass
class DashboardPanel:
    """A single dashboard panel configuration.

    Attributes:
        panel_id: Unique identifier for the panel
        title: Display title
        panel_type: Type of visualization
        description: Human-readable description of what the panel shows
        time_range: Time range for data (e.g., '1h', '24h', '7d')
        filters: List of filter criteria
        position: Panel position as (row, column) tuple
    """

    panel_id: str
    title: str
    panel_type: PanelType
    description: str
    time_range: str = "24h"
    filters: List[PanelFilter] = field(default_factory=list)
    position: tuple = (0, 0)

    def to_dict(self) -> Dict:
        """Serialize panel configuration to dictionary."""
        return {
            "id": self.panel_id,
            "title": self.title,
            "type": self.panel_type.value,
            "description": self.description,
            "time_range": self.time_range,
            "filters": [f.to_query() for f in self.filters if f.to_query()],
            "position": {"row": self.position[0], "col": self.position[1]},
        }


@dataclass
class DashboardConfig:
    """Complete dashboard configuration.

    Attributes:
        name: Dashboard name
        description: Dashboard description
        panels: Ordered list of dashboard panels
        refresh_interval_seconds: Auto-refresh interval
        environment: Default environment filter
    """

    name: str
    description: str
    panels: List[DashboardPanel] = field(default_factory=list)
    refresh_interval_seconds: int = 60
    environment: str = "production"

    def add_panel(self, panel: DashboardPanel) -> None:
        """Add a panel to the dashboard."""
        # Check for duplicate panel IDs
        existing_ids = {p.panel_id for p in self.panels}
        if panel.panel_id in existing_ids:
            raise ValueError(f"Panel ID '{panel.panel_id}' already exists in dashboard")
        self.panels.append(panel)

    def remove_panel(self, panel_id: str) -> bool:
        """Remove a panel by ID. Returns True if removed, False if not found."""
        for i, panel in enumerate(self.panels):
            if panel.panel_id == panel_id:
                self.panels.pop(i)
                return True
        return False

    def get_panel(self, panel_id: str) -> Optional[DashboardPanel]:
        """Get a panel by ID."""
        for panel in self.panels:
            if panel.panel_id == panel_id:
                return panel
        return None

    def to_dict(self) -> Dict:
        """Serialize full dashboard configuration to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "refresh_interval_seconds": self.refresh_interval_seconds,
            "environment": self.environment,
            "panels": [panel.to_dict() for panel in self.panels],
        }

    def validate(self) -> List[str]:
        """Validate dashboard configuration. Returns list of error messages."""
        errors: List[str] = []

        if not self.name:
            errors.append("Dashboard name is required")

        if not self.panels:
            errors.append("Dashboard must have at least one panel")

        if self.refresh_interval_seconds < 10:
            errors.append("Refresh interval must be at least 10 seconds")

        # Check for duplicate panel IDs
        panel_ids = [p.panel_id for p in self.panels]
        duplicates = set(pid for pid in panel_ids if panel_ids.count(pid) > 1)
        if duplicates:
            errors.append(f"Duplicate panel IDs: {', '.join(duplicates)}")

        return errors


def get_default_dashboard(environment: str = "production") -> DashboardConfig:
    """Create the default InterviewOS error monitoring dashboard.

    Args:
        environment: Target environment for dashboard filters

    Returns:
        Pre-configured DashboardConfig with standard monitoring panels
    """
    env_filter = PanelFilter(environment=environment)

    dashboard = DashboardConfig(
        name="InterviewOS Error Monitor",
        description="Real-time error monitoring for interview sessions",
        environment=environment,
        refresh_interval_seconds=60,
    )

    # Row 1: Overview panels
    dashboard.add_panel(DashboardPanel(
        panel_id="error_count_total",
        title="Total Errors (24h)",
        panel_type=PanelType.ERROR_COUNT,
        description="Total error count across all sessions in the last 24 hours",
        time_range="24h",
        filters=[env_filter],
        position=(0, 0),
    ))

    dashboard.add_panel(DashboardPanel(
        panel_id="error_rate_per_minute",
        title="Error Rate (per minute)",
        panel_type=PanelType.ERROR_RATE,
        description="Errors per minute over time, indicating spike patterns",
        time_range="1h",
        filters=[env_filter],
        position=(0, 1),
    ))

    # Row 2: Breakdown panels
    dashboard.add_panel(DashboardPanel(
        panel_id="errors_by_phase",
        title="Errors by Interview Phase",
        panel_type=PanelType.ERROR_BREAKDOWN,
        description="Error distribution across interview phases (intro, scope, architecture, etc.)",
        time_range="24h",
        filters=[env_filter, PanelFilter(tag_key="phase", tag_value="*")],
        position=(1, 0),
    ))

    dashboard.add_panel(DashboardPanel(
        panel_id="errors_by_component",
        title="Errors by Component",
        panel_type=PanelType.ERROR_BREAKDOWN,
        description="Error distribution by component (STT, LLM, TTS, VAD)",
        time_range="24h",
        filters=[env_filter],
        position=(1, 1),
    ))

    # Row 3: Top issues and session health
    dashboard.add_panel(DashboardPanel(
        panel_id="top_unresolved_issues",
        title="Top Unresolved Issues",
        panel_type=PanelType.TOP_ISSUES,
        description="Most frequent unresolved errors requiring attention",
        time_range="7d",
        filters=[env_filter],
        position=(2, 0),
    ))

    dashboard.add_panel(DashboardPanel(
        panel_id="session_error_health",
        title="Session Health",
        panel_type=PanelType.SESSION_HEALTH,
        description="Percentage of sessions completing without errors",
        time_range="24h",
        filters=[env_filter],
        position=(2, 1),
    ))

    # Row 4: Critical errors and response times
    dashboard.add_panel(DashboardPanel(
        panel_id="critical_errors",
        title="Critical Errors",
        panel_type=PanelType.ERROR_COUNT,
        description="Fatal and critical errors requiring immediate attention",
        time_range="24h",
        filters=[env_filter, PanelFilter(error_level="fatal")],
        position=(3, 0),
    ))

    dashboard.add_panel(DashboardPanel(
        panel_id="llm_response_time",
        title="LLM Response Time",
        panel_type=PanelType.RESPONSE_TIME,
        description="Claude API response latency distribution",
        time_range="1h",
        filters=[env_filter],
        position=(3, 1),
    ))

    return dashboard
