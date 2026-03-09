"""
Scoring engine for post-interview evaluation.

Calls Anthropic directly (independent of LiveKit) to produce a 5-dimension
scorecard after the interview WRAP phase completes (or session ends).

Dependency: anthropic (pip install anthropic). Likely already present via
livekit-plugins-anthropic, but noted here as an explicit direct-SDK dependency.
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import anthropic

from ..models.scorecard import (
    DIMENSION_WEIGHTS,
    SCORE_LABELS,
    DimensionScore,
    InterviewScorecard,
    compute_hire_signal,
)
from ..models.session import InterviewSession
from ..structured_logging import get_logger

logger = get_logger(__name__)

_SCORING_SYSTEM_PROMPT = """\
The interviewer follows a structured Staff-level (L5→L6) system design interview \
format with deliberate probing, vagueness pushback, and introduced failure scenarios. \
Score based on the CANDIDATE's performance — what they volunteered unprompted, how \
they handled challenges, and how they adapted. Do not penalize the candidate for \
being questioned.

You MUST output ONLY valid JSON — no prose, no markdown fences, no explanation \
outside the JSON object.\
"""

_RUBRIC = """\
Score each dimension 1-5 using ONLY integer values. Use ALL criteria below:

REQUIREMENTS GATHERING (weight 0.15)
5 – Asked proactively about 5-6 areas (scale, latency, consistency, availability, \
R/W ratio, geography); gave specific numbers; 4+ constraints locked
4 – Covered 4-5 areas; mostly specific numbers; 3 constraints locked; minor gaps
3 – Covered 3-4 areas; some vagueness accepted; 2 constraints locked; needed light nudging
2 – Covered 1-2 areas; missed critical constraints; 0-1 constraints locked; needed heavy prompting
1 – Jumped to design without scoping; no clarifying questions; no constraints established

SYSTEM ARCHITECTURE (weight 0.25)
5 – Clear component breakdown with justification for every major choice; \
identified bottlenecks proactively; zero vague components
4 – Clear components, justified most choices; minor gaps or 1 vague component
3 – Reasonable architecture but some vague components; needed prompting on justification; \
core path clear
2 – Incomplete architecture; multiple unjustified or contradictory choices; significant gaps
1 – No coherent architecture; components unnamed or contradictory

TECHNICAL DEPTH (weight 0.25)
5 – Implementation-level detail on critical components; discussed data models, \
edge cases, specific algorithms
4 – Good depth on 2+ critical components; mostly concrete; minor hand-waving
3 – Some depth on 1 component; tends high-level; could go deeper when directly probed
2 – Mostly high-level; couldn't produce detail when probed; stayed at component-name level
1 – No technical detail; all high-level; could not respond to implementation questions

SCALABILITY & RELIABILITY (weight 0.25)
5 – Proactively raised failure modes; adapted design well under 3+ failure scenarios; \
specific fallback plans with concrete mechanisms
4 – Handled 2-3 failure scenarios with solid responses; good scaling awareness; \
minor gaps in edge cases
3 – Addressed 1-2 failure scenarios adequately; some gaps; adapted under prompting
2 – Struggled with failure scenarios; surface-level responses; no concrete fallback plan
1 – Could not adapt to introduced failures; no scaling awareness; failures unaddressed

