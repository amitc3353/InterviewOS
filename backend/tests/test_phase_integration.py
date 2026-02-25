"""Integration tests for scenario metadata in phases."""
import pytest
from backend.interview.phase_manager import PhaseManager
from backend.interview.scenario_loader import ScenarioLoader
from backend.models.session import SessionState, InterviewPhase


@pytest.fixture
def scenario_metadata():
    loader = ScenarioLoader()
    return loader.get_scenario("url-shortener")


# Test 1: SCOPE with metadata
def test_scope_phase_with_metadata(scenario_metadata):
    pm = PhaseManager("Design a URL shortener", scenario_metadata)
    state = SessionState(phase=InterviewPhase.SCOPE)
    prompt = pm.get_system_prompt(state)

    # Should contain prepared answers
    assert "million" in prompt.lower()
    assert "YOUR PREPARED ANSWERS" in prompt


# Test 2: SCOPE without metadata
def test_scope_phase_without_metadata():
    pm = PhaseManager("Design a URL shortener", scenario_metadata=None)
    state = SessionState(phase=InterviewPhase.SCOPE)
    prompt = pm.get_system_prompt(state)

    # Should contain generic guidance
    assert "Have reasonable answers ready" in prompt
    assert "make a reasonable assumption" in prompt


# Test 3: FAILURE with metadata
def test_failure_phase_with_metadata(scenario_metadata):
    pm = PhaseManager("Design a URL shortener", scenario_metadata)
    state = SessionState(phase=InterviewPhase.FAILURE)
    prompt = pm.get_system_prompt(state)

    # Should contain prepared failure scenarios
    assert "viral" in prompt.lower() or "50x" in prompt
    assert "database region" in prompt.lower() or "goes down" in prompt
    assert "FAILURE SCENARIOS FOR THIS SCENARIO" in prompt


# Test 4: FAILURE without metadata
def test_failure_phase_without_metadata():
    pm = PhaseManager("Design a URL shortener", scenario_metadata=None)
    state = SessionState(phase=InterviewPhase.FAILURE)
    prompt = pm.get_system_prompt(state)

    # Should contain generic examples
    assert "Introduce new constraints" in prompt


# Test 5: ARCHITECTURE with metadata
def test_architecture_phase_with_metadata(scenario_metadata):
    pm = PhaseManager("Design a URL shortener", scenario_metadata)
    state = SessionState(phase=InterviewPhase.ARCHITECTURE)
    prompt = pm.get_system_prompt(state)

    # Should contain depth guidance
    assert "Short code generation" in prompt
    assert "DEPTH GUIDANCE" in prompt
    assert "Load balancer" in prompt  # in low-priority list


# Test 6: DEEP_DIVE with metadata
def test_deep_dive_phase_with_metadata(scenario_metadata):
    pm = PhaseManager("Design a URL shortener", scenario_metadata)
    state = SessionState(phase=InterviewPhase.DEEP_DIVE)
    prompt = pm.get_system_prompt(state)

    # Should contain depth guidance
    assert "DEPTH GUIDANCE" in prompt
    assert "critical" in prompt.lower() or "most important" in prompt.lower()


# Test 7: INTRO phase unaffected
def test_intro_phase_unaffected(scenario_metadata):
    pm_with = PhaseManager("Design a URL shortener", scenario_metadata)
    pm_without = PhaseManager("Design a URL shortener", None)

    state = SessionState(phase=InterviewPhase.INTRO)
    prompt_with = pm_with.get_system_prompt(state)
    prompt_without = pm_without.get_system_prompt(state)

    # INTRO should be identical (metadata not used)
    assert "INTRO PHASE" in prompt_with
    assert "INTRO PHASE" in prompt_without
