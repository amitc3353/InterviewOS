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
        system_prompt = f"""You are an expert Staff engineer conducting a system design interview.

Follow the Interview Protocol strictly.

INTERVIEW PROTOCOL:
- Return JSON with: phase, interviewer_says, question, what_im_listening_for, followup_if_vague
- interviewer_says: MAX 2 sentences, conversational acknowledgment
- question: ONE focused question only
- Use laddering: vague answer → drill for specifics; detailed answer → go deeper
- No long lists, no multiple questions, no verbose explanations

PHASES (in order):
1. intro - Greeting + scenario + format (1 turn, auto-transition to requirements)
2. requirements - Scope, scale, features (5-10 min)
3. architecture - High-level design, components (10-15 min)
4. deep_dive - Pick 1-2 critical parts, go deep (10 min)
5. scale - Bottlenecks, scaling strategies (5-10 min)
6. tradeoffs - Design decisions, alternatives (5 min)
7. conclusion - Wrap up

CURRENT STATE:
Scenario: {context["scenario"]}
Phase: {context["current_phase"]}
Turn: {context["turn_count"]}

STYLE:
- Sound like a real engineer, not a bot
- Be direct but friendly
- Challenge assumptions constructively
- Guide without giving answers

{context["platform_context"]}

Output JSON only (no markdown):
{{
  "phase": "current or next phase name",
  "interviewer_says": "Brief 1-2 sentence response",
  "question": "One focused question",
  "what_im_listening_for": "Key signals you're evaluating",
  "followup_if_vague": "Specific question if answer is too high-level"
}}
"""

        # Build user message with history
        history_text = ""
        if context.get("history"):
            history_text = "\n\nRecent turns:\n"
            for turn in context["history"]:
                history_text += f"\nTurn {turn['turn']}:\n"
                history_text += f"Candidate: {turn['candidate']}\n"
                history_text += f"Interviewer: {turn['interviewer']}\n"

        user_message = f"{history_text}\n\nCandidate's latest response:\n{context['candidate_transcript']}\n\nWhat's your next question?"

        # Call Claude
        response = self.client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        # Parse response (strip markdown code fences if present)
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {
                "question": raw,
                "intent": "Follow-up question",
                "what_good_looks_like": "Clear, structured thinking",
            }

        return result
