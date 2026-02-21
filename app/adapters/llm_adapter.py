"""LLM Adapter - Generate interviewer responses via Claude."""

import json
from anthropic import Anthropic
from app.config import Config


class LLMAdapter:
    """
    LLM adapter for interviewer response generation.
    
    Interface for transport layer - abstracts LLM implementation.
    """
    
    def __init__(self):
        """Initialize Claude client."""
        if not Config.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set in .env")
        
        self.client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    
    def get_next_question(self, context: dict) -> dict:
        """
        Generate next interviewer question based on context.
        
        Args:
            context: dict with keys:
                - scenario
                - turn_count
                - current_phase
                - candidate_transcript
                - platform_context
                - history (last few turns)
        
        Returns:
            dict with keys:
                - question: Next interviewer question
                - intent: What this question probes for
                - what_good_looks_like: Key points for strong answer
        """
        # Build system prompt
        system_prompt = f"""You are an expert technical interviewer conducting a system design interview.

{context['platform_context']}

Current scenario: {context['scenario']}
Current phase: {context['current_phase']}
Turn: {context['turn_count']}

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
        
        # Build user message with history
        history_text = ""
        if context.get('history'):
            history_text = "\n\nRecent turns:\n"
            for turn in context['history']:
                history_text += f"\nTurn {turn['turn']}:\n"
                history_text += f"Candidate: {turn['candidate']}\n"
                history_text += f"Interviewer: {turn['interviewer']}\n"
        
        user_message = f"{history_text}\n\nCandidate's latest response:\n{context['candidate_transcript']}\n\nWhat's your next question?"
        
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
        
        return result
