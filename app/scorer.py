"""Interview scoring using structured rubric."""

import json
from pathlib import Path
from datetime import datetime
from anthropic import Anthropic
from app.config import Config

CONTEXT_FILE = Config.PROJECT_ROOT / "INTERVIEW_PLATFORM_CONTEXT.md"
PLATFORM_CONTEXT = CONTEXT_FILE.read_text() if CONTEXT_FILE.exists() else ""


def score_interview(transcript_path: str) -> dict:
    """
    Score an interview transcript using the 5-dimension rubric.

    Args:
        transcript_path: Path to transcript JSON file

    Returns:
        dict with scoring results:
            - dimensions: scores for each dimension (0-10)
            - total: sum of all dimensions (out of 50)
            - strengths: list of 2 strengths
            - improvements: list of 2 improvement areas
            - next_focus: recommendation for next practice session
    """
    transcript_file = Path(transcript_path)

    if not transcript_file.exists():
        raise FileNotFoundError(f"Transcript not found: {transcript_path}")

    if not Config.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    # Load transcript
    with open(transcript_file) as f:
        transcript_data = json.load(f)

    transcript_text = transcript_data.get("transcript", "")

    # Build scoring prompt
    system_prompt = f"""You are an expert technical interviewer evaluating a system design interview.

{PLATFORM_CONTEXT}

Score the candidate's performance across 5 dimensions (0-10 each):
1. Requirements Gathering
2. Architecture
3. Deep Dive
4. Scale/Bottlenecks
5. Tradeoffs

Output format (JSON):
{{
  "dimensions": {{
    "requirements_gathering": <0-10>,
    "architecture": <0-10>,
    "deep_dive": <0-10>,
    "scale_bottlenecks": <0-10>,
    "tradeoffs": <0-10>
  }},
  "total": <sum>,
  "strengths": ["strength 1", "strength 2"],
  "improvements": ["improvement 1", "improvement 2"],
  "next_focus": "Specific recommendation for next practice session"
}}

Be honest but constructive. Use the scoring guide in the context.
"""

    user_message = (
        f"Interview transcript:\n\n{transcript_text}\n\nProvide structured scoring."
    )

    # Call Claude for scoring
    client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    # Parse response
    try:
        scores = json.loads(response.content[0].text)
    except json.JSONDecodeError:
        raise RuntimeError("Failed to parse scoring response from Claude")

    return scores


def score_and_save(transcript_path: str) -> Path:
    """
    Score interview and save results to /scores folder.

    Returns:
        Path to saved scores JSON
    """
    scores = score_interview(transcript_path)

    # Generate output filename based on transcript
    transcript_name = Path(transcript_path).stem
    output_file = Config.SCORES_DIR / f"{transcript_name}_scores.json"

    # Add metadata
    scores["metadata"] = {
        "transcript_file": str(transcript_path),
        "scored_at": datetime.now().isoformat(),
    }

    # Save
    with open(output_file, "w") as f:
        json.dump(scores, f, indent=2)

    return output_file
