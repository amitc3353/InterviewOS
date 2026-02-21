"""Core interview engine - session state machine."""

from .session import SessionState
from app.config import Config

# Load interview platform context
CONTEXT_FILE = Config.PROJECT_ROOT / "INTERVIEW_PLATFORM_CONTEXT.md"
PLATFORM_CONTEXT = CONTEXT_FILE.read_text() if CONTEXT_FILE.exists() else ""


class InterviewEngine:
    """
    Core interview state machine.

    Does NOT know about audio, microphone, or transport.
    Pure business logic: session state + turn management.
    """

    SCENARIOS = {
        "payments": "payment processing system",
        "social_feed": "social media feed",
        "e_commerce": "e-commerce platform",
        "ride_sharing": "ride-sharing system",
        "video_streaming": "video streaming platform",
    }

    def __init__(self):
        """Initialize engine (no session yet)."""
        self.session: SessionState = None

    def start(self, scenario: str = "payments") -> dict:
        """
        Start a new interview session.

        Args:
            scenario: Interview scenario (payments, social_feed, etc.)

        Returns:
            Opening question (structured with Interview Protocol)
        """
        if scenario not in self.SCENARIOS:
            raise ValueError(
                f"Unknown scenario: {scenario}. Choose from: {list(self.SCENARIOS.keys())}"
            )

        self.session = SessionState(scenario=scenario)
        self.session.current_phase = "intro"

        scenario_name = self.SCENARIOS[scenario]

        return {
            "phase": "intro",
            "interviewer_says": f"Hi! Today we're designing a {scenario_name}. We'll start with requirements, then architecture, dive deep on a component or two, and wrap with scaling. Sound good?",
            "question": "Where would you like to start?",
            "what_im_listening_for": "Does candidate ask clarifying questions or jump to solution?",
            "followup_if_vague": "What questions do you have about the system's scope or scale?",
        }

    def process_turn(self, transcript: str) -> dict:
        """
        Process a candidate's response and prepare context for LLM.

        Args:
            transcript: Candidate's spoken response

        Returns:
            Context dict for LLMAdapter (not the question itself)
        """
        if not self.session:
            raise RuntimeError("Session not started. Call start() first.")

        # Return context for LLM to generate next question
        return {
            "scenario": self.session.scenario,
            "turn_count": self.session.turn_count,
            "current_phase": self.session.current_phase,
            "candidate_transcript": transcript,
            "platform_context": PLATFORM_CONTEXT,
            "history": [
                {
                    "turn": t.turn_number,
                    "candidate": t.candidate_transcript,
                    "interviewer": t.interviewer_response.get("question", ""),
                }
                for t in self.session.turns[-3:]  # Last 3 turns for context
            ],
        }

    def record_turn(self, transcript: str, response: dict) -> None:
        """
        Record a completed turn in session history.

        Args:
            transcript: Candidate's response
            response: Interviewer's question (from LLM)
        """
        self.session.add_turn(transcript, response)

    def get_state(self) -> dict:
        """Get current session state."""
        if not self.session:
            return {"status": "not_started"}

        return {"status": "active", "session": self.session.to_dict()}
