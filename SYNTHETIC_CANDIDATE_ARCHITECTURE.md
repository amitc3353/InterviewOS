# Synthetic Candidate Architecture Plan

**Status**: Research and Design
**Date**: 2026-03-04
**Purpose**: Enable automated interview simulation with AI-powered synthetic candidates for testing, validation, and dataset generation

---

## Executive Summary

This document outlines the architecture for a synthetic candidate system that connects to InterviewOS to simulate realistic interview sessions. The system will support multiple candidate personas (strong, weak, average) and log full transcripts to PostgreSQL for analysis and validation.

**Key Design Decision**: Use **text injection directly into llm_node** rather than full voice pipeline to minimize latency, reduce API costs, and simplify initial implementation.

---

## 1. Connection Method

### Current Architecture Analysis

**File**: `backend/run_interview.py`
- Uses LiveKit Agent Server with `cli.run_app(worker_opts)`
- Creates worker with `entrypoint_fnc=entrypoint` and `prewarm_fnc=prewarm`
- Entrypoint is invoked when a participant joins the room

**File**: `backend/agents/interview_agent.py`
- `entrypoint(ctx: JobContext)`: Creates InterviewAgent instance and starts session
- `InterviewAgent.__init__()`: Initializes session state, phase manager, scoring engine
- `InterviewAgent.llm_node()`: Custom LLM node that:
  - Receives `chat_ctx` (conversation context) and `model_settings`
  - Streams Claude API responses with tag-based parsing (`[Q]`, `[ACK]`, `[SUMMARY]`)
  - Yields spoken text to TTS pipeline
  - Updates session state (phase, locked constraints) after streaming
  - Returns nothing if `_session_completed` flag is set
- **Pipeline**: STT (Deepgram) → `llm_node` → TTS (Cartesia/OpenAI) → Audio output

**Critical Code Location**: Line 115-300 in `backend/agents/interview_agent.py`
```python
async def llm_node(
    self,
    chat_ctx: llm.ChatContext,  # Contains conversation history
    tools: list[llm.Tool],
    model_settings: agents.ModelSettings,
):
    # Extracts user_text from chat_ctx.messages()
    # Calls Claude API via anthropic plugin
    # Streams response and parses tags
    # Updates self._session_state
```

### Recommended Approach: **Text Injection (v1)**

**Architecture**:
```
┌─────────────────────────────────────────────────────────────────┐
│ Synthetic Candidate (run_synthetic.py)                         │
│                                                                 │
│  ┌──────────────┐    ┌─────────────┐    ┌──────────────────┐  │
│  │ Persona LLM  │───▶│ Text Buffer │───▶│ Inject into      │  │
│  │ (Claude API) │    │             │    │ chat_ctx         │  │
│  └──────────────┘    └─────────────┘    └──────────────────┘  │
│                                                 │               │
└─────────────────────────────────────────────────┼───────────────┘
                                                  │
                                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ InterviewOS Backend (existing)                                  │
│                                                                 │
│     ┌─────────────┐                                             │
│     │ chat_ctx    │ (injected text appears as user message)     │
│     └──────┬──────┘                                             │
│            │                                                     │
│            ▼                                                     │
│     ┌─────────────┐    ┌──────────┐    ┌─────────────┐        │
│     │  llm_node   │───▶│ TTS Node │───▶│ Audio Out   │        │
│     │  (existing) │    │(existing)│    │ (existing)  │        │
│     └─────────────┘    └──────────┘    └─────────────┘        │
│            │                                                     │
│            ▼                                                     │
│     ┌─────────────┐                                             │
│     │ State Mgmt  │ (phase transitions, constraints)            │
│     └─────────────┘                                             │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation Strategy**:

1. **Create new entry point**: `backend/run_synthetic.py`
   - Does NOT use LiveKit room connection
   - Directly instantiates `InterviewAgent` with minimal mocking
   - Bypasses STT and audio playback (headless mode)

2. **Text injection mechanism**:
   - Call `agent.llm_node()` directly with pre-constructed `chat_ctx`
   - Build `chat_ctx` with synthetic user messages from persona LLM
   - Parse interviewer response from `llm_node()` yield stream
   - Feed interviewer response to persona LLM for next turn

3. **Session lifecycle**:
   ```python
   # Pseudocode structure
   agent = InterviewAgent(config, scenario)
   candidate = SyntheticCandidate(persona="strong_candidate")

   while not agent._session_completed:
       # Candidate generates response to current question
       candidate_text = await candidate.generate_response(
           interviewer_context=agent.get_last_interviewer_question()
       )

       # Inject into chat context
       chat_ctx.add_message(role="user", content=candidate_text)

       # Get interviewer response
       interviewer_chunks = []
       async for chunk in agent.llm_node(chat_ctx, tools=[], model_settings=...):
           interviewer_chunks.append(chunk)

       interviewer_text = parse_spoken_text(interviewer_chunks)

       # Log to database
       log_turn(session_id, turn, speaker, text, phase)
   ```

**Trade-offs**:

| Approach | Pros | Cons |
|----------|------|------|
| **Text Injection (RECOMMENDED)** | ✅ Simple implementation<br>✅ No STT/TTS latency or cost<br>✅ Fast iteration (10-20 sessions/min)<br>✅ Deterministic testing<br>✅ Direct access to session state | ⚠️ Doesn't test voice pipeline<br>⚠️ Requires mocking LiveKit components |
| **Full Voice Pipeline** | ✅ Tests complete system<br>✅ Realistic audio conditions | ❌ Complex TTS→STT round-trip<br>❌ Slow (1 session/45min)<br>❌ High API costs ($0.43/session)<br>❌ STT transcription errors add noise |

**Rationale**: Text injection is optimal for v1 because:
- Primary use case is **generating training data and validation sets**, not testing voice quality
- Enables rapid iteration (100+ sessions/day vs 32/day with voice)
- Lower cost ($0.03/session vs $0.43/session)
- Deterministic output (no STT errors)
- Can add voice pipeline testing as v2 enhancement

---

## 2. Candidate Behavior Design

### Persona Architecture

**File**: `backend/interview/scoring_engine.py` (lines 17, 30-86)
- Shows pattern for direct Anthropic SDK usage: `import anthropic`, `anthropic.Anthropic(api_key=...)`
- Uses system prompts with explicit behavior rules and output schemas
- Demonstrates rubric-based scoring (1-5 scale with detailed criteria)

**Persona LLM Design**:

```python
# File: backend/synthetic/candidate.py (NEW)

