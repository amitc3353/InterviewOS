"""Pydantic models for API request/response validation."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from backend.interview.input_validation import (
    sanitize_candidate_name,
    sanitize_scenario_name,
)


class CreateSessionRequest(BaseModel):
    """Request body for creating a new interview session."""

    scenario: str = Field(
        ...,
        description="Interview scenario (e.g., 'Design a URL shortener')",
        min_length=1,
        max_length=200,
    )
    candidate_name: Optional[str] = Field(
        default=None,
        description="Optional candidate name for the session",
        max_length=100,
    )

    @field_validator("scenario")
    @classmethod
    def validate_scenario(cls, v: str) -> str:
        """Sanitize scenario name to prevent injection/traversal attacks."""
        return sanitize_scenario_name(v)

    @field_validator("candidate_name")
    @classmethod
    def validate_candidate_name(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize candidate name."""
        return sanitize_candidate_name(v)


class SessionResponse(BaseModel):
    """Response for a created or retrieved interview session."""

    session_id: str
    scenario: str
    phase: str
    locked_constraints: Dict[str, str]
    total_turns: int
    elapsed_seconds: float
    livekit_room_name: Optional[str] = None
    created_at: str


class SessionListResponse(BaseModel):
    """Response for listing sessions."""

    sessions: List[SessionResponse]
    total: int


class SessionStateResponse(BaseModel):
    """Response for current session state."""

    session_id: str
    phase: str
    locked_constraints: Dict[str, str]
    turn_count: int
    phase_turn_count: int
    elapsed_seconds: float
    conversation_history: List[Dict]


class TokenResponse(BaseModel):
    """Response for LiveKit participant token."""

    token: str
    room_name: str


class DimensionScoreResponse(BaseModel):
    """Score for a single evaluation dimension."""

    dimension: str
    score: int
    label: str
    rationale: str
    strengths: List[str]
    gaps: List[str]


class FeedbackResponse(BaseModel):
    """Response for session feedback/scorecard."""

    session_id: str
    scenario: str
    dimensions: Dict[str, DimensionScoreResponse]
    overall_score: float
    hire_signal: str
    narrative: str
    locked_constraints: Dict[str, str]
    total_turns: int
    elapsed_minutes: float
    generated_at: str


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
