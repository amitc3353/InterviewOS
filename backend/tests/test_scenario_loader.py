"""Tests for ScenarioLoader — 10 tests."""
import pytest
from pathlib import Path
from backend.interview.scenario_loader import ScenarioLoader, ScenarioNotFoundError, ScenarioMetadata


# Test 1: Load existing scenario
def test_get_scenario_success():
    loader = ScenarioLoader()
    scenario = loader.get_scenario("url-shortener")
    assert scenario.id == "url-shortener"
    assert "URL" in scenario.name
    assert len(scenario.description) > 50


# Test 2: Metadata structure
def test_scenario_metadata_structure():
    loader = ScenarioLoader()
    scenario = loader.get_scenario("url-shortener")
    assert scenario.archetype in ["crud-metadata", "transactional", "feed-timeline", "platform-infra", "real-time-streaming"]
    assert isinstance(scenario.scope_answers, dict)
    assert isinstance(scenario.failure_scenarios, list)
    assert isinstance(scenario.critical_components, list)
    assert isinstance(scenario.scoring_benchmarks, dict)


# Test 3: Scenario not found
def test_scenario_not_found():
    loader = ScenarioLoader()
    with pytest.raises(ScenarioNotFoundError, match="Unknown scenario"):
        loader.get_scenario("nonexistent")


# Test 4: Empty directory
def test_empty_directory(tmp_path):
    empty_loader = ScenarioLoader(scenarios_dir=tmp_path)
    with pytest.raises(ValueError, match="No scenarios loaded"):
        empty_loader.get_scenario("url-shortener")


# Test 5: List available scenarios
def test_list_available():
    loader = ScenarioLoader()
    scenarios = loader.list_available()
    assert len(scenarios) == 6
    assert all("id" in s and "name" in s and "archetype" in s for s in scenarios)
    ids = [s["id"] for s in scenarios]
    assert "url-shortener" in ids
    assert "payment-gateway" in ids
    assert "ride-sharing" in ids


# Test 6: Scope answers exist
def test_scope_answers():
    loader = ScenarioLoader()
    scenario = loader.get_scenario("url-shortener")
    assert bool(scenario.scope_answers) is True
    assert len(scenario.scope_answers) > 0


# Test 7: Failure scenarios exist
def test_failure_scenarios():
    loader = ScenarioLoader()
    scenario = loader.get_scenario("url-shortener")
    assert bool(scenario.failure_scenarios) is True
    assert len(scenario.failure_scenarios) >= 2


# Test 8: Critical components exist
def test_critical_components():
    loader = ScenarioLoader()
    scenario = loader.get_scenario("url-shortener")
    assert len(scenario.critical_components) > 0
    assert all("name" in c and "why" in c for c in scenario.critical_components)


# Test 9: Scoring benchmarks exist
def test_scoring_benchmarks():
    loader = ScenarioLoader()
    scenario = loader.get_scenario("url-shortener")
    assert "exceptional" in scenario.scoring_benchmarks
    assert "solid" in scenario.scoring_benchmarks
    assert "weak" in scenario.scoring_benchmarks


# Test 10: Custom directory
def test_custom_directory(tmp_path):
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("""
id: test
name: Test Scenario
description: Test description
archetype: general
scope_answers:
  users: "1000"
failure_scenarios:
  - scenario: "Test failure"
    focus: "Test focus"
critical_components:
  - name: "Component A"
    why: "Reason A"
low_priority_components:
  - "Component B"
scoring_benchmarks:
  exceptional: "Great"
  solid: "Good"
  weak: "Poor"
""")

    loader = ScenarioLoader(scenarios_dir=tmp_path)
    assert len(loader._scenarios) == 1
    scenario = loader.get_scenario("test")
    assert scenario.name == "Test Scenario"
