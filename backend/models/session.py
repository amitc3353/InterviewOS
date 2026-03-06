"""Interview session data models."""

import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from backend.structured_logging import get_logger

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
            logger.debug(
                f"User turn {self.total_turn_count} in {self.phase.value} phase",
                event_type="turn_start",
                session_id=self.session_id,
                turn_number=self.total_turn_count,
                phase=self.phase.value,
                phase_turn_count=self.phase_turn_count,
                message_length=len(content)
            )
        else:
            logger.debug(
                f"Assistant response in {self.phase.value} phase",
                event_type="assistant_response",
                session_id=self.session_id,
                turn_number=self.total_turn_count,
                phase=self.phase.value,
                message_length=len(content)
            )

        # Log memory profile every 10 messages to monitor session growth
        if len(self.conversation_history) % 10 == 0:
            self.log_memory_profile()
    
    def get_recent_history(self, window_size: int = 5) -> List[Message]:
        """Get last N messages for LLM context."""
        return self.conversation_history[-window_size:]

    def get_memory_stats(self) -> Dict:
        """
        Calculate memory usage stats for the conversation history.

        Returns:
            Dict with message_count, total_chars, estimated_bytes, and avg_message_chars.
        """
        message_count = len(self.conversation_history)
        total_chars = sum(len(msg.content) for msg in self.conversation_history)
        # Rough estimate: each char ~= 1 byte in ASCII, ~4 bytes per char in Python str
        estimated_bytes = sum(sys.getsizeof(msg.content) for msg in self.conversation_history)
        avg_chars = total_chars / message_count if message_count > 0 else 0

        return {
            "message_count": message_count,
            "total_chars": total_chars,
            "estimated_bytes": estimated_bytes,
            "avg_message_chars": round(avg_chars, 1),
        }

    def log_memory_profile(self) -> None:
        """Log conversation history memory stats for monitoring session growth."""
        stats = self.get_memory_stats()
        estimated_mb = stats["estimated_bytes"] / (1024 * 1024)

        # Log at appropriate level based on memory usage
        if estimated_mb > 50:
            logger.warning(
                f"High memory usage: conversation history at {estimated_mb:.1f}MB "
                f"({stats['message_count']} messages, {stats['total_chars']} chars)",
                event_type="memory_profile",
                session_id=self.session_id,
                turn_number=self.total_turn_count,
                message_count=stats["message_count"],
                total_chars=stats["total_chars"],
                estimated_bytes=stats["estimated_bytes"],
                estimated_mb=round(estimated_mb, 2),
                avg_message_chars=stats["avg_message_chars"],
                level="warning",
            )
        else:
            logger.debug(
                f"Memory profile: {stats['message_count']} messages, "
                f"{stats['total_chars']} chars, ~{estimated_mb:.2f}MB",
                event_type="memory_profile",
                session_id=self.session_id,
                turn_number=self.total_turn_count,
                message_count=stats["message_count"],
                total_chars=stats["total_chars"],
                estimated_bytes=stats["estimated_bytes"],
                estimated_mb=round(estimated_mb, 2),
                avg_message_chars=stats["avg_message_chars"],
            )
    
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
                f"Invalid phase transition attempted: {old_phase.value} → {new_phase}",
                event_type="phase_invalid",
                session_id=self.session_id,
                turn_number=self.total_turn_count,
                current_phase=old_phase.value,
                requested_phase=str(new_phase),
                reason="invalid_phase"
            )
            return False

        # Monotonic forward only
        if new_idx <= current_idx:
            logger.warning(
                f"Phase transition blocked: {old_phase.value} → {new_phase.value}",
                event_type="phase_blocked",
                session_id=self.session_id,
                turn_number=self.total_turn_count,
                current_phase=old_phase.value,
                requested_phase=new_phase.value,
                reason="monotonic_enforcement"
            )
            return False

        # Allow forward movement
        phase_elapsed = self.phase_elapsed_seconds()
        old_phase_turn_count = self.phase_turn_count
        self.phase = new_phase
        self.phase_start_time = datetime.now()
        self.phase_turn_count = 0

        logger.info(
            f"Phase transition: {old_phase.value} → {new_phase.value}",
            event_type="phase_transition",
            session_id=self.session_id,
            turn_number=self.total_turn_count,
            old_phase=old_phase.value,
            new_phase=new_phase.value,
            phase_elapsed_seconds=phase_elapsed,
            phase_turn_count=old_phase_turn_count,
            constraint_count=len(self.locked_constraints)
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
                f"Constraint key '{key}' already exists. "
                f"Keeping original value '{old_value}', ignoring new value '{value}'",
                event_type="constraint_conflict",
                session_id=self.session_id,
                turn_number=self.total_turn_count,
                phase=self.phase.value,
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
            phase=self.phase.value,
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

    def __post_init__(self):
        """Initialize SessionState with session_id after dataclass creation."""
        if not self.state.session_id:
            self.state.session_id = self.session_id

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
