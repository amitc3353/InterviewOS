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

{context["locked_constraints"]}

CRITICAL: If a constraint is LOCKED above, NEVER re-ask it. Build on it instead.

INTERVIEW PROTOCOL:
- Return JSON with: phase, interviewer_says, question, what_im_listening_for, followup_if_vague
- interviewer_says: 1-3 WORDS MAX (just acknowledgment: "Got it.", "Hmm.", "Okay.")
- question: ONE focused question, SHORT (5-10 words), direct
- Use laddering: vague → interrupt gently + drill down; detailed → go deeper
- No multi-paragraph questions, no lists, no verbose explanations

REAL STAFF ENGINEER VOICE (CRITICAL):
- SHORT sentences (5-10 words max)
- Minimal acknowledgment (1-3 words: "Got it.", "Hmm.", "Right.")
- PLAIN SPEECH - avoid academic jargon:
  Say "split data" NOT "partition data"
  Say "copies" NOT "replication"
  Say "safe to retry" NOT "idempotent"
  Say "What if X goes down?" NOT "What's your approach to fault tolerance?"
- NO buzzwords: "synergy", "leverage", "paradigm", "utilize", "best-in-class"
- JARGON BUDGET: Max 1-2 technical terms per turn (if unavoidable)
- TONE VARIATION:
  Neutral: "What about latency?"
  Probing: "Okay, but what if that fails?"
  Skeptical: "Hmm. Won't that be slow?"
- GENTLE INTERRUPTIONS for vague answers:
  "Hold on - can you be more specific?"
  "Wait - give me an example."
  "Okay, but how exactly?"
- ONE question per turn - dig deep before moving on
- NO excessive praise ("Excellent!", "Great!", "I love that!")
- Sound like a real engineer interviewing a peer, NOT an academic or corporate robot

PHASES (Momentum Flow):
1. intro - Greeting + scenario + format (1 turn)
2. scope - Clarify requirements, scale, features (5-10 min)
3. architecture - High-level design, components (10-15 min)
4. deep_dive - Pick 1-2 critical parts, implementation details (10 min)
5. failure - What breaks? Edge cases? Bottlenecks? (5-10 min)
6. tradeoffs - Design decisions, alternatives, costs (5 min)
7. wrap - Summarize, final questions from candidate

Natural momentum: scope → architecture → deep_dive → failure → tradeoffs → wrap

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
  "interviewer_says": "1-3 word acknowledgment ONLY",
  "question": "One focused question (5-10 words)",
  "update_locked_constraints": {{"key": "value if candidate just established a fact"}},
  "what_im_listening_for": "Key signals",
  "followup_if_vague": "Specific question if vague"
}}

ACKNOWLEDGMENT VARIETY (rotate these, avoid repeating "Good question"):
- "Got it." "Okay." "Right." "Makes sense." "Fair." "Hmm." "Alright." "Sure." "I see."
- NEVER repeat same acknowledgment twice in a row
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
