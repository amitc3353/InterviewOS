"""Session state management."""

from dataclasses import dataclass, field
from typing import List
from datetime import datetime
from .locked_constraints import LockedConstraints


@dataclass
class Turn:
    """Single interview turn."""

    turn_number: int
    candidate_transcript: str
    interviewer_response: dict
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SessionState:
    """Interview session state."""

    scenario: str
    turn_count: int = 0
    current_phase: str = "intro"
    turns: List[Turn] = field(default_factory=list)
    locked_constraints: LockedConstraints = field(default_factory=LockedConstraints)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Phase progression order
    PHASE_ORDER = [
        "intro",
        "scope",
        "architecture",
        "deep_dive",
        "failure",
        "tradeoffs",
        "wrap",
    ]

    def add_turn(self, transcript: str, response: dict) -> None:
        """Add a turn to the session."""
        self.turn_count += 1
        turn = Turn(
            turn_number=self.turn_count,
            candidate_transcript=transcript,
            interviewer_response=response,
        )
        self.turns.append(turn)

        # Update locked constraints if LLM returned any
        if "update_locked_constraints" in response:
            for key, value in response["update_locked_constraints"].items():
                self.locked_constraints.lock(key, value)

        # Update phase if LLM progressed it
        if "phase" in response and response["phase"] != self.current_phase:
            new_phase = response["phase"]
            # Only allow forward progression (or same phase)
            if self._can_progress_to(new_phase):
                self.current_phase = new_phase

    def _can_progress_to(self, new_phase: str) -> bool:
        """Check if phase progression is valid (monotonic forward or same)."""
        if new_phase not in self.PHASE_ORDER:
            return False

        current_idx = self.PHASE_ORDER.index(self.current_phase)
        new_idx = self.PHASE_ORDER.index(new_phase)

        # Can stay in same phase or move forward, but not backward
        return new_idx >= current_idx

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "scenario": self.scenario,
            "turn_count": self.turn_count,
            "current_phase": self.current_phase,
            "started_at": self.started_at,
            "turns": [
                {
                    "turn_number": t.turn_number,
                    "candidate": t.candidate_transcript,
                    "interviewer": t.interviewer_response,
                    "timestamp": t.timestamp,
                }
                for t in self.turns
            ],
        }
