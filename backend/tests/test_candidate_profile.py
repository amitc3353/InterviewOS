"""Tests for CandidateProfile data models — 15 tests, zero network calls."""

import pytest

from backend.models.candidate_profile import (
    CandidatePersona,
    CandidateProfile,
    CommunicationStyle,
    DEFAULT_DIMENSION_SKILLS,
    ResponseConfig,
    SKILL_LEVEL_SCORE_RANGES,
    SKILL_LEVEL_TEMPERATURES,
    SkillLevel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_persona(
    name: str = "Test Candidate",
    communication_style: CommunicationStyle = CommunicationStyle.STRUCTURED,
) -> CandidatePersona:
    """Build a minimal CandidatePersona for testing."""
    return CandidatePersona(
        name=name,
        background="software engineer at a tech company",
        years_of_experience=5,
        communication_style=communication_style,
        strengths=["backend development"],
        weaknesses=["frontend"],
    )


def _make_profile(
    skill_level: SkillLevel = SkillLevel.MID,
    dimension_skills: dict = None,
    scenario_id: str = "url-shortener",
) -> CandidateProfile:
    """Build a minimal CandidateProfile for testing."""
    return CandidateProfile(
        persona=_make_persona(),
        overall_skill_level=skill_level,
        dimension_skills=dimension_skills or {},
        scenario_id=scenario_id,
    )


# ---------------------------------------------------------------------------
# Tests — SkillLevel Enum
# ---------------------------------------------------------------------------

def test_skill_level_values():
    """All five skill levels have correct string values."""
    assert SkillLevel.NOVICE.value == "novice"
    assert SkillLevel.JUNIOR.value == "junior"
    assert SkillLevel.MID.value == "mid"
    assert SkillLevel.SENIOR.value == "senior"
    assert SkillLevel.STAFF.value == "staff"


def test_skill_level_score_ranges_cover_all_levels():
    """Every SkillLevel has a defined score range."""
    for level in SkillLevel:
        assert level in SKILL_LEVEL_SCORE_RANGES
        min_score, max_score = SKILL_LEVEL_SCORE_RANGES[level]
        assert min_score < max_score
        assert min_score >= 1.0
        assert max_score <= 5.0


def test_skill_level_temperatures_cover_all_levels():
    """Every SkillLevel has a defined temperature."""
    for level in SkillLevel:
        assert level in SKILL_LEVEL_TEMPERATURES
        temp = SKILL_LEVEL_TEMPERATURES[level]
        assert 0.0 < temp <= 1.0


# ---------------------------------------------------------------------------
# Tests — CommunicationStyle Enum
# ---------------------------------------------------------------------------

def test_communication_style_values():
    """All four communication styles have correct string values."""
    assert CommunicationStyle.STRUCTURED.value == "structured"
    assert CommunicationStyle.VERBOSE.value == "verbose"
    assert CommunicationStyle.CONCISE.value == "concise"
    assert CommunicationStyle.RAMBLING.value == "rambling"


# ---------------------------------------------------------------------------
# Tests — CandidatePersona
# ---------------------------------------------------------------------------

def test_persona_creation():
    """CandidatePersona stores all fields correctly."""
    persona = _make_persona(name="Alex Chen")
    assert persona.name == "Alex Chen"
    assert persona.years_of_experience == 5
    assert persona.communication_style == CommunicationStyle.STRUCTURED


def test_persona_to_dict():
    """CandidatePersona serializes all fields to dictionary."""
    persona = _make_persona(name="Jordan Lee")
    result = persona.to_dict()

    assert result["name"] == "Jordan Lee"
    assert result["communication_style"] == "structured"
    assert isinstance(result["strengths"], list)
    assert isinstance(result["weaknesses"], list)


def test_persona_default_lists():
    """CandidatePersona defaults strengths and weaknesses to empty lists."""
    persona = CandidatePersona(
        name="Minimal",
        background="engineer",
        years_of_experience=3,
    )
    assert persona.strengths == []
    assert persona.weaknesses == []


# ---------------------------------------------------------------------------
# Tests — ResponseConfig
# ---------------------------------------------------------------------------

def test_response_config_defaults():
    """ResponseConfig has sensible defaults."""
    config = ResponseConfig()
    assert config.max_response_tokens == 512
    assert config.temperature is None
    assert config.include_filler_words is False
    assert config.ask_clarifying_questions is True
    assert config.volunteer_information is True


def test_response_config_get_temperature_explicit():
    """Explicit temperature overrides skill-level default."""
    config = ResponseConfig(temperature=0.9)
    assert config.get_temperature(SkillLevel.STAFF) == 0.9


def test_response_config_get_temperature_from_skill_level():
    """Without explicit temperature, derives from skill level."""
    config = ResponseConfig()
    assert config.get_temperature(SkillLevel.STAFF) == SKILL_LEVEL_TEMPERATURES[SkillLevel.STAFF]
    assert config.get_temperature(SkillLevel.NOVICE) == SKILL_LEVEL_TEMPERATURES[SkillLevel.NOVICE]


# ---------------------------------------------------------------------------
# Tests — CandidateProfile
# ---------------------------------------------------------------------------

def test_profile_fills_missing_dimension_skills():
    """CandidateProfile auto-fills missing dimension skills from overall level."""
    profile = _make_profile(skill_level=SkillLevel.SENIOR)

    for dim_key in DEFAULT_DIMENSION_SKILLS:
        assert dim_key in profile.dimension_skills
        assert profile.dimension_skills[dim_key] == SkillLevel.SENIOR


def test_profile_preserves_explicit_dimension_overrides():
    """Explicit per-dimension skills are preserved, not overwritten by overall level."""
    overrides = {"communication": SkillLevel.STAFF}
    profile = _make_profile(
        skill_level=SkillLevel.MID,
        dimension_skills=overrides,
    )

    assert profile.dimension_skills["communication"] == SkillLevel.STAFF
    assert profile.dimension_skills["system_architecture"] == SkillLevel.MID


def test_profile_get_target_score_range():
    """get_target_score_range returns range matching skill level."""
    profile = _make_profile(skill_level=SkillLevel.SENIOR)
    min_score, max_score = profile.get_target_score_range()
    assert min_score == 3.5
    assert max_score == 4.4


def test_profile_get_dimension_skill_with_fallback():
    """get_dimension_skill falls back to overall level for unknown dimensions."""
    profile = _make_profile(skill_level=SkillLevel.SENIOR)
    assert profile.get_dimension_skill("unknown_dimension") == SkillLevel.SENIOR


def test_profile_to_dict():
    """CandidateProfile serializes to dictionary with all fields."""
    profile = _make_profile(skill_level=SkillLevel.MID)
    result = profile.to_dict()

    assert result["overall_skill_level"] == "mid"
    assert result["scenario_id"] == "url-shortener"
    assert isinstance(result["dimension_skills"], dict)
    assert isinstance(result["target_score_range"], list)
    assert len(result["target_score_range"]) == 2
    assert "persona" in result
