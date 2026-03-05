"""Data models for synthetic candidate profiles."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class SkillLevel(Enum):
    """Candidate skill level, maps to expected scoring outcomes."""
    NOVICE = "novice"        # Expected score: 1.0–1.9
    JUNIOR = "junior"        # Expected score: 2.0–2.9
    MID = "mid"              # Expected score: 3.0–3.4
    SENIOR = "senior"        # Expected score: 3.5–4.4
    STAFF = "staff"          # Expected score: 4.5–5.0


class CommunicationStyle(Enum):
    """Controls how the synthetic candidate communicates."""
    STRUCTURED = "structured"  # Uses frameworks, numbered lists, clear signposting
    VERBOSE = "verbose"        # Over-explains, adds unnecessary detail
    CONCISE = "concise"        # Brief, direct answers
    RAMBLING = "rambling"      # Disorganized, jumps between topics


# Maps SkillLevel to expected overall score range (min, max)
SKILL_LEVEL_SCORE_RANGES: Dict[SkillLevel, Tuple[float, float]] = {
    SkillLevel.NOVICE: (1.0, 1.9),
    SkillLevel.JUNIOR: (2.0, 2.9),
    SkillLevel.MID: (3.0, 3.4),
    SkillLevel.SENIOR: (3.5, 4.4),
    SkillLevel.STAFF: (4.5, 5.0),
}

# Maps SkillLevel to LLM temperature for response generation
SKILL_LEVEL_TEMPERATURES: Dict[SkillLevel, float] = {
    SkillLevel.NOVICE: 0.8,
    SkillLevel.JUNIOR: 0.7,
    SkillLevel.MID: 0.5,
    SkillLevel.SENIOR: 0.3,
    SkillLevel.STAFF: 0.3,
}

# Default dimension skill levels when only an overall level is specified
DEFAULT_DIMENSION_SKILLS: Dict[str, SkillLevel] = {
    "requirements_gathering": SkillLevel.MID,
    "system_architecture": SkillLevel.MID,
    "technical_depth": SkillLevel.MID,
    "scalability_reliability": SkillLevel.MID,
    "communication": SkillLevel.MID,
}


@dataclass
class CandidatePersona:
    """Identity and behavioral traits for a synthetic candidate."""
    name: str
    background: str
    years_of_experience: int
    communication_style: CommunicationStyle = CommunicationStyle.STRUCTURED
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Serialize persona to dictionary."""
        return {
            "name": self.name,
            "background": self.background,
            "years_of_experience": self.years_of_experience,
            "communication_style": self.communication_style.value,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
        }


@dataclass
class ResponseConfig:
    """Controls response generation behavior."""
    max_response_tokens: int = 512
    temperature: Optional[float] = None  # If None, derived from skill level
    include_filler_words: bool = False    # "um", "uh" for realism
    ask_clarifying_questions: bool = True
    volunteer_information: bool = True    # Proactively share relevant details

    def get_temperature(self, skill_level: SkillLevel) -> float:
        """Return temperature, defaulting to skill-level-based value."""
        if self.temperature is not None:
            return self.temperature
        return SKILL_LEVEL_TEMPERATURES.get(skill_level, 0.5)


@dataclass
class CandidateProfile:
    """Complete synthetic candidate configuration for interview simulation."""
    persona: CandidatePersona
    overall_skill_level: SkillLevel
    dimension_skills: Dict[str, SkillLevel] = field(default_factory=dict)
    response_config: ResponseConfig = field(default_factory=ResponseConfig)
    scenario_id: str = "url-shortener"

    def __post_init__(self) -> None:
        """Fill missing dimension skills from overall level."""
        for dim_key in DEFAULT_DIMENSION_SKILLS:
            if dim_key not in self.dimension_skills:
                self.dimension_skills[dim_key] = self.overall_skill_level

    def get_target_score_range(self) -> Tuple[float, float]:
        """Return expected score range based on overall skill level."""
        return SKILL_LEVEL_SCORE_RANGES[self.overall_skill_level]

    def get_dimension_skill(self, dimension: str) -> SkillLevel:
        """Get skill level for a specific dimension, falling back to overall."""
        return self.dimension_skills.get(dimension, self.overall_skill_level)

    def to_dict(self) -> Dict:
        """Serialize profile to dictionary."""
        return {
            "persona": self.persona.to_dict(),
            "overall_skill_level": self.overall_skill_level.value,
            "dimension_skills": {
                k: v.value for k, v in self.dimension_skills.items()
            },
            "scenario_id": self.scenario_id,
            "target_score_range": list(self.get_target_score_range()),
        }