from dataclasses import dataclass
import anthropic
from typing import Literal

PersonaType = Literal["strong_candidate", "average_candidate", "weak_candidate"]

@dataclass
class SyntheticCandidate:
    persona: PersonaType
    model: str = "claude-sonnet-4-20250514"

    def __post_init__(self):
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.conversation_history = []

    async def generate_response(
        self,
        interviewer_question: str,
        phase: str,
        locked_constraints: dict
    ) -> str:
        """
        Generate candidate response based on persona and context.

        Uses one-line persona prompt to guide behavior.
        """
        system_prompt = self._get_persona_prompt()

        # Build context-aware user message
        user_message = self._build_context_message(
            interviewer_question,
            phase,
            locked_constraints
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,  # Typical candidate response length
            system=system_prompt,
            messages=self.conversation_history + [
                {"role": "user", "content": user_message}
            ]
        )

        candidate_text = response.content[0].text

        # Update conversation history for context continuity
        self.conversation_history.append(
            {"role": "user", "content": interviewer_question}
        )
        self.conversation_history.append(
            {"role": "assistant", "content": candidate_text}
        )

        return candidate_text
```

**Persona Prompts**:

```python
PERSONA_PROMPTS = {
    "strong_candidate": """
You are a strong L5→L6 system design interview candidate. You proactively ask
clarifying questions about scale, latency, consistency, availability, geography.
You give specific numeric constraints. You justify architectural choices with
clear tradeoffs. You volunteer failure modes and edge cases. You communicate
with structure ("Let me break this into 3 parts"). You go deep on critical
components with implementation-level detail. Keep responses concise (2-4 sentences).
""",

    "average_candidate": """
You are an average L5→L6 system design interview candidate. You ask some
clarifying questions but miss 1-2 critical areas. You provide mostly reasonable
architecture but need occasional prompting on justification. You address failure
scenarios when asked but don't volunteer them. Communication is clear but not
always structured. You go somewhat deep when probed. Keep responses concise (2-4 sentences).
""",

    "weak_candidate": """
You are a weak L5→L6 system design interview candidate. You jump to design
without much scoping. You accept vagueness without pushing back. Your architecture
has gaps or unjustified choices. You struggle with failure scenarios and stay
high-level when probed for detail. Communication is somewhat disorganized.
Keep responses concise (2-4 sentences).
"""
}
```

**Context Injection Strategy**:

The persona LLM needs awareness of:
1. **Current phase** (scope, architecture, deep_dive, etc.) → informs response style
2. **Locked constraints** → maintains consistency (don't contradict QPS if already stated)
3. **Interviewer's last question** → what to respond to
4. **Prior conversation** → accumulated via `conversation_history`

**Context Message Builder**:
```python
def _build_context_message(
    self,
    interviewer_question: str,
    phase: str,
    locked_constraints: dict
) -> str:
    """Build context-aware message for persona LLM."""

    context_parts = [f"Phase: {phase}"]

    if locked_constraints:
        constraints_str = ", ".join(
            f"{k}={v}" for k, v in locked_constraints.items()
        )
        context_parts.append(f"Locked constraints: {constraints_str}")

    context_parts.append(f"Interviewer: {interviewer_question}")

    return "\n".join(context_parts)
```

**Response Injection Point**:

In `InterviewAgent.llm_node()`, the user message is extracted from `chat_ctx.messages()`:
```python
# Line ~140 in interview_agent.py
messages_list = chat_ctx.messages()
if messages_list:
    latest_msg = messages_list[-1]
    if latest_msg.role == "user":
        user_text = extract_text_from_message(latest_msg)
```

**Injection mechanism**:
```python
# In run_synthetic.py
mock_chat_ctx = MagicMock(spec=llm.ChatContext)
mock_message = MagicMock()
mock_message.role = "user"
mock_message.content = [candidate_response_text]  # From persona LLM

