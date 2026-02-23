"""Interview session data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class InterviewPhase(Enum):
    """Interview phases."""
    INTRO = "intro"
    EXPLORATION = "exploration"
    CONSTRAINTS = "constraints"
    DEPTH = "depth"
    CLOSING = "closing"


@dataclass
class Message:
    """Conversation message."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SessionState:
    """Current session state."""
    phase: InterviewPhase = InterviewPhase.INTRO
    locked_constraints: List[str] = field(default_factory=list)
    conversation_history: List[Message] = field(default_factory=list)
    phase_start_time: datetime = field(default_factory=datetime.now)
    session_start_time: datetime = field(default_factory=datetime.now)
    
    def elapsed_seconds(self) -> float:
        """Total session elapsed time in seconds."""
        return (datetime.now() - self.session_start_time).total_seconds()
    
    def phase_elapsed_seconds(self) -> float:
        """Current phase elapsed time in seconds."""
        return (datetime.now() - self.phase_start_time).total_seconds()
    
    def add_message(self, role: str, content: str):
        """Add message to conversation history."""
        self.conversation_history.append(Message(role=role, content=content))
    
    def advance_phase(self, new_phase: InterviewPhase):
        """Advance to next phase."""
        self.phase = new_phase
        self.phase_start_time = datetime.now()


@dataclass
class InterviewSession:
    """Complete interview session data."""
    session_id: str
    scenario: str
    state: SessionState = field(default_factory=SessionState)
    transcript: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    
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
            "session_start_time": self.state.session_start_time.isoformat(),
            "elapsed_seconds": self.state.elapsed_seconds()
        }
