"""Load and manage interview scenarios from YAML files."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import yaml

from ..structured_logging import get_logger
from .input_validation import validate_path_within_directory, validate_scenario_id

logger = get_logger(__name__)


class ScenarioNotFoundError(Exception):
    """Raised when a scenario file is not found."""
    pass


@dataclass
class ScenarioMetadata:
    """Rich metadata parsed from YAML scenario files."""

    id: str
    name: str
    description: str
    archetype: str
    complexity_notes: str
    scope_answers: Dict[str, str]
    failure_scenarios: List[Dict[str, str]]
    critical_components: List[Dict[str, str]]
    low_priority_components: List[str]
    scoring_benchmarks: Dict[str, str]
    deep_dive_focus: List[Dict[str, str]]

    @classmethod
    def from_yaml(cls, path: Path) -> "ScenarioMetadata":
        """
        Parse YAML file into ScenarioMetadata.

        Args:
            path: Path to YAML file

        Returns:
            ScenarioMetadata instance

        Raises:
            ValueError: If required fields are missing
        """
        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        # Validate required fields
        required_fields = ["id", "name", "description"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field '{field}' in {path}")

        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            archetype=data.get("archetype", "general"),
            complexity_notes=data.get("complexity_notes", ""),
            scope_answers=data.get("scope_answers", {}),
            failure_scenarios=data.get("failure_scenarios", []),
            critical_components=data.get("critical_components", []),
            low_priority_components=data.get("low_priority_components", []),
            scoring_benchmarks=data.get("scoring_benchmarks", {}),
            deep_dive_focus=data.get("deep_dive_focus", []),
        )


class ScenarioLoader:
    """Load scenarios from YAML library."""

    DEFAULT_SCENARIO_ID = "url-shortener"

    def __init__(self, scenarios_dir: str | Path | None = None):
        """
        Initialize loader and load all scenarios.

        Args:
            scenarios_dir: Directory containing YAML files.
                           Defaults to INTERVIEW_SCENARIOS_DIR env var,
                           or backend/scenarios/ if not set.
        """
        if scenarios_dir is None:
            # Support env var for production deployments
            env_dir = os.getenv("INTERVIEW_SCENARIOS_DIR")
            if env_dir:
                scenarios_dir = Path(env_dir)
            else:
                # Default: backend/scenarios/ (relative to this file)
                base = Path(__file__).parent.parent
                scenarios_dir = base / "scenarios"

        self.scenarios_dir = Path(scenarios_dir)
        self._scenarios: Dict[str, ScenarioMetadata] = {}
        self._load_all_scenarios()

    def _load_all_scenarios(self) -> None:
        """Load all YAML files from scenarios directory."""
        if not self.scenarios_dir.exists():
            logger.warning(f"Scenarios directory not found: {self.scenarios_dir}")
            return

        for yaml_file in self.scenarios_dir.glob("*.yaml"):
            try:
                # Validate file is within the scenarios directory
                validate_path_within_directory(yaml_file, self.scenarios_dir)
                scenario = ScenarioMetadata.from_yaml(yaml_file)
                self._scenarios[scenario.id] = scenario
                logger.info(f"Loaded scenario: {scenario.id} ({scenario.name})")
            except Exception as e:
                logger.error(f"Failed to load {yaml_file}: {e}")
                # Skip invalid files, don't crash

    def get_scenario(self, scenario_id: str) -> ScenarioMetadata:
        """
        Load scenario by ID. Raises if not found.

        Args:
            scenario_id: Scenario ID (e.g., "url-shortener")

        Returns:
            ScenarioMetadata object

        Raises:
            ValueError: If no scenarios are loaded or scenario_id is invalid
            ScenarioNotFoundError: If scenario_id not found
        """
        # Validate scenario ID format to prevent injection/traversal
        scenario_id = validate_scenario_id(scenario_id)

        if not self._scenarios:
            raise ValueError("No scenarios loaded")

        if scenario_id not in self._scenarios:
            raise ScenarioNotFoundError(f"Unknown scenario: {scenario_id}")

        return self._scenarios[scenario_id]

    def list_available(self) -> List[Dict[str, str]]:
        """
        Return available scenarios for frontend display.

        Returns:
            List of dicts with id, name, archetype for each scenario
        """
        return [
            {
                "id": s.id,
                "name": s.name,
                "archetype": s.archetype
            }
            for s in self._scenarios.values()
        ]