mock_chat_ctx.messages = MagicMock(return_value=[mock_message])
```

---

## 3. PostgreSQL Logging Schema

### Current Session State Analysis

**File**: `backend/models/session.py`

Key data structures:
- `SessionState` (dataclass): Current in-memory state
  - `phase: InterviewPhase`
  - `locked_constraints: Dict[str, str]`
  - `conversation_history: List[Message]` (Message = role, content, timestamp)
  - `phase_turn_count: int`, `total_turn_count: int`
  - `session_start_time: datetime`, `phase_start_time: datetime`

- `InterviewSession` (dataclass): Complete session data
  - `session_id: str`, `scenario: str`
  - `state: SessionState`
  - `transcript: List[Dict]` (currently unused in backend, but present)
  - `metadata: Dict`, `scorecard: Optional[Dict]`

- `Message` (dataclass):
  - `role: str` ("user" or "assistant")
  - `content: str`
  - `timestamp: datetime`

### Recommended PostgreSQL Schema

**Database**: `interviewos_db`

#### Table: `interview_sessions`
Primary session metadata table.

```sql
CREATE TABLE interview_sessions (
    -- Identity
    session_id VARCHAR(255) PRIMARY KEY,
    scenario TEXT NOT NULL,

    -- Session type
    session_type VARCHAR(50) NOT NULL DEFAULT 'human',  -- 'human' | 'synthetic'
    persona_type VARCHAR(50),  -- NULL for human, 'strong_candidate' for synthetic

    -- Timing
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_seconds INTEGER,

    -- Final state
    final_phase VARCHAR(50),  -- Last phase reached
    total_turns INTEGER DEFAULT 0,

    -- Outcome
    scorecard JSONB,  -- Store full scorecard as JSON

    -- Metadata
    metadata JSONB,  -- Flexible field for additional data

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_sessions_type ON interview_sessions(session_type);
CREATE INDEX idx_sessions_persona ON interview_sessions(persona_type);
CREATE INDEX idx_sessions_started_at ON interview_sessions(started_at DESC);
CREATE INDEX idx_sessions_scenario ON interview_sessions(scenario);
```

#### Table: `interview_turns`
Conversation transcript with turn-level granularity.

```sql
CREATE TABLE interview_turns (
    -- Identity
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL REFERENCES interview_sessions(session_id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,

    -- Content
    speaker VARCHAR(20) NOT NULL,  -- 'interviewer' | 'candidate'
    text TEXT NOT NULL,

    -- Context
    phase VARCHAR(50) NOT NULL,  -- 'intro', 'scope', 'architecture', etc.
    phase_turn_number INTEGER NOT NULL,  -- Turn within current phase

    -- Timing
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    elapsed_seconds FLOAT,  -- Seconds since session start

    -- Metadata
    metadata JSONB,  -- STT confidence, latency metrics, etc.

    -- Constraints
    UNIQUE(session_id, turn_number)
);

-- Indexes for fast querying
CREATE INDEX idx_turns_session_id ON interview_turns(session_id);
CREATE INDEX idx_turns_session_turn ON interview_turns(session_id, turn_number);
CREATE INDEX idx_turns_speaker ON interview_turns(speaker);
CREATE INDEX idx_turns_phase ON interview_turns(phase);
CREATE INDEX idx_turns_timestamp ON interview_turns(timestamp DESC);

-- Full-text search on transcript content
CREATE INDEX idx_turns_text_search ON interview_turns USING gin(to_tsvector('english', text));
```

#### Table: `locked_constraints`
Track constraint evolution throughout session.

```sql
CREATE TABLE locked_constraints (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL REFERENCES interview_sessions(session_id) ON DELETE CASCADE,

    -- Constraint data
    constraint_key VARCHAR(255) NOT NULL,
    constraint_value TEXT NOT NULL,

    -- When it was locked
    locked_at_turn INTEGER NOT NULL,
    locked_at_phase VARCHAR(50) NOT NULL,
    locked_at_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Constraints
    UNIQUE(session_id, constraint_key)
);

CREATE INDEX idx_constraints_session_id ON locked_constraints(session_id);
CREATE INDEX idx_constraints_phase ON locked_constraints(locked_at_phase);
```

#### Table: `session_errors` (for error tracking)
Structured error logging with full context.

```sql
CREATE TABLE session_errors (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(255) REFERENCES interview_sessions(session_id) ON DELETE SET NULL,

    -- Error details
    error_type VARCHAR(100) NOT NULL,  -- 'llm_timeout', 'stt_failure', etc.
    error_message TEXT NOT NULL,
    stack_trace TEXT,

    -- Context
    phase VARCHAR(50),
    turn_number INTEGER,

    -- Timing
    occurred_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Additional context
    context JSONB,  -- Any additional debugging info

    -- Sentry integration
    sentry_event_id VARCHAR(255)  -- Link to Sentry event
);

CREATE INDEX idx_errors_session_id ON session_errors(session_id);
CREATE INDEX idx_errors_type ON session_errors(error_type);
CREATE INDEX idx_errors_occurred_at ON session_errors(occurred_at DESC);
```

### Database Client Implementation

**File**: `backend/database/client.py` (NEW)

```python
"""PostgreSQL database client for interview session logging."""

import os
import logging
from datetime import datetime
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseClient:
    """Thread-safe PostgreSQL client for interview logging."""

    def __init__(self, connection_string: Optional[str] = None):
        """
        Initialize database client.

        Args:
            connection_string: PostgreSQL connection string
                Format: postgresql://user:password@host:port/database
                Falls back to DATABASE_URL env var if not provided
        """
        self.connection_string = connection_string or os.getenv("DATABASE_URL")
        if not self.connection_string:
            raise ValueError("DATABASE_URL not configured")

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = psycopg2.connect(self.connection_string)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def create_session(
        self,
        session_id: str,
        scenario: str,
        session_type: str = "human",
        persona_type: Optional[str] = None
    ) -> None:
        """Create new interview session record."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO interview_sessions
                    (session_id, scenario, session_type, persona_type)
                    VALUES (%s, %s, %s, %s)
                """, (session_id, scenario, session_type, persona_type))

    def log_turn(
        self,
        session_id: str,
        turn_number: int,
        speaker: str,
        text: str,
        phase: str,
        phase_turn_number: int,
        elapsed_seconds: float,
        metadata: Optional[Dict] = None
    ) -> None:
        """Log a single conversation turn."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO interview_turns
                    (session_id, turn_number, speaker, text, phase,
                     phase_turn_number, elapsed_seconds, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    session_id, turn_number, speaker, text, phase,
                    phase_turn_number, elapsed_seconds, Json(metadata or {})
                ))

    def update_locked_constraint(
        self,
        session_id: str,
        key: str,
        value: str,
        turn_number: int,
        phase: str
    ) -> None:
        """Record a newly locked constraint."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO locked_constraints
                    (session_id, constraint_key, constraint_value,
                     locked_at_turn, locked_at_phase)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (session_id, constraint_key) DO NOTHING
                """, (session_id, key, value, turn_number, phase))

    def complete_session(
        self,
        session_id: str,
        final_phase: str,
        total_turns: int,
        scorecard: Optional[Dict] = None
    ) -> None:
        """Mark session as completed and store final state."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE interview_sessions
                    SET completed_at = NOW(),
                        duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at)),
                        final_phase = %s,
                        total_turns = %s,
                        scorecard = %s,
                        updated_at = NOW()
                    WHERE session_id = %s
                """, (final_phase, total_turns, Json(scorecard or {}), session_id))

    def log_error(
        self,
        session_id: Optional[str],
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None,
        phase: Optional[str] = None,
        turn_number: Optional[int] = None,
        context: Optional[Dict] = None,
        sentry_event_id: Optional[str] = None
    ) -> None:
        """Log an error with full context."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO session_errors
                    (session_id, error_type, error_message, stack_trace,
                     phase, turn_number, context, sentry_event_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    session_id, error_type, error_message, stack_trace,
                    phase, turn_number, Json(context or {}), sentry_event_id
                ))