COMMUNICATION (weight 0.10)
5 – Crystal clear, structured thinking, concise and precise, articulated tradeoffs \
with specificity; uses frameworks (e.g., "Let me break this into 3 parts"); \
signposts transitions; verbalizes tradeoffs before choosing
4 – Clear and organized throughout; minor stumbles; tradeoffs generally explained
3 – Mostly clear; occasional rambling or imprecision; structure apparent but not tight
2 – Hard to follow at times; disorganized; tradeoffs poorly explained
1 – Unclear throughout; no discernible structure; very hard to follow\
"""

_OUTPUT_SCHEMA = """\
{
  "dimensions": {
    "requirements_gathering": {
      "score": <integer 1-5>,
      "rationale": "<2-3 sentences citing specific transcript moments>",
      "strengths": ["<bullet>", "<bullet>"],
      "gaps": ["<bullet>", "<bullet>"]
    },
    "system_architecture": {
      "score": <integer 1-5>,
      "rationale": "<2-3 sentences citing specific transcript moments>",
      "strengths": ["<bullet>"],
      "gaps": ["<bullet>"]
    },
    "technical_depth": {
      "score": <integer 1-5>,
      "rationale": "<2-3 sentences citing specific transcript moments>",
      "strengths": ["<bullet>"],
      "gaps": ["<bullet>"]
    },
    "scalability_reliability": {
      "score": <integer 1-5>,
      "rationale": "<2-3 sentences citing specific transcript moments>",
      "strengths": ["<bullet>"],
      "gaps": ["<bullet>"]
    },
    "communication": {
      "score": <integer 1-5>,
      "rationale": "<2-3 sentences citing specific transcript moments>",
      "strengths": ["<bullet>"],
      "gaps": ["<bullet>"]
    }
  },
  "narrative": "<2-3 sentence overall summary>"
}\
"""


class ScoringEngine:
    """Generates a post-interview scorecard using a direct Anthropic API call."""

    async def score_interview(self, session: InterviewSession, config) -> InterviewScorecard:
        """
        Run the scoring call and return a fully populated InterviewScorecard.

        Args:
            session: The completed (or partial) InterviewSession.
            config: AgentConfig with anthropic_api_key and llm_model.
        """
        prompt = self._build_scoring_prompt(session)
        raw = await self._call_claude(prompt, config)
        return self._parse_scorecard(raw, session)

    def _build_scoring_prompt(self, session: InterviewSession) -> str:
        """Build the user-turn scoring prompt."""
        elapsed_minutes = session.state.elapsed_seconds() / 60.0
        total_turns = session.state.total_turn_count

        constraints_block = (
            json.dumps(session.state.locked_constraints, indent=2)
            if session.state.locked_constraints
            else "(none locked)"
        )

        transcript_block = self._format_transcript(session)

        return (
            f"SCENARIO: {session.scenario}\n"
            f"Total turns: {total_turns} | Elapsed: {elapsed_minutes:.1f} min\n\n"
            f"LOCKED CONSTRAINTS:\n{constraints_block}\n\n"
            f"TRANSCRIPT:\n{transcript_block}\n\n"
            f"RUBRIC:\n{_RUBRIC}\n\n"
            f"OUTPUT SCHEMA (emit ONLY this JSON, nothing else):\n{_OUTPUT_SCHEMA}"
        )

    async def _call_claude(self, prompt: str, config) -> Dict:
        """Call Anthropic directly and return parsed JSON dict.

        Retries on transient API errors (network, rate limit, server errors)
        with exponential backoff, then retries once more on JSON parse failure.
        """
        client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        max_api_retries = 3
        backoff_base = 1.0  # seconds

        for attempt in range(max_api_retries):
            try:
                response = await client.messages.create(
                    model=config.llm_model,
                    max_tokens=2048,
                    temperature=0,          # deterministic scoring
                    system=_SCORING_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
            except Exception as api_err:
                status_code = getattr(api_err, "status_code", None)
                is_retryable = status_code in (429, 500, 502, 503, 529) or status_code is None
                if is_retryable and attempt < max_api_retries - 1:
                    wait = backoff_base * (2 ** attempt)
                    logger.warning(
                        f"Scoring API call failed (attempt {attempt + 1}/{max_api_retries}), "
                        f"retrying in {wait:.1f}s: {api_err}"
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"Scoring API call failed after {attempt + 1} attempts: {api_err}")
                raise

            raw_text = response.content[0].text.strip()

            # Strip markdown fences if Claude includes them despite instructions
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                raw_text = "\n".join(
                    line for line in lines
                    if not line.startswith("```")
                ).strip()

            try:
                return json.loads(raw_text)
            except json.JSONDecodeError as exc:
                if attempt < max_api_retries - 1:
                    logger.warning(f"Scoring JSON parse failed (attempt {attempt + 1}), retrying: {exc}")
                else:
                    logger.error(f"Scoring JSON parse failed after retry: {exc}\nRaw: {raw_text[:500]}")
                    raise

        # Unreachable, but satisfies type checkers
        raise RuntimeError("_call_claude exhausted retries")

    def _parse_scorecard(self, raw: Dict, session: InterviewSession) -> InterviewScorecard:
        """Build an InterviewScorecard from raw Claude JSON output."""
        dimensions: Dict[str, DimensionScore] = {}

        for dim_key, weight in DIMENSION_WEIGHTS.items():
            dim_data = raw["dimensions"][dim_key]
            score = int(dim_data["score"])
            dimensions[dim_key] = DimensionScore(
                dimension=dim_key,
                score=score,
                label=SCORE_LABELS[score],
                rationale=dim_data["rationale"],
                strengths=dim_data.get("strengths", []),
                gaps=dim_data.get("gaps", []),
            )

        overall_score = round(
            sum(dimensions[k].score * w for k, w in DIMENSION_WEIGHTS.items()), 1
        )

        return InterviewScorecard(
            session_id=session.session_id,
            scenario=session.scenario,
            dimensions=dimensions,
            overall_score=overall_score,
            hire_signal=compute_hire_signal(overall_score),
            narrative=raw["narrative"],
            locked_constraints=dict(session.state.locked_constraints),
            total_turns=session.state.total_turn_count,
            elapsed_minutes=round(session.state.elapsed_seconds() / 60.0, 1),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    async def save_scorecard(self, scorecard: InterviewScorecard) -> Path:
        """Write scorecard JSON to data/scorecards/{session_id}.json. Returns the Path."""
        output_dir = Path("data/scorecards")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{scorecard.session_id}.json"
        output_path.write_text(
            json.dumps(scorecard.to_dict(), indent=2),
            encoding="utf-8",
        )
        return output_path

    def _format_transcript(self, session: InterviewSession) -> str:
        """Format conversation history as [INTERVIEWER]: / [CANDIDATE]: lines."""
        lines = []
        for msg in session.state.conversation_history:
            if msg.role == "assistant":
                speaker = "[INTERVIEWER]"
            else:
                speaker = "[CANDIDATE]"
            lines.append(f"{speaker}: {msg.content}")
        return "\n".join(lines) if lines else "(no transcript)"
