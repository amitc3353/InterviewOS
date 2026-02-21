"""Core interview engine - session state machine."""

from typing import Dict
from pathlib import Path
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
        "payments": "Let's design a payment processing system. Where would you like to start?",
        "social_feed": "Today we'll design a social media feed. What's your approach?",
        "e_commerce": "Let's build an e-commerce platform. How do you want to begin?",
        "ride_sharing": "We're designing a ride-sharing system. Where should we start?",
        "video_streaming": "Let's design a video streaming platform. What's your first step?"
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
            Opening question (structured)
        """
        if scenario not in self.SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario}. Choose from: {list(self.SCENARIOS.keys())}")
        
        self.session = SessionState(scenario=scenario)
        
        opening_question = self.SCENARIOS[scenario]
        
        return {
            "question": opening_question,
            "intent": "Establish starting point and gauge requirements gathering approach",
            "what_good_looks_like": "Candidate asks clarifying questions about scale, users, and key features"
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
                    "interviewer": t.interviewer_response.get("question", "")
                }
                for t in self.session.turns[-3:]  # Last 3 turns for context
            ]
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
        
        return {
            "status": "active",
            "session": self.session.to_dict()
        }
