"""Scorecard data models for post-interview evaluation."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List


SCORE_LABELS = {
    1: "Critical Gap",
    2: "Developing",
    3: "Solid",
    4: "Strong",
    5: "Exceptional",
}

DIMENSION_WEIGHTS = {
    "requirements_gathering":  0.15,
    "system_architecture":     0.25,
    "technical_depth":         0.25,
    "scalability_reliability": 0.25,
    "communication":           0.10,
}


@dataclass
class DimensionScore:
    """Score for a single evaluation dimension."""
    dimension: str
    score: int          # 1-5
    label: str          # derived from SCORE_LABELS
    rationale: str      # 2-3 sentences citing specific transcript evidence
    strengths: List[str]  # 1-3 bullets
    gaps: List[str]       # 1-3 bullets

    def to_dict(self) -> Dict:
        return {
            "dimension": self.dimension,
            "score": self.score,
            "label": self.label,
            "rationale": self.rationale,
            "strengths": self.strengths,
            "gaps": self.gaps,
        }


@dataclass
class InterviewScorecard:
    """Complete post-interview scorecard."""
    session_id: str
    scenario: str
    dimensions: Dict[str, DimensionScore]
    overall_score: float      # weighted average, 1 decimal
    hire_signal: str          # "Strong Yes" / "Lean Yes" / "Lean No" / "No"
    narrative: str            # 2-3 sentence summary
    locked_constraints: Dict[str, str]
    total_turns: int
    elapsed_minutes: float
    generated_at: str         # ISO timestamp

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "scenario": self.scenario,
            "dimensions": {k: v.to_dict() for k, v in self.dimensions.items()},
            "overall_score": self.overall_score,
            "hire_signal": self.hire_signal,
            "narrative": self.narrative,
            "locked_constraints": self.locked_constraints,
            "total_turns": self.total_turns,
            "elapsed_minutes": self.elapsed_minutes,
            "generated_at": self.generated_at,
        }


def compute_hire_signal(overall_score: float) -> str:
    """Map weighted average score to hire signal."""
    if overall_score >= 4.0:
        return "Strong Yes"
    if overall_score >= 3.5:
        return "Lean Yes"
    if overall_score >= 2.5:
        return "Lean No"
    return "No"