```

**Migration File**: `backend/database/migrations/001_create_tables.sql` (NEW)

Contains all CREATE TABLE statements from schema above.

**Integration Point**:

In `backend/agents/interview_agent.py`, add database logging hooks:
```python
class InterviewAgent:
    def __init__(self, config, scenario, db_client=None):
        # ... existing init code ...
        self.db_client = db_client

        if self.db_client:
            self.db_client.create_session(
                session_id=self._session_id,
                scenario=scenario,
                session_type="human"  # vs "synthetic"
            )

    async def llm_node(self, chat_ctx, tools, model_settings):
        # ... existing code ...

        # After extracting user_text (line ~150):
        if self.db_client and user_text:
            self.db_client.log_turn(
                session_id=self._session_id,
                turn_number=self._session_state.total_turn_count,
                speaker="candidate",
                text=user_text,
                phase=self._session_state.phase.value,
                phase_turn_number=self._session_state.phase_turn_count,
                elapsed_seconds=self._session_state.elapsed_seconds()
            )

        # After streaming interviewer response (line ~250):
        if self.db_client and interviewer_text:
            self.db_client.log_turn(
                session_id=self._session_id,
                turn_number=self._session_state.total_turn_count + 1,
                speaker="interviewer",
                text=interviewer_text,
                phase=self._session_state.phase.value,
                phase_turn_number=self._session_state.phase_turn_count,
                elapsed_seconds=self._session_state.elapsed_seconds()
            )
```

---

## 4. CLI Interface Design

### Command Structure

**File**: `backend/run_synthetic.py` (NEW)

```bash
# Basic usage
python backend/run_synthetic.py \
    --scenario "Design a URL shortener" \
    --persona "strong_candidate"

# With optional parameters
python backend/run_synthetic.py \
    --scenario "Design a URL shortener" \
    --persona "strong_candidate" \
    --max-turns 50 \
    --verbose

# Batch mode (run multiple sessions)
python backend/run_synthetic.py \
    --scenario "Design a URL shortener" \
    --persona "strong_candidate" \
    --batch 10
```

### CLI Arguments

```python
# In run_synthetic.py

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from backend.config import AgentConfig
from backend.agents.interview_agent import InterviewAgent
from backend.synthetic.candidate import SyntheticCandidate
from backend.database.client import DatabaseClient

load_dotenv()

def parse_args():
    parser = argparse.ArgumentParser(
        description="Run synthetic interview session with AI candidate"
    )

    # Required arguments
    parser.add_argument(
        "--scenario",
        required=True,
        help="Interview scenario (e.g., 'Design a URL shortener')"
    )
    parser.add_argument(
        "--persona",
        required=True,
        choices=["strong_candidate", "average_candidate", "weak_candidate"],
        help="Candidate persona type"
    )

    # Optional arguments
    parser.add_argument(
        "--max-turns",
        type=int,
        default=100,
        help="Maximum conversation turns before timeout (default: 100)"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=1,
        help="Number of sessions to run (default: 1)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip database logging (useful for testing)"
    )

    return parser.parse_args()


