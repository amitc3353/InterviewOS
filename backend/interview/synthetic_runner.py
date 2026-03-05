"""Orchestrates synthetic interview sessions using existing engine components."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.structured_logging import get_logger
from backend.models.candidate_profile import CandidateProfile, SkillLevel
from backend.models.session import InterviewPhase, InterviewSession, SessionState

from .synthetic_candidate import SyntheticCandidateGenerator

logger = get_logger(__name__)

# Maximum turns per phase to prevent infinite loops
DEFAULT_MAX_TURNS_PER_PHASE: Dict[InterviewPhase, int] = {
    InterviewPhase.INTRO: 2,
    InterviewPhase.SCOPE: 8,
    InterviewPhase.ARCHITECTURE: 10,
    InterviewPhase.DEEP_DIVE: 8,
    InterviewPhase.FAILURE: 8,
    InterviewPhase.TRADEOFFS: 6,
    InterviewPhase.WRAP: 2,
}

# Phase progression order
_PHASE_ORDER = [
    InterviewPhase.INTRO,
    InterviewPhase.SCOPE,
    InterviewPhase.ARCHITECTURE,
    InterviewPhase.DEEP_DIVE,
    InterviewPhase.FAILURE,
    InterviewPhase.TRADEOFFS,
    InterviewPhase.WRAP,
]


@dataclass
class TurnResult:
    """Result of a single interviewer↔candidate exchange."""
    turn_number: int
    phase: str
    interviewer_message: str
    candidate_response: str

    def to_dict(self) -> Dict:
        """Serialize turn result to dictionary."""
        return {
            "turn_number": self.turn_number,
            "phase": self.phase,
            "interviewer_message": self.interviewer_message,
            "candidate_response": self.candidate_response,
        }


@dataclass
class InterviewRunResult:
    """Complete results from a synthetic interview run."""
    session: InterviewSession
    profile: CandidateProfile
    turns: List[TurnResult] = field(default_factory=list)
    phases_completed: List[str] = field(default_factory=list)
    total_turns: int = 0
    completed: bool = False

    def to_dict(self) -> Dict:
        """Serialize run result to dictionary."""
        return {
            "session": self.session.to_dict(),
            "profile": self.profile.to_dict(),
            "turns": [t.to_dict() for t in self.turns],
            "phases_completed": self.phases_completed,
            "total_turns": self.total_turns,
            "completed": self.completed,
        }

    def get_transcript(self) -> str:
        """Format the full conversation as a readable transcript."""
        lines = []
        for turn in self.turns:
            lines.append(f"[INTERVIEWER] ({turn.phase}): {turn.interviewer_message}")
            lines.append(f"[CANDIDATE]: {turn.candidate_response}")
            lines.append("")
        return "\n".join(lines)


class SyntheticInterviewRunner:
    """
    Orchestrates a synthetic interview by coordinating existing components.

    Manages the interview loop: for each turn, it records the interviewer message,
    generates a candidate response using SyntheticCandidateGenerator, and tracks
    phase progression through SessionState.
    """

    def __init__(
        self,
        profile: CandidateProfile,
        session_id: str = "synthetic-001",
        max_turns_per_phase: Optional[Dict[InterviewPhase, int]] = None,
    ) -> None:
        self._profile = profile
        self._generator = SyntheticCandidateGenerator()
        self._session = InterviewSession(
            session_id=session_id,
            scenario=profile.scenario_id,
        )
        self._max_turns = max_turns_per_phase or DEFAULT_MAX_TURNS_PER_PHASE
        self._turns: List[TurnResult] = []
        self._phases_completed: List[str] = []
        self._current_phase_idx = 0

        logger.info(
            f"Initialized synthetic runner: {profile.persona.name}",
            event_type="synthetic_runner_init",
            session_id=session_id,
            skill_level=profile.overall_skill_level.value,
            scenario_id=profile.scenario_id,
        )

    @property
    def session(self) -> InterviewSession:
        """Access the underlying interview session."""
        return self._session

    @property
    def current_phase(self) -> InterviewPhase:
        """Current interview phase."""
        return self._session.state.phase

    @property
    def total_turns(self) -> int:
        """Total turns completed so far."""
        return self._session.state.total_turn_count

    def get_candidate_prompt(self) -> str:
        """
        Build the LLM system prompt for the current phase.

        Returns:
            System prompt string for generating candidate responses.
        """
        return self._generator.build_candidate_prompt(
            profile=self._profile,
            phase=self._session.state.phase.value,
            scenario_description=self._profile.scenario_id,
        )

    def record_turn(
        self,
        interviewer_message: str,
        candidate_response: str,
    ) -> TurnResult:
        """
        Record a single interviewer↔candidate exchange.

        Args:
            interviewer_message: What the interviewer said.
            candidate_response: What the candidate replied.

        Returns:
            TurnResult with turn metadata.
        """
        state = self._session.state
        phase_value = state.phase.value

        # Record messages in session state
        state.add_message("assistant", interviewer_message)
        state.add_message("user", candidate_response)

        turn = TurnResult(
            turn_number=state.total_turn_count,
            phase=phase_value,
            interviewer_message=interviewer_message,
            candidate_response=candidate_response,
        )
        self._turns.append(turn)

        logger.debug(
            f"Turn {state.total_turn_count} recorded in {phase_value}",
            event_type="synthetic_turn_recorded",
            session_id=self._session.session_id,
            turn_number=state.total_turn_count,
            phase=phase_value,
        )

        return turn

    def should_advance_phase(self) -> bool:
        """
        Check if the current phase has reached its turn limit.

        Returns:
            True if the phase should advance to the next one.
        """
        current_phase = self._session.state.phase
        max_turns = self._max_turns.get(current_phase, 5)
        return self._session.state.phase_turn_count >= max_turns

    def advance_to_next_phase(self) -> bool:
        """
        Advance to the next phase in the interview sequence.

        Returns:
            True if successfully advanced, False if already at WRAP or blocked.
        """
        if self._current_phase_idx >= len(_PHASE_ORDER) - 1:
            return False

        current_phase = _PHASE_ORDER[self._current_phase_idx]
        self._phases_completed.append(current_phase.value)

        self._current_phase_idx += 1
        next_phase = _PHASE_ORDER[self._current_phase_idx]

        success = self._session.state.advance_phase(next_phase)
        if success:
            logger.info(
                f"Synthetic interview advanced to {next_phase.value}",
                event_type="synthetic_phase_advance",
                session_id=self._session.session_id,
                new_phase=next_phase.value,
                phases_completed=len(self._phases_completed),
            )
        return success

    def get_results(self) -> InterviewRunResult:
        """
        Return the complete interview results.

        Returns:
            InterviewRunResult with session data, turns, and completion status.
        """
        is_completed = (
            self._session.state.phase == InterviewPhase.WRAP
            or InterviewPhase.WRAP.value in self._phases_completed
        )

        return InterviewRunResult(
            session=self._session,
            profile=self._profile,
            turns=list(self._turns),
            phases_completed=list(self._phases_completed),
            total_turns=self._session.state.total_turn_count,
            completed=is_completed,
        )

    def get_phase_summary(self) -> Dict[str, int]:
        """Return a count of turns per phase."""
        summary: Dict[str, int] = {}
        for turn in self._turns:
            summary[turn.phase] = summary.get(turn.phase, 0) + 1
        return summary
