"""Generates synthetic candidate profiles and LLM prompts for interview simulation."""

from typing import Dict, List, Optional

from backend.logging import get_logger
from backend.models.candidate_profile import (
    CandidatePersona,
    CandidateProfile,
    CommunicationStyle,
    ResponseConfig,
    SkillLevel,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Skill-level prompt calibration
# ---------------------------------------------------------------------------

_SKILL_LEVEL_INSTRUCTIONS: Dict[SkillLevel, str] = {
    SkillLevel.NOVICE: (
        "You have almost no system design experience. You struggle with basic concepts "
        "like load balancing, caching, and database selection. When asked about scale, "
        "you give vague or incorrect answers. You cannot break a system into components "
        "without heavy prompting. You tend to jump to implementation without scoping."
    ),
    SkillLevel.JUNIOR: (
        "You have basic system design knowledge but lack depth. You know common components "
        "(load balancer, cache, database) but cannot justify your choices. When probed on "
        "details like sharding strategies or failure modes, you give surface-level answers. "
        "You need prompting to ask clarifying questions about requirements."
    ),
    SkillLevel.MID: (
        "You have solid system design fundamentals. You ask some clarifying questions about "
        "scale and requirements. You can design a reasonable architecture with standard "
        "components. When probed on technical depth, you can go one level deeper but may "
        "struggle with advanced topics like distributed consensus or cache stampede prevention. "
        "You handle 1-2 failure scenarios adequately but may miss edge cases."
    ),
    SkillLevel.SENIOR: (
        "You have strong system design skills. You proactively ask about scale, latency, "
        "consistency, and availability requirements. Your architecture is well-justified "
        "with clear component responsibilities. You can go deep on 2-3 critical components "
        "with implementation-level detail. You handle failure scenarios well with concrete "
        "fallback mechanisms. You articulate tradeoffs clearly."
    ),
    SkillLevel.STAFF: (
        "You are an exceptional system designer. You proactively scope requirements across "
        "5-6 dimensions with specific numbers. Your architecture is thorough with every "
        "component justified. You volunteer implementation details on critical paths — "
        "data models, algorithms, edge cases. You proactively raise failure modes before "
        "being asked. You use frameworks to structure your thinking and articulate tradeoffs "
        "with specificity. You precompute capacity math and address distributed system "
        "challenges like consensus, partition tolerance, and cache coherence."
    ),
}

_COMMUNICATION_STYLE_INSTRUCTIONS: Dict[CommunicationStyle, str] = {
    CommunicationStyle.STRUCTURED: (
        "Organize your responses with clear structure. Use numbered lists or frameworks "
        "like 'Let me break this into three parts.' Signpost transitions between topics. "
        "Be precise and avoid rambling."
    ),
    CommunicationStyle.VERBOSE: (
        "You tend to over-explain. Add extra context and qualifications to your answers. "
        "Sometimes repeat points in different ways. Your answers are longer than necessary "
        "but still technically sound for your skill level."
    ),
    CommunicationStyle.CONCISE: (
        "Give brief, direct answers. Don't elaborate unless specifically asked. "
        "Your responses are short — sometimes too short, requiring the interviewer "
        "to probe for more detail."
    ),
    CommunicationStyle.RAMBLING: (
        "Your answers are disorganized. Jump between topics without clear transitions. "
        "Start answering one question, then drift to a tangent. Eventually get to the "
        "point but make the interviewer work to follow your reasoning."
    ),
}

# ---------------------------------------------------------------------------
# Preset profiles for common testing scenarios
# ---------------------------------------------------------------------------

PRESET_PROFILES: Dict[str, Dict] = {
    "strong_hire": {
        "persona": {
            "name": "Priya Sharma",
            "background": "Staff engineer at a large-scale cloud infrastructure company",
            "years_of_experience": 12,
            "communication_style": CommunicationStyle.STRUCTURED,
            "strengths": ["distributed systems", "capacity planning", "failure analysis"],
            "weaknesses": ["frontend architecture", "mobile systems"],
        },
        "overall_skill_level": SkillLevel.STAFF,
    },
    "borderline": {
        "persona": {
            "name": "Jordan Lee",
            "background": "Senior engineer at a mid-size SaaS company",
            "years_of_experience": 6,
            "communication_style": CommunicationStyle.CONCISE,
            "strengths": ["database design", "API design"],
            "weaknesses": ["distributed consensus", "failure mode analysis"],
        },
        "overall_skill_level": SkillLevel.MID,
    },
    "weak_candidate": {
        "persona": {
            "name": "Sam Torres",
            "background": "Backend developer at a small startup",
            "years_of_experience": 3,
            "communication_style": CommunicationStyle.RAMBLING,
            "strengths": ["basic CRUD applications"],
            "weaknesses": [
                "system design",
                "scaling",
                "distributed systems",
                "failure analysis",
            ],
        },
        "overall_skill_level": SkillLevel.JUNIOR,
    },
    "silent_candidate": {
        "persona": {
            "name": "Casey Nguyen",
            "background": "Software engineer at a consulting firm",
            "years_of_experience": 5,
            "communication_style": CommunicationStyle.CONCISE,
            "strengths": ["backend development", "database design"],
            "weaknesses": ["verbal communication", "system design breadth"],
        },
        "overall_skill_level": SkillLevel.MID,
        "response_config": {
            "max_response_tokens": 128,
            "volunteer_information": False,
        },
    },
    "over_explainer": {
        "persona": {
            "name": "Morgan Patel",
            "background": "Senior platform engineer at a large e-commerce company",
            "years_of_experience": 9,
            "communication_style": CommunicationStyle.VERBOSE,
            "strengths": ["caching", "database optimization", "monitoring"],
            "weaknesses": ["staying on topic", "time management"],
        },
        "overall_skill_level": SkillLevel.SENIOR,
    },
}


class SyntheticCandidateGenerator:
    """Generates synthetic candidate profiles and LLM prompts for interview simulation."""

    def generate_profile(
        self,
        skill_level: SkillLevel,
        scenario_id: str = "url-shortener",
        communication_style: CommunicationStyle = CommunicationStyle.STRUCTURED,
        persona_name: Optional[str] = None,
    ) -> CandidateProfile:
        """
        Create a CandidateProfile with appropriate traits for the given skill level.

        Args:
            skill_level: Overall candidate skill level.
            scenario_id: Interview scenario identifier.
            communication_style: How the candidate communicates.
            persona_name: Optional custom name for the persona.

        Returns:
            A fully configured CandidateProfile.
        """
        persona = self._build_persona(skill_level, communication_style, persona_name)
        profile = CandidateProfile(
            persona=persona,
            overall_skill_level=skill_level,
            response_config=ResponseConfig(),
            scenario_id=scenario_id,
        )

        logger.info(
            f"Generated synthetic profile: {persona.name} ({skill_level.value})",
            event_type="synthetic_profile_generated",
            skill_level=skill_level.value,
            scenario_id=scenario_id,
            communication_style=communication_style.value,
        )

        return profile

    def generate_profile_from_preset(self, preset_name: str) -> CandidateProfile:
        """
        Create a CandidateProfile from a named preset.

        Args:
            preset_name: One of the PRESET_PROFILES keys.

        Returns:
            A CandidateProfile configured per the preset.

        Raises:
            ValueError: If preset_name is not recognized.
        """
        if preset_name not in PRESET_PROFILES:
            available = ", ".join(sorted(PRESET_PROFILES.keys()))
            raise ValueError(
                f"Unknown preset '{preset_name}'. Available: {available}"
            )

        preset = PRESET_PROFILES[preset_name]
        persona_data = preset["persona"]

        persona = CandidatePersona(
            name=persona_data["name"],
            background=persona_data["background"],
            years_of_experience=persona_data["years_of_experience"],
            communication_style=persona_data["communication_style"],
            strengths=persona_data.get("strengths", []),
            weaknesses=persona_data.get("weaknesses", []),
        )

        response_config = ResponseConfig()
        if "response_config" in preset:
            rc_data = preset["response_config"]
            response_config = ResponseConfig(
                max_response_tokens=rc_data.get(
                    "max_response_tokens", response_config.max_response_tokens
                ),
                volunteer_information=rc_data.get(
                    "volunteer_information", response_config.volunteer_information
                ),
            )

        profile = CandidateProfile(
            persona=persona,
            overall_skill_level=preset["overall_skill_level"],
            response_config=response_config,
            scenario_id="url-shortener",
        )

        logger.info(
            f"Generated profile from preset: {preset_name}",
            event_type="synthetic_preset_loaded",
            preset_name=preset_name,
            skill_level=preset["overall_skill_level"].value,
        )

        return profile

    def build_candidate_prompt(
        self,
        profile: CandidateProfile,
        phase: str,
        scenario_description: str = "",
    ) -> str:
        """
        Build a system prompt that instructs the LLM to roleplay as this candidate.

        Args:
            profile: The candidate profile to simulate.
            phase: Current interview phase (e.g., "scope", "architecture").
            scenario_description: The interview scenario description text.

        Returns:
            System prompt string for the LLM.
        """
        persona = profile.persona
        skill_level = profile.overall_skill_level

        # Core identity
        sections = [
            f"You are {persona.name}, a {persona.background} with "
            f"{persona.years_of_experience} years of experience.",
            f"You are in a Staff-level system design interview.",
        ]

        # Scenario context
        if scenario_description:
            sections.append(
                f"The interview scenario is: {scenario_description}"
            )

        # Skill calibration
        skill_instruction = _SKILL_LEVEL_INSTRUCTIONS.get(skill_level, "")
        if skill_instruction:
            sections.append(f"SKILL CALIBRATION:\n{skill_instruction}")

        # Per-dimension overrides
        dimension_overrides = self._build_dimension_overrides(profile)
        if dimension_overrides:
            sections.append(f"DIMENSION-SPECIFIC SKILLS:\n{dimension_overrides}")

        # Communication style
        comm_instruction = _COMMUNICATION_STYLE_INSTRUCTIONS.get(
            persona.communication_style, ""
        )
        if comm_instruction:
            sections.append(f"COMMUNICATION STYLE:\n{comm_instruction}")

        # Strengths and weaknesses
        if persona.strengths:
            sections.append(
                f"YOUR STRENGTHS (show depth here): {', '.join(persona.strengths)}"
            )
        if persona.weaknesses:
            sections.append(
                f"YOUR WEAKNESSES (struggle here): {', '.join(persona.weaknesses)}"
            )

        # Phase-specific behavior
        phase_instruction = self._get_phase_instruction(phase, skill_level)
        if phase_instruction:
            sections.append(f"CURRENT PHASE ({phase}):\n{phase_instruction}")

        # Response rules
        sections.append(self._get_response_rules(profile))

        return "\n\n".join(sections)

    def list_presets(self) -> List[Dict]:
        """Return available preset profiles with their metadata."""
        result = []
        for name, preset in PRESET_PROFILES.items():
            persona = preset["persona"]
            result.append({
                "name": name,
                "persona_name": persona["name"],
                "skill_level": preset["overall_skill_level"].value,
                "communication_style": persona["communication_style"].value,
            })
        return result

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _build_persona(
        self,
        skill_level: SkillLevel,
        communication_style: CommunicationStyle,
        persona_name: Optional[str],
    ) -> CandidatePersona:
        """Build a CandidatePersona appropriate for the skill level."""
        experience_ranges: Dict[SkillLevel, int] = {
            SkillLevel.NOVICE: 1,
            SkillLevel.JUNIOR: 3,
            SkillLevel.MID: 5,
            SkillLevel.SENIOR: 8,
            SkillLevel.STAFF: 12,
        }

        backgrounds: Dict[SkillLevel, str] = {
            SkillLevel.NOVICE: "junior developer at a small startup",
            SkillLevel.JUNIOR: "backend developer at a mid-size company",
            SkillLevel.MID: "software engineer at a tech company",
            SkillLevel.SENIOR: "senior engineer at a large tech company",
            SkillLevel.STAFF: "staff engineer at a cloud infrastructure company",
        }

        name = persona_name or f"Candidate ({skill_level.value})"

        return CandidatePersona(
            name=name,
            background=backgrounds.get(skill_level, "software engineer"),
            years_of_experience=experience_ranges.get(skill_level, 5),
            communication_style=communication_style,
            strengths=self._default_strengths(skill_level),
            weaknesses=self._default_weaknesses(skill_level),
        )

    def _default_strengths(self, skill_level: SkillLevel) -> List[str]:
        """Return default strengths for a skill level."""
        if skill_level in (SkillLevel.STAFF, SkillLevel.SENIOR):
            return ["distributed systems", "database design", "capacity planning"]
        if skill_level == SkillLevel.MID:
            return ["backend development", "SQL databases"]
        return ["basic programming"]

    def _default_weaknesses(self, skill_level: SkillLevel) -> List[str]:
        """Return default weaknesses for a skill level."""
        if skill_level == SkillLevel.STAFF:
            return ["mobile architecture"]
        if skill_level == SkillLevel.SENIOR:
            return ["cost optimization", "mobile systems"]
        if skill_level == SkillLevel.MID:
            return ["distributed consensus", "failure mode analysis"]
        return ["system design", "scaling", "distributed systems"]

    def _build_dimension_overrides(self, profile: CandidateProfile) -> str:
        """Build text describing per-dimension skill overrides."""
        lines = []
        for dim, level in profile.dimension_skills.items():
            if level != profile.overall_skill_level:
                display_dim = dim.replace("_", " ").title()
                lines.append(f"- {display_dim}: Perform at {level.value} level")
        return "\n".join(lines)

    def _get_phase_instruction(self, phase: str, skill_level: SkillLevel) -> str:
        """Return phase-specific behavior instructions for the candidate."""
        phase_behaviors: Dict[str, Dict[SkillLevel, str]] = {
            "intro": {
                SkillLevel.STAFF: "Briefly introduce yourself and your relevant experience.",
                SkillLevel.SENIOR: "Introduce yourself. Mention your background briefly.",
                SkillLevel.MID: "Introduce yourself. Keep it short.",
                SkillLevel.JUNIOR: "Introduce yourself nervously. Keep it very brief.",
                SkillLevel.NOVICE: "Struggle to introduce yourself clearly.",
            },
            "scope": {
                SkillLevel.STAFF: (
                    "Proactively ask about 5-6 requirements: scale, latency, consistency, "
                    "availability, R/W ratio, geography. Give specific numbers when answering."
                ),
                SkillLevel.SENIOR: (
                    "Ask about 3-4 key requirements. Be specific about scale and latency."
                ),
                SkillLevel.MID: (
                    "Ask about 2-3 requirements when prompted. May need nudging to be specific."
                ),
                SkillLevel.JUNIOR: (
                    "Ask 1-2 basic questions. Often accept vague answers without pushing back."
                ),
                SkillLevel.NOVICE: (
                    "Jump to design without asking clarifying questions. If prompted, "
                    "ask generic questions that don't help narrow scope."
                ),
            },
            "architecture": {
                SkillLevel.STAFF: (
                    "Present a clear, justified component breakdown. Explain why each component "
                    "exists and how they interact. Address bottlenecks proactively."
                ),
                SkillLevel.SENIOR: (
                    "Present a reasonable architecture with most components justified. "
                    "May leave 1 component vague."
                ),
                SkillLevel.MID: (
                    "Present basic architecture with standard components. Need prompting "
                    "to justify choices and explain interactions."
                ),
                SkillLevel.JUNIOR: (
                    "Present incomplete architecture. Miss important components. "
                    "Struggle to explain why you chose specific technologies."
                ),
                SkillLevel.NOVICE: (
                    "Cannot produce a coherent architecture without heavy guidance. "
                    "Name components without explaining their purpose or interactions."
                ),
            },
            "deep_dive": {
                SkillLevel.STAFF: (
                    "Provide implementation-level detail: data models, algorithms, "
                    "edge cases, capacity math. Volunteer tradeoffs."
                ),
                SkillLevel.SENIOR: (
                    "Go deep on 2 components with good detail. Handle probing well."
                ),
                SkillLevel.MID: (
                    "Can go one level deeper when probed. Struggle with advanced topics."
                ),
                SkillLevel.JUNIOR: (
                    "Stay high-level even when probed. Cannot produce implementation detail."
                ),
                SkillLevel.NOVICE: (
                    "Cannot respond to deep technical questions. Repeat high-level points."
                ),
            },
            "failure": {
                SkillLevel.STAFF: (
                    "Adapt design well. Propose specific fallback mechanisms with "
                    "concrete implementation details. Raise additional failure modes."
                ),
                SkillLevel.SENIOR: (
                    "Handle failure scenarios with solid responses. Propose fallbacks."
                ),
                SkillLevel.MID: (
                    "Address failure scenarios adequately with some gaps."
                ),
                SkillLevel.JUNIOR: (
                    "Struggle with failure scenarios. Give surface-level responses."
                ),
                SkillLevel.NOVICE: (
                    "Cannot adapt to introduced failures. Freeze or give irrelevant answers."
                ),
            },
            "tradeoffs": {
                SkillLevel.STAFF: (
                    "Articulate tradeoffs with specificity. Compare alternatives with "
                    "concrete metrics. Explain why you chose your approach."
                ),
                SkillLevel.SENIOR: (
                    "Discuss tradeoffs clearly. May miss some nuance."
                ),
                SkillLevel.MID: (
                    "Acknowledge tradeoffs exist but struggle to articulate specifics."
                ),
                SkillLevel.JUNIOR: (
                    "Barely aware of tradeoffs. Cannot explain alternatives."
                ),
                SkillLevel.NOVICE: (
                    "Do not understand the concept of design tradeoffs."
                ),
            },
            "wrap": {
                SkillLevel.STAFF: "Summarize your design concisely. Ask thoughtful questions.",
                SkillLevel.SENIOR: "Summarize key points. Ask a relevant question.",
                SkillLevel.MID: "Briefly summarize if prompted.",
                SkillLevel.JUNIOR: "Say thanks. Struggle to summarize.",
                SkillLevel.NOVICE: "Just say thanks.",
            },
        }

        phase_dict = phase_behaviors.get(phase, {})
        return phase_dict.get(skill_level, "")

    def _get_response_rules(self, profile: CandidateProfile) -> str:
        """Build response generation rules from profile configuration."""
        rules = [
            "RESPONSE RULES:",
            "- Respond ONLY as the candidate. Do not narrate or break character.",
            "- Do not mention that you are a synthetic or AI candidate.",
            "- Respond naturally as if speaking in a real interview.",
        ]

        config = profile.response_config
        if not config.volunteer_information:
            rules.append(
                "- Only answer what is directly asked. Do not volunteer extra information."
            )
        if config.include_filler_words:
            rules.append(
                "- Include occasional filler words like 'um', 'uh', 'so' for realism."
            )
        if not config.ask_clarifying_questions:
            rules.append(
                "- Do not ask clarifying questions. Just answer with what you know."
            )

        return "\n".join(rules)