async def run_session(
    scenario: str,
    persona: str,
    max_turns: int,
    db_client: Optional[DatabaseClient]
) -> str:
    """
    Run a single synthetic interview session.

    Returns:
        session_id: ID of completed session
    """
    # Load config
    config = AgentConfig.from_env()

    # Create agent (without LiveKit connection)
    agent = InterviewAgent(
        config=config,
        scenario=scenario,
        db_client=db_client
    )

    # Create synthetic candidate
    candidate = SyntheticCandidate(persona=persona)

    # Session loop
    turn = 0
    interviewer_question = None  # Start with None - agent speaks first

    logger.info(f"Starting synthetic session: {agent._session_id}")
    logger.info(f"Scenario: {scenario}")
    logger.info(f"Persona: {persona}")

    while not agent._session_completed and turn < max_turns:
        turn += 1

        # Generate candidate response (skip first turn - let interviewer start)
        if turn > 1:
            candidate_text = await candidate.generate_response(
                interviewer_question=interviewer_question,
                phase=agent._session_state.phase.value,
                locked_constraints=agent._session_state.locked_constraints
            )

            logger.info(f"[Turn {turn}] Candidate: {candidate_text[:100]}...")

            # Inject into agent's chat context
            mock_chat_ctx = _build_mock_chat_ctx(candidate_text)
        else:
            # First turn - no candidate response yet
            mock_chat_ctx = _build_mock_chat_ctx("")

        # Get interviewer response
        interviewer_chunks = []
        try:
            async for chunk in agent.llm_node(
                chat_ctx=mock_chat_ctx,
                tools=[],
                model_settings=_get_default_model_settings()
            ):
                interviewer_chunks.append(chunk)
        except Exception as e:
            logger.error(f"LLM node error: {e}")
            if db_client:
                db_client.log_error(
                    session_id=agent._session_id,
                    error_type="llm_node_error",
                    error_message=str(e),
                    phase=agent._session_state.phase.value,
                    turn_number=turn
                )
            break

        # Parse interviewer response
        interviewer_question = _extract_spoken_text(interviewer_chunks)

        logger.info(f"[Turn {turn}] Interviewer: {interviewer_question[:100]}...")

        # Check for session completion
        if agent._session_completed:
            logger.info("Session completed - WRAP phase finished")
            break

    # Finalize session
    if db_client:
        # Generate scorecard (existing scoring_engine.py logic)
        scorecard = await _generate_scorecard(agent)

        db_client.complete_session(
            session_id=agent._session_id,
            final_phase=agent._session_state.phase.value,
            total_turns=agent._session_state.total_turn_count,
            scorecard=scorecard
        )

    logger.info(f"✓ Session completed: {agent._session_id}")
    return agent._session_id


