"""Tests for SyntheticCandidateGenerator — 14 tests, zero network calls."""

import pytest
from unittest.mock import patch, MagicMock

from backend.interview.synthetic_candidate import (
    PRESET_PROFILES,
    SyntheticCandidateGenerator,
    _SKILL_LEVEL_INSTRUCTIONS,
    _COMMUNICATION_STYLE_INSTRUCTIONS,
)
from backend.models.candidate_profile import (
    CandidatePersona,
    CandidateProfile,
    CommunicationStyle,
    ResponseConfig,
    SkillLevel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_generator() -> SyntheticCandidateGenerator:
    """Build a SyntheticCandidateGenerator for testing."""
    return SyntheticCandidateGenerator()


def _make_persona(
    name: str = "Test Candidate",
    communication_style: CommunicationStyle = CommunicationStyle.STRUCTURED,
) -> CandidatePersona:
    """Build a minimal CandidatePersona for testing."""
    return CandidatePersona(
        name=name,
        background="software engineer",
        years_of_experience=5,
        communication_style=communication_style,
        strengths=["backend"],
        weaknesses=["frontend"],
    )


def _make_profile(
    skill_level: SkillLevel = SkillLevel.MID,
    communication_style: CommunicationStyle = CommunicationStyle.STRUCTURED,
) -> CandidateProfile:
    """Build a minimal CandidateProfile for testing."""
    return CandidateProfile(
        persona=_make_persona(communication_style=communication_style),
        overall_skill_level=skill_level,
    )


# ---------------------------------------------------------------------------
# Tests — generate_profile
# ---------------------------------------------------------------------------

def test_generate_profile_returns_candidate_profile():
    """generate_profile returns a properly typed CandidateProfile."""
    gen = _make_generator()
    profile = gen.generate_profile(SkillLevel.SENIOR)

    assert isinstance(profile, CandidateProfile)
    assert profile.overall_skill_level == SkillLevel.SENIOR
    assert profile.scenario_id == "url-shortener"


def test_generate_profile_custom_scenario():
    """generate_profile accepts custom scenario_id."""
    gen = _make_generator()
    profile = gen.generate_profile(SkillLevel.MID, scenario_id="payment-gateway")

    assert profile.scenario_id == "payment-gateway"


def test_generate_profile_custom_name():
    """generate_profile uses custom persona name when provided."""
    gen = _make_generator()
    profile = gen.generate_profile(SkillLevel.STAFF, persona_name="Alice Smith")

    assert profile.persona.name == "Alice Smith"


def test_generate_profile_default_name_includes_skill_level():
    """Default persona name includes the skill level for identification."""
    gen = _make_generator()
    profile = gen.generate_profile(SkillLevel.JUNIOR)

    assert "junior" in profile.persona.name.lower()


def test_generate_profile_sets_communication_style():
    """generate_profile respects the communication_style parameter."""
    gen = _make_generator()
    profile = gen.generate_profile(
        SkillLevel.MID,
        communication_style=CommunicationStyle.VERBOSE,
    )

    assert profile.persona.communication_style == CommunicationStyle.VERBOSE


def test_generate_profile_fills_dimension_skills():
    """Generated profile has all five dimensions populated."""
    gen = _make_generator()
    profile = gen.generate_profile(SkillLevel.SENIOR)

    expected_dims = {
        "requirements_gathering",
        "system_architecture",
        "technical_depth",
        "scalability_reliability",
        "communication",
    }
    assert set(profile.dimension_skills.keys()) == expected_dims


# ---------------------------------------------------------------------------
# Tests — generate_profile_from_preset
# ---------------------------------------------------------------------------

def test_generate_profile_from_preset_strong_hire():
    """strong_hire preset produces a STAFF-level profile."""
    gen = _make_generator()
    profile = gen.generate_profile_from_preset("strong_hire")

    assert profile.overall_skill_level == SkillLevel.STAFF
    assert profile.persona.name == "Priya Sharma"
    assert profile.persona.communication_style == CommunicationStyle.STRUCTURED


def test_generate_profile_from_preset_weak_candidate():
    """weak_candidate preset produces a JUNIOR-level profile."""
    gen = _make_generator()
    profile = gen.generate_profile_from_preset("weak_candidate")

    assert profile.overall_skill_level == SkillLevel.JUNIOR
    assert profile.persona.communication_style == CommunicationStyle.RAMBLING


def test_generate_profile_from_preset_silent_candidate():
    """silent_candidate preset has reduced response tokens and no volunteering."""
    gen = _make_generator()
    profile = gen.generate_profile_from_preset("silent_candidate")

    assert profile.response_config.max_response_tokens == 128
    assert profile.response_config.volunteer_information is False


def test_generate_profile_from_preset_unknown_raises():
    """Unknown preset raises ValueError with available presets listed."""
    gen = _make_generator()

    with pytest.raises(ValueError, match="Unknown preset"):
        gen.generate_profile_from_preset("nonexistent_preset")


# ---------------------------------------------------------------------------
# Tests — build_candidate_prompt
# ---------------------------------------------------------------------------

def test_build_candidate_prompt_includes_persona_name():
    """Candidate prompt includes the persona's name."""
    gen = _make_generator()
    profile = _make_profile()
    profile.persona.name = "Alex Chen"

    prompt = gen.build_candidate_prompt(profile, phase="scope")

    assert "Alex Chen" in prompt


def test_build_candidate_prompt_includes_skill_calibration():
    """Candidate prompt includes skill-level-appropriate calibration."""
    gen = _make_generator()

    for level in SkillLevel:
        profile = _make_profile(skill_level=level)
        prompt = gen.build_candidate_prompt(profile, phase="architecture")
        assert "SKILL CALIBRATION" in prompt


def test_build_candidate_prompt_includes_communication_style():
    """Candidate prompt includes communication style instructions."""
    gen = _make_generator()
    profile = _make_profile(communication_style=CommunicationStyle.VERBOSE)

    prompt = gen.build_candidate_prompt(profile, phase="scope")

    assert "COMMUNICATION STYLE" in prompt
    assert "over-explain" in prompt


def test_build_candidate_prompt_includes_response_rules():
    """Candidate prompt includes response generation rules."""
    gen = _make_generator()
    profile = _make_profile()

    prompt = gen.build_candidate_prompt(profile, phase="architecture")

    assert "RESPONSE RULES" in prompt
    assert "Do not narrate" in prompt


# ---------------------------------------------------------------------------
# Tests — list_presets
# ---------------------------------------------------------------------------

def test_list_presets_returns_all_presets():
    """list_presets returns metadata for all defined presets."""
    gen = _make_generator()
    presets = gen.list_presets()

    assert len(presets) == len(PRESET_PROFILES)

    preset_names = {p["name"] for p in presets}
    assert "strong_hire" in preset_names
    assert "borderline" in preset_names
    assert "weak_candidate" in preset_names


# ---------------------------------------------------------------------------
# Tests — Skill level instructions coverage
# ---------------------------------------------------------------------------

def test_skill_level_instructions_cover_all_levels():
    """Every SkillLevel has a defined instruction string."""
    for level in SkillLevel:
        assert level in _SKILL_LEVEL_INSTRUCTIONS
        assert len(_SKILL_LEVEL_INSTRUCTIONS[level]) > 20


def test_communication_style_instructions_cover_all_styles():
    """Every CommunicationStyle has a defined instruction string."""
    for style in CommunicationStyle:
        assert style in _COMMUNICATION_STYLE_INSTRUCTIONS
        assert len(_COMMUNICATION_STYLE_INSTRUCTIONS[style]) > 20
