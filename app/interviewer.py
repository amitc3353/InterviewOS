"""AI Interviewer using Claude (Anthropic API)."""

import json
from pathlib import Path
from anthropic import Anthropic
from app.config import Config

# Load interview platform context
CONTEXT_FILE = Config.PROJECT_ROOT / "INTERVIEW_PLATFORM_CONTEXT.md"
PLATFORM_CONTEXT = CONTEXT_FILE.read_text() if CONTEXT_FILE.exists() else ""


class InterviewSession:
    """Manages an interview session state and AI interviewer responses."""
    
    def __init__(self, scenario: str = "payments"):
        """
        Initialize interview session.
        
        Args:
            scenario: Interview scenario (payments, social_feed, etc.)
        """
        self.scenario = scenario
        self.turn_count = 0
        self.history = []
        self.current_phase = "requirements_gathering"
        
        if not Config.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set in .env")
        
        self.client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    
    def next_question(self, candidate_input: str) -> dict:
        """
        Get next interviewer question based on candidate's response.
        
        Args:
            candidate_input: Candidate's latest response
            
        Returns:
            dict with keys:
                - question: Next interviewer question
                - intent: What this question probes for
                - what_good_looks_like: Key points for strong answer
        """
        self.turn_count += 1
        
        # Build prompt
        system_prompt = f"""You are an expert technical interviewer conducting a system design interview.

{PLATFORM_CONTEXT}

Current scenario: {self.scenario}
Current phase: {self.current_phase}
Turn: {self.turn_count}

Your goal:
- Ask insightful follow-up questions
- Probe for depth without giving away answers
- Guide if stuck, but don't solve for them
- Be professional but conversational

Output format (JSON):
{{
  "question": "Your next question",
  "intent": "What you're probing for",
  "what_good_looks_like": "Key points a strong candidate would cover"
}}
"""
        
        user_message = f"Candidate's response:\n{candidate_input}\n\nWhat's your next question?"
        
        # Call Claude
        response = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        
        # Parse response
        try:
            result = json.loads(response.content[0].text)
        except json.JSONDecodeError:
            # Fallback if not valid JSON
            result = {
                "question": response.content[0].text,
                "intent": "Follow-up question",
                "what_good_looks_like": "Clear, structured thinking"
            }
        
        # Update history
        self.history.append({
            "turn": self.turn_count,
            "candidate": candidate_input,
            "interviewer": result
        })
        
        return result
    
    def start(self) -> dict:
        """Get opening question for the interview."""
        opening = {
            "payments": "Let's design a payment processing system. Where would you like to start?",
            "social_feed": "Today we'll design a social media feed. What's your approach?",
            "e_commerce": "Let's build an e-commerce platform. How do you want to begin?",
            "ride_sharing": "We're designing a ride-sharing system. Where should we start?",
            "video_streaming": "Let's design a video streaming platform. What's your first step?"
        }
        
        question = opening.get(self.scenario, "Let's design a system. Where would you like to start?")
        
        return {
            "question": question,
            "intent": "Establish starting point and gauge requirements gathering approach",
            "what_good_looks_like": "Candidate asks clarifying questions about scale, users, and key features"
        }