def main():
    args = parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Initialize database client
    db_client = None
    if not args.no_db:
        try:
            db_client = DatabaseClient()
            logger.info("✓ Database connection initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            sys.exit(1)

    # Run session(s)
    session_ids = []
    for i in range(args.batch):
        if args.batch > 1:
            logger.info(f"\n{'='*60}")
            logger.info(f"Running session {i+1}/{args.batch}")
            logger.info(f"{'='*60}\n")

        session_id = asyncio.run(
            run_session(
                scenario=args.scenario,
                persona=args.persona,
                max_turns=args.max_turns,
                db_client=db_client
            )
        )
        session_ids.append(session_id)

    # Output summary
    print("\n" + "="*60)
    print("✓ Synthetic interview session(s) completed")
    print("="*60)
    print(f"Scenario: {args.scenario}")
    print(f"Persona: {args.persona}")
    print(f"Sessions: {len(session_ids)}")
    print("\nSession IDs:")
    for session_id in session_ids:
        print(f"  - {session_id}")
    print("\nReview sessions:")
    print(f"  psql $DATABASE_URL -c \"SELECT * FROM interview_sessions WHERE session_id IN ('{session_ids[0]}');\"")
    print("="*60)


if __name__ == "__main__":
    main()
```

### Session Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│ 1. INITIALIZATION                                           │
│    - Parse CLI arguments                                    │
│    - Load AgentConfig from .env                             │
│    - Initialize DatabaseClient                              │
│    - Create InterviewAgent instance (headless mode)         │
│    - Create SyntheticCandidate with persona                 │
│    - Log session_id to database (interview_sessions table)  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. CONVERSATION LOOP (until session_completed or max_turns) │
│                                                              │
│    ┌────────────────────────────────────────┐              │
│    │ A. Candidate generates response        │              │
│    │    - Call persona LLM with context     │              │
│    │    - Log turn to database (speaker='candidate')       │
│    └────────────────────────────────────────┘              │
│                     │                                        │
│                     ▼                                        │
│    ┌────────────────────────────────────────┐              │
│    │ B. Inject into agent chat context      │              │
│    │    - Build mock chat_ctx with text     │              │
│    └────────────────────────────────────────┘              │
│                     │                                        │
│                     ▼                                        │
│    ┌────────────────────────────────────────┐              │
│    │ C. Get interviewer response            │              │
│    │    - Call agent.llm_node()             │              │
│    │    - Parse streamed chunks             │              │
│    │    - Extract spoken text               │              │
│    │    - Log turn to database (speaker='interviewer')     │
│    └────────────────────────────────────────┘              │
│                     │                                        │
│                     ▼                                        │
│    ┌────────────────────────────────────────┐              │
│    │ D. Update state                        │              │
│    │    - Phase transitions happen in agent │              │
│    │    - Locked constraints logged to DB   │              │
│    └────────────────────────────────────────┘              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. FINALIZATION                                             │
│    - Generate scorecard (using ScoringEngine)               │
│    - Update interview_sessions with final state             │
│    - Print session_id for review                            │
│    - Exit cleanly                                           │
└─────────────────────────────────────────────────────────────┘
```

### Exit Conditions

1. **Normal completion**: `agent._session_completed == True` (WRAP phase finished)
2. **Timeout**: `turn >= max_turns` (default 100 turns = ~50 Q&A pairs)
3. **LLM error**: Exception in `agent.llm_node()` (logged to database, session terminates)
4. **Keyboard interrupt**: `Ctrl+C` (clean shutdown, log partial session)

### Output Format

**Console output**:
```
Starting synthetic session: synth-abc123-2026-03-04
Scenario: Design a URL shortener
Persona: strong_candidate
[Turn 1] Interviewer: Hey! Let's design a URL shortener. Before we dive in, what...
[Turn 2] Candidate: Thanks! Let me start by clarifying some requirements. What scale...
[Turn 3] Interviewer: Good questions. Let's say 100 million URLs created per month...
...
[Turn 42] Interviewer: [WRAP] That wraps up our interview. Thank you!
Session completed - WRAP phase finished
✓ Session completed: synth-abc123-2026-03-04

============================================================
✓ Synthetic interview session completed
============================================================
Scenario: Design a URL shortener
Persona: strong_candidate
Sessions: 1

Session IDs:
  - synth-abc123-2026-03-04

Review session:
  psql $DATABASE_URL -c "SELECT * FROM interview_sessions WHERE session_id = 'synth-abc123-2026-03-04';"
============================================================
```

---

## 5. Error Capture Strategy

### Current Error Handling Analysis

**File**: `backend/config.py` (lines 100-133)
- Sentry SDK integration via `init_sentry()` method
- Configured with DSN, environment, trace sampling

**File**: `backend/interview/sentry_context.py`
- `set_interview_context(session_id, state)`: Tags Sentry events with session metadata
- `update_turn_context(state)`: Refreshes tags after each turn
- `capture_exception_with_context()`: Captures exceptions with full context

**File**: `backend/agents/interview_agent.py`
- Try/except blocks around LLM calls (lines 160-200)
- Retry logic for LLM timeouts (lines 26-27: `MAX_LLM_RETRIES = 3`)
- Logging at ERROR level for exceptions

### Error Types in Synthetic Mode

```python
# backend/synthetic/errors.py (NEW)

class SyntheticSessionError(Exception):
    """Base exception for synthetic session errors."""
    pass

class PersonaLLMError(SyntheticSessionError):
    """Error calling persona LLM API."""
    pass

class InterviewerLLMError(SyntheticSessionError):
    """Error calling interviewer LLM (agent.llm_node)."""
    pass

class DatabaseError(SyntheticSessionError):
    """Error writing to database."""
    pass

class SessionTimeoutError(SyntheticSessionError):
    """Session exceeded max_turns without completing."""
    pass
```

### Error Logging Integration

**Dual logging strategy**: Sentry + PostgreSQL

```python
# In run_synthetic.py

from backend.interview.sentry_context import (
    set_interview_context,
    capture_exception_with_context
)

async def run_session(...):
    # Initialize Sentry context
    set_interview_context(
        session_id=agent._session_id,
        state=agent._session_state
    )

    try:
        # ... session loop ...

        # Example: Persona LLM error
        try:
            candidate_text = await candidate.generate_response(...)
        except Exception as e:
            # Log to Sentry
            capture_exception_with_context(
                exception=e,
                session_id=agent._session_id,
                state=agent._session_state,
                extra_context={
                    "error_source": "persona_llm",
                    "persona": persona,
                    "turn": turn
                }
            )

            # Log to database
            if db_client:
                db_client.log_error(
                    session_id=agent._session_id,
                    error_type="persona_llm_error",
                    error_message=str(e),
                    stack_trace=traceback.format_exc(),
                    phase=agent._session_state.phase.value,
                    turn_number=turn,
                    context={"persona": persona}
                )

            # Re-raise or handle gracefully
            raise PersonaLLMError(f"Persona LLM failed at turn {turn}") from e

    except SyntheticSessionError as e:
        logger.error(f"Session failed: {e}")

        # Mark session as failed in database
        if db_client:
            db_client.complete_session(
                session_id=agent._session_id,
                final_phase=agent._session_state.phase.value,
                total_turns=agent._session_state.total_turn_count,
                scorecard=None  # No scorecard for failed sessions
            )

        return None  # Signal failure
```

### Error Context Enrichment

**Sentry tags** (set via `set_interview_context`):
- `session_id`: Unique session identifier
- `session_type`: "synthetic" (vs "human")
- `persona_type`: "strong_candidate" / "average_candidate" / "weak_candidate"
- `turn_number`: Current turn number
- `phase`: Current interview phase
- `error_source`: "persona_llm" / "interviewer_llm" / "database"

**Database fields** (in `session_errors` table):
- `session_id`: Link to interview session
- `error_type`: Categorized error type
- `error_message`: Human-readable message
- `stack_trace`: Full Python traceback
- `phase`, `turn_number`: Conversation context
- `context` (JSONB): Flexible additional data
- `sentry_event_id`: Link to Sentry event for correlation

### Retry and Fallback Logic

**LLM errors**:
```python
# In run_synthetic.py

MAX_PERSONA_LLM_RETRIES = 3
RETRY_DELAY_SECONDS = 2

async def generate_with_retry(candidate, **kwargs):
    """Retry persona LLM calls with exponential backoff."""
    for attempt in range(MAX_PERSONA_LLM_RETRIES):
        try:
            return await candidate.generate_response(**kwargs)
        except anthropic.APIError as e:
            if attempt == MAX_PERSONA_LLM_RETRIES - 1:
                raise

            delay = RETRY_DELAY_SECONDS * (2 ** attempt)
            logger.warning(f"Persona LLM error, retrying in {delay}s: {e}")
            await asyncio.sleep(delay)
```

**Database errors** (non-blocking):
```python
# In DatabaseClient

def log_turn(self, ...):
    """Log turn - non-blocking on error."""
    try:
        # ... database insert ...
    except Exception as e:
        logger.error(f"Failed to log turn {turn_number}: {e}")
        # Don't raise - allow session to continue
        # Sentry will capture the exception
```

### Monitoring and Alerting

**GlitchTip webhook integration** (existing):
- Alerts on high error rates
- Filters for `session_type:synthetic` errors
- Threshold: >5% session failure rate

**Postgres queries for analysis**:
```sql
-- Session success rate by persona
SELECT
    persona_type,
    COUNT(*) as total_sessions,
    SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END) as completed,
    ROUND(100.0 * SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate_pct
FROM interview_sessions
WHERE session_type = 'synthetic'
GROUP BY persona_type;

-- Most common error types
SELECT
    error_type,
    COUNT(*) as error_count,
    COUNT(DISTINCT session_id) as affected_sessions
FROM session_errors
GROUP BY error_type
ORDER BY error_count DESC
LIMIT 10;

-- Error rate by phase
SELECT
    phase,
    COUNT(*) as errors
FROM session_errors
WHERE occurred_at > NOW() - INTERVAL '24 hours'
GROUP BY phase
ORDER BY errors DESC;
```

---

## Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Create database schema (`backend/database/migrations/001_create_tables.sql`)
- [ ] Implement `DatabaseClient` (`backend/database/client.py`)
- [ ] Add database logging hooks to `InterviewAgent` (`backend/agents/interview_agent.py`)
- [ ] Create synthetic error types (`backend/synthetic/errors.py`)

### Phase 2: Synthetic Candidate
- [ ] Implement `SyntheticCandidate` class (`backend/synthetic/candidate.py`)
- [ ] Define persona prompts with clear behavioral guidelines
- [ ] Add conversation history tracking for context continuity
- [ ] Test persona LLM responses with mock conversations

### Phase 3: CLI Runner
- [ ] Create `run_synthetic.py` with argument parsing
- [ ] Implement session loop with text injection
- [ ] Add retry logic for LLM failures
- [ ] Implement clean exit handlers (Ctrl+C, timeouts)

### Phase 4: Testing
- [ ] Unit tests for `DatabaseClient` (mocked psycopg2)
- [ ] Unit tests for `SyntheticCandidate` (mocked Anthropic API)
- [ ] Integration test for full session flow
- [ ] Validate database schema with test data

### Phase 5: Documentation
- [ ] Update README with synthetic session instructions
- [ ] Document database schema in ARCHITECTURE.md
- [ ] Add persona tuning guide (adjust prompts based on scorecard results)

---

## File Paths Reference

### New Files (To Be Created)
```
backend/
  synthetic/
    __init__.py
    candidate.py          # SyntheticCandidate class with persona prompts
    errors.py             # Exception types for synthetic sessions

  database/
    __init__.py
    client.py             # DatabaseClient for PostgreSQL logging
    migrations/
      001_create_tables.sql  # Schema creation

  run_synthetic.py        # CLI entry point for synthetic sessions
```

### Modified Files
```
backend/agents/interview_agent.py
  - Add db_client parameter to __init__
  - Add logging hooks in llm_node (lines ~150, ~250)

backend/config.py
  - Add DATABASE_URL configuration field
  - Add database connection validation

backend/tests/
  test_database_client.py    # NEW
  test_synthetic_candidate.py  # NEW
  test_synthetic_integration.py  # NEW
```

### Environment Variables
```bash
# .env additions
DATABASE_URL=postgresql://user:password@localhost:5432/interviewos_db

# Existing (reused)
ANTHROPIC_API_KEY=sk-ant-...  # Used by both interviewer and persona LLM
```

---

## Architecture Diagrams

### System Context
```
┌────────────────────────────────────────────────────────────────┐
│                      InterviewOS System                        │
│                                                                │
│  ┌─────────────────┐              ┌─────────────────┐        │
│  │ Human Mode      │              │ Synthetic Mode  │        │
│  │ (LiveKit voice) │              │ (Headless text) │        │
│  └─────────────────┘              └─────────────────┘        │
│          │                                  │                  │
│          ▼                                  ▼                  │
│  ┌───────────────────────────────────────────────────┐       │
│  │        InterviewAgent (backend/agents/)           │       │
│  │  - llm_node (interviewer LLM)                      │       │
│  │  - SessionState management                         │       │
│  │  - Phase transitions                               │       │
│  └───────────────────────────────────────────────────┘       │
│          │                                  │                  │
└──────────┼──────────────────────────────────┼──────────────────┘
           │                                  │
           ▼                                  ▼
  ┌──────────────────┐            ┌───────────────────┐
  │ LiveKit Room     │            │ SyntheticCandidate│
  │ (WebRTC audio)   │            │ (Claude API)      │
  └──────────────────┘            └───────────────────┘
           │                                  │
           │                                  │
           ▼                                  ▼
  ┌──────────────────────────────────────────────────┐
  │         PostgreSQL Database                      │
  │  - interview_sessions                            │
  │  - interview_turns                               │
  │  - locked_constraints                            │
  │  - session_errors                                │
  └──────────────────────────────────────────────────┘
```

### Conversation Flow (Synthetic Mode)
```
Turn 1:
  Interviewer (agent.llm_node) → "Hey! Let's design a URL shortener..."
                                → DB log (speaker=interviewer, turn=1)

Turn 2:
  Candidate (persona LLM) → "Thanks! Let me clarify scale requirements..."
                          → DB log (speaker=candidate, turn=2)
  Interviewer → "[ACK] Good questions. Let's say 100M URLs/month..."
              → DB log (speaker=interviewer, turn=3)

Turn 3:
  Candidate → "Got it. For 100M URLs/month, that's ~40 writes/sec..."
            → DB log (speaker=candidate, turn=4)
  Interviewer → "[CONSTRAINT:qps=40] Yep. What about reads vs writes?"
              → DB log (speaker=interviewer, turn=5)
              → DB log constraint (key="qps", value="40")

... (continues through all phases)

Turn 42:
  Interviewer → "[WRAP] That wraps up our interview. Thank you!"
              → DB log (speaker=interviewer, turn=84)
              → agent._session_completed = True

Finalization:
  ScoringEngine → Generate scorecard
  DatabaseClient → Update interview_sessions with scorecard
  Exit → Print session_id for review
```

---

## Cost Analysis

**Per synthetic session**:
- Persona LLM (Claude Sonnet 4): ~25-30 API calls × 500 tokens/call = ~15K tokens
  - Input: 10K tokens × $3/MTok = $0.03
  - Output: 5K tokens × $15/MTok = $0.075
  - Subtotal: **$0.105**

- Interviewer LLM (existing): ~$0.03 (already accounted for)

- Database writes: Negligible (PostgreSQL local or managed)

- **Total per synthetic session**: ~**$0.14** (vs $0.43 for human voice session)

**Cost efficiency**:
- 10× faster than real-time (voice)
- 67% cheaper per session
- Enables 100+ sessions/day on a single API key

---

## Success Metrics

1. **Session completion rate**: >95% of synthetic sessions reach WRAP phase
2. **Error rate**: <5% of sessions encounter LLM/database errors
3. **Persona differentiation**: Scorecard averages show clear separation:
   - Strong: 4.0-4.5 average score
   - Average: 3.0-3.5 average score
   - Weak: 1.5-2.5 average score
4. **Database integrity**: Zero constraint overwrites, all turns logged sequentially
5. **Throughput**: 10+ sessions per hour per machine

---

## Next Steps (Post-Research)

1. **Create GitHub issue** for implementation tracking
2. **Database setup**: Provision PostgreSQL instance (local or RDS)
3. **Prototype persona prompts**: Run 5 sessions per persona, review quality
4. **Tune prompts**: Adjust based on scorecard results and transcript review
5. **Scale testing**: Run 100+ sessions to validate cost and error rates
6. **Integration**: Add to CI/CD for regression testing (1 session per scenario per commit)

---

## Appendix: Alternative Approaches Considered

### Voice Pipeline Approach (Rejected for v1)

**Flow**: Persona LLM → Cartesia TTS → Audio file → LiveKit room → Deepgram STT → InterviewAgent

**Pros**:
- Tests full audio pipeline
- Realistic prosody and pacing

**Cons**:
- 45-minute sessions (real-time only)
- High cost ($0.43/session)
- STT transcription errors add noise
- Complex audio routing

**Decision**: Defer to v2 for voice quality testing. Use text injection for v1 dataset generation.

---

## Appendix: Database Query Examples

**Get full transcript for session**:
```sql
SELECT
    turn_number,
    speaker,
    text,
    phase,
    timestamp
FROM interview_turns
WHERE session_id = 'synth-abc123'
ORDER BY turn_number;
```

**Analyze constraint locking patterns**:
```sql
SELECT
    locked_at_phase as phase,
    COUNT(*) as constraints_locked,
    AVG(locked_at_turn) as avg_turn_locked
FROM locked_constraints
WHERE session_id IN (
    SELECT session_id FROM interview_sessions
    WHERE persona_type = 'strong_candidate'
    LIMIT 100
)
GROUP BY locked_at_phase
ORDER BY
    CASE locked_at_phase
        WHEN 'scope' THEN 1
        WHEN 'architecture' THEN 2
        WHEN 'deep_dive' THEN 3
        WHEN 'failure' THEN 4
        ELSE 5
    END;
```

**Compare session quality by persona**:
```sql
SELECT
    persona_type,
    COUNT(*) as sessions,
    AVG((scorecard->>'overall_score')::float) as avg_score,
    AVG(total_turns) as avg_turns,
    AVG(duration_seconds / 60.0) as avg_duration_min
FROM interview_sessions
WHERE session_type = 'synthetic'
  AND scorecard IS NOT NULL
GROUP BY persona_type;
```

---

**End of Architecture Plan**
