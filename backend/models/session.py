"""Interview session data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from backend.logging import get_logger

logger = get_logger(__name__)


class InterviewPhase(Enum):
    """Interview phases - MUST match INTERVIEWER_BEHAVIOR.md spec."""
    INTRO = "intro"
    SCOPE = "scope"
    ARCHITECTURE = "architecture"
    DEEP_DIVE = "deep_dive"
    FAILURE = "failure"
    TRADEOFFS = "tradeoffs"
    WRAP = "wrap"


# Phase order for monotonic enforcement
PHASE_ORDER = [
    InterviewPhase.INTRO,
    InterviewPhase.SCOPE,
    InterviewPhase.ARCHITECTURE,
    InterviewPhase.DEEP_DIVE,
    InterviewPhase.FAILURE,
    InterviewPhase.TRADEOFFS,
    InterviewPhase.WRAP,
]


@dataclass
class Message:
    """Conversation message."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SessionState:
    """Current session state."""
    session_id: str = ""  # Session identifier for logging
    phase: InterviewPhase = InterviewPhase.INTRO
    locked_constraints: Dict[str, str] = field(default_factory=dict)  # key-value pairs
    conversation_history: List[Message] = field(default_factory=list)
    phase_start_time: datetime = field(default_factory=datetime.now)
    session_start_time: datetime = field(default_factory=datetime.now)
    phase_turn_count: int = 0  # Turns in current phase
    total_turn_count: int = 0  # Total turns in session
    last_constraint_summary_turn: int = 0  # Track when we last summarized
    consecutive_silence_count: int = 0  # Track consecutive empty user turns
    
    def elapsed_seconds(self) -> float:
        """Total session elapsed time in seconds."""
        return (datetime.now() - self.session_start_time).total_seconds()
    
    def phase_elapsed_seconds(self) -> float:
        """Current phase elapsed time in seconds."""
        return (datetime.now() - self.phase_start_time).total_seconds()
    
    def add_message(self, role: str, content: str):
        """Add message to conversation history."""
        self.conversation_history.append(Message(role=role, content=content))
        
        # Increment turn count
        if role == "user":
            self.phase_turn_count += 1
            self.total_turn_count += 1
    
    def get_recent_history(self, window_size: int = 5) -> List[Message]:
        """Get last N messages for LLM context."""
        return self.conversation_history[-window_size:]
    
    def advance_phase(self, new_phase: InterviewPhase) -> bool:
        """
        Advance to next phase with monotonic enforcement.

        Returns:
            True if phase changed, False if blocked
        """
        old_phase = self.phase
        current_idx = PHASE_ORDER.index(self.phase)
        try:
            new_idx = PHASE_ORDER.index(new_phase)
        except ValueError:
            # Invalid phase
            logger.warning(
                f"Invalid phase requested: {new_phase}",
                event_type="phase_invalid",
                session_id=self.session_id,
                turn_number=self.total_turn_count,
                current_phase=self.phase.value,
                requested_phase=str(new_phase)
            )
            return False

        # Monotonic forward only
        if new_idx <= current_idx:
            logger.warning(
                f"Phase transition blocked: {old_phase.value} -> {new_phase.value} (backward/same)",
                event_type="phase_blocked",
                session_id=self.session_id,
                turn_number=self.total_turn_count,
                current_phase=old_phase.value,
                requested_phase=new_phase.value,
                reason="monotonic_enforcement"
            )
            return False

        # Allow forward movement
        self.phase = new_phase
        self.phase_start_time = datetime.now()
        self.phase_turn_count = 0

        logger.info(
            f"Phase transition: {old_phase.value} -> {new_phase.value}",
            event_type="phase_transition",
            session_id=self.session_id,
            turn_number=self.total_turn_count,
            old_phase=old_phase.value,
            new_phase=new_phase.value,
            phase_elapsed_seconds=round((datetime.now() - self.phase_start_time).total_seconds(), 2)
        )
        return True
    
    def add_locked_constraint(self, key: str, value: str):
        """
        Add a locked constraint (key-value pair).

        If the key already exists, logs a warning with both old and new values
        and keeps the original value (does not overwrite).

        Args:
            key: Constraint key
            value: Constraint value
        """
        if key in self.locked_constraints:
            old_value = self.locked_constraints[key]
            logger.warning(
                f"Constraint conflict: key '{key}' already locked",
                event_type="constraint_conflict",
                session_id=self.session_id,
                turn_number=self.total_turn_count,
                constraint_key=key,
                existing_value=old_value,
                attempted_value=value,
                action="keeping_original"
            )
            return

        self.locked_constraints[key] = value
        logger.info(
            f"Constraint added: {key}={value}",
            event_type="constraint_added",
            session_id=self.session_id,
            turn_number=self.total_turn_count,
            constraint_key=key,
            constraint_value=value,
            total_constraints=len(self.locked_constraints)
        )

    def lock_constraint(self, key: str, value: str):
        """
        Legacy method for backward compatibility.

        Deprecated: Use add_locked_constraint() instead.
        """
        self.add_locked_constraint(key, value)
    
    def has_constraint_category(self, prefix: str) -> bool:
        """Check if any locked constraint key starts with the given prefix."""
        return any(key.startswith(prefix) for key in self.locked_constraints)


@dataclass
class InterviewSession:
    """Complete interview session data."""
    session_id: str
    scenario: str
    state: SessionState = field(default_factory=SessionState)
    transcript: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    scorecard: Optional[Dict] = None

    def to_dict(self) -> Dict:
        """Convert session to dictionary for storage."""
        return {
            "session_id": self.session_id,
            "scenario": self.scenario,
            "phase": self.state.phase.value,
            "locked_constraints": self.state.locked_constraints,
            "conversation_history": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat()
                }
                for msg in self.state.conversation_history
            ],
            "transcript": self.transcript,
            "metadata": self.metadata,
            "scorecard": self.scorecard,
            "session_start_time": self.state.session_start_time.isoformat(),
            "elapsed_seconds": self.state.elapsed_seconds(),
            "total_turns": self.state.total_turn_count
        }
