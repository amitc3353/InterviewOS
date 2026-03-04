# InterviewOS - AI Agent Guidelines

## Project Overview

InterviewOS is a real-time voice-based AI interview simulator designed specifically for **Staff-level (L5→L6) system design interviews**. Unlike generic ChatGPT conversations, InterviewOS provides a structured, realistic interview experience with:

- **Structured interview phases**: Intro → Scope → Architecture → Deep Dive → Failure → Tradeoffs → Wrap
- **Realistic probing**: AI interviewer asks follow-up questions like a real Staff engineer
- **Locked constraints tracking**: Monitors and enforces architectural decisions throughout the session
- **Natural conversation**: No push-to-talk, just speak naturally with <2s response latency
- **Real-time voice pipeline**: Uses LiveKit WebRTC, Deepgram STT, Claude LLM, and Cartesia/OpenAI TTS

**Key Architecture Principle**: Strict separation between Interview Engine (business logic) and Transport layer (audio/networking). Components are modular and swappable via configuration.

## Technology Stack

### Backend (`backend/`)
- **Python**: 3.8+
- **LiveKit Agents Framework**: Real-time voice orchestration (1.0+)
- **STT**: Deepgram streaming API (default), with Whisper support planned
- **LLM**: Claude Sonnet 4 via Anthropic API (default), GPT-4 support planned
- **TTS**: Cartesia (default), OpenAI TTS (fallback)
- **VAD**: Silero for voice activity detection
- **Testing**: pytest
- **Key Libraries**:
  - `livekit` and `livekit-agents` (1.0+)
  - `livekit-plugins-deepgram`, `livekit-plugins-anthropic`, `livekit-plugins-cartesia`
  - `python-dotenv` for environment configuration

### Frontend/CLI (`app/`)
- **Python**: CLI-based application (no web frontend yet)
- **Architecture**: Modular adapter pattern for STT, LLM, TTS, and audio output
- **Transport**: LocalMicTransport (Phase 1), DailyTransport (Phase 2, planned)

### Infrastructure
- **Version Control**: Git with GitHub
- **CI/CD**: GitHub Actions (see `.github/`)
- **Environment**: `.env` file for API keys and configuration

## Directory Structure

### Root Layout
```
InterviewOS/
├── backend/              # LiveKit agent and interview engine
├── app/                  # CLI application with modular adapters
├── data/                 # Interview data (scorecards, scenarios)
├── .github/              # GitHub workflows and CI/CD
├── .env.example          # Environment variable template
├── requirements.txt      # Python dependencies
├── README.md            # User-facing setup guide
├── ARCHITECTURE.md      # Technical architecture details
├── INTERVIEWER_BEHAVIOR.md  # Interviewer AI behavior rules
├── INTERVIEW_PROTOCOL.md    # Interview phase specifications
└── CLAUDE.md            # This file
```

### Backend Structure (`backend/`)
```
backend/
├── agents/              # LiveKit agent implementation
│   └── interview_agent.py    # Main orchestration agent
├── interview/           # Interview logic
│   ├── phase_manager.py      # Phase transitions & system prompts
│   ├── response_parser.py    # JSON response parsing with fallback
│   ├── scoring_engine.py     # Post-interview scoring
│   ├── scenario_loader.py    # Scenario metadata loading
│   └── tts_pronunciations.py # TTS pronunciation customization
├── models/              # Data models
│   ├── session.py            # SessionState, InterviewSession, InterviewPhase
│   └── scorecard.py          # Scoring models
├── scenarios/           # Interview scenario definitions
├── tests/               # pytest test suite
│   ├── test_scoring_engine.py
│   ├── test_phase_integration.py
│   ├── test_scenario_loader.py
│   └── test_streaming_parser.py
├── config.py            # Environment-based configuration
├── run_interview.py     # Main entry point
└── test_setup.py        # Setup validation script
```

### App Structure (`app/`)
```
app/
├── engine/              # Interview engine (transport-agnostic)
│   ├── interview_engine.py   # Core state machine
│   ├── session.py            # Session state management
│   └── locked_constraints.py # Constraint tracking
├── adapters/            # Modular provider adapters
│   ├── stt_adapter.py        # Speech-to-text (Deepgram)
│   ├── llm_adapter.py        # LLM (Claude)
│   ├── tts_adapter.py        # Text-to-speech (OpenAI/Cartesia)
│   └── audio_out_adapter.py  # Audio playback
├── transport/           # Transport layer implementations
│   ├── base.py               # Transport interface
│   ├── local_mic.py          # Phase 1: Local microphone
│   └── daily.py              # Phase 2: Daily.co WebRTC (planned)
├── cli.py               # CLI commands
├── realtime.py          # Real-time voice mode entry point
├── interviewer.py       # Legacy interviewer logic
├── scorer.py            # Scoring utilities
├── stt.py               # STT utilities
└── tts.py               # TTS utilities
```

### Data Structure (`data/`)
```
data/
└── scorecards/          # Interview scorecard definitions
    └── *.json           # Scenario-specific scorecards (gitignored)
```

## Coding Conventions

### Python (Backend & App)

#### Import Organization
Follow this order (separated by blank lines):
1. Standard library imports
2. Third-party library imports
3. Local/application imports

Example:
```python
"""Module docstring."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from livekit import agents

from ..models.session import InterviewPhase, SessionState
```

#### Type Hints
- **ALWAYS use type hints** for function parameters and return types
- Use `typing` module: `Dict`, `List`, `Optional`, `Callable`
- Dataclasses should have typed fields

Example:
```python
def process_turn(self, transcript: str) -> Dict:
    """Process user turn and return response."""
    pass

@dataclass
class SessionState:
    phase: InterviewPhase = InterviewPhase.INTRO
    locked_constraints: Dict[str, str] = field(default_factory=dict)
```

#### Naming Conventions
- **snake_case**: Functions, variables, module names
- **PascalCase**: Classes, Enums
- **UPPER_SNAKE_CASE**: Constants
- **_private**: Single underscore prefix for internal/private functions and variables

Example:
```python
PHASE_DURATIONS = {...}  # Constant

class PhaseManager:  # Class
    def get_system_prompt(self, state: SessionState) -> str:  # Method
        pass

def _make_session() -> InterviewSession:  # Private helper
    pass
```

#### Docstrings
- **Module docstrings**: Brief description at top of file
- **Class docstrings**: Describe purpose and key responsibilities
- **Function docstrings**: Describe what it does, parameters (if complex), and return value
- Use triple double quotes: `"""`
- Keep docstrings concise and focused on "what" and "why", not "how"

Example:
```python
"""Manages interview phases and generates system prompts with INTERVIEWER_BEHAVIOR rules."""

class PhaseManager:
    """Manages interview phases and generates human-like system prompts."""

    def advance_phase(self, new_phase: InterviewPhase) -> bool:
        """
        Advance to next phase with monotonic enforcement.

        Returns:
            True if phase changed, False if blocked
        """
```

#### Dataclasses
- Prefer `@dataclass` for data containers over manual `__init__`
- Use `field(default_factory=...)` for mutable defaults (list, dict)
- Add methods for computed properties or data transformations

Example:
```python
@dataclass
class SessionState:
    phase: InterviewPhase = InterviewPhase.INTRO
    locked_constraints: Dict[str, str] = field(default_factory=dict)
    conversation_history: List[Message] = field(default_factory=list)

    def elapsed_seconds(self) -> float:
        """Total session elapsed time in seconds."""
        return (datetime.now() - self.session_start_time).total_seconds()
```

#### Configuration
- Use `@classmethod` for factory methods (e.g., `from_env()`)
- Load configuration from environment variables via `python-dotenv`
- Provide sensible defaults
- Validate configuration before use

Example:
```python
@dataclass
class AgentConfig:
    livekit_url: str
    llm_model: str = "claude-sonnet-4-20250514"

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Load configuration from environment variables."""
        return cls(
            livekit_url=os.getenv("LIVEKIT_URL", ""),
            llm_model=os.getenv("LLM_MODEL", "claude-sonnet-4-20250514"),
        )
```

#### Error Handling
- Be explicit about error cases
- Use specific exception types when possible
- Handle errors at appropriate abstraction levels
- Log errors with context

### TypeScript/JavaScript (Future Frontend)
_Not yet implemented. Frontend is currently CLI-based Python._

## Testing Requirements

### Backend Tests (`backend/tests/`)

#### Test Framework
- **pytest** is the testing framework
- Tests are located in `backend/tests/`
- Run tests with: `pytest backend/tests/` or `python -m pytest backend/tests/`

#### Test File Naming
- **Pattern**: `test_*.py` (e.g., `test_scoring_engine.py`)
- **Location**: `backend/tests/`
- One test file per module being tested

#### Test Function Naming
- **Pattern**: `test_<what_is_being_tested>()`
- Use descriptive names that explain the test scenario
- Example: `test_hire_signal_thresholds()`, `test_weighted_average_calculation()`

#### Test Structure
```python
"""Tests for ScoringEngine — 7 tests, zero network calls."""
import pytest
from unittest.mock import AsyncMock, patch

from backend.models.session import InterviewSession
from backend.interview.scoring_engine import ScoringEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(transcript_lines=None) -> InterviewSession:
    """Build a minimal InterviewSession for testing."""
    session = InterviewSession(session_id="test-123", scenario="Design a URL shortener")
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_dimension_score_labels():
    """score 1→'Critical Gap', 5→'Exceptional', all intermediates correct."""
    assert SCORE_LABELS[1] == "Critical Gap"
    assert SCORE_LABELS[5] == "Exceptional"
```

#### Pytest Fixtures
- Use `@pytest.fixture` for shared test setup
- Define fixtures in the test file or `conftest.py`
- Example:
```python
@pytest.fixture
def scenario_metadata():
    loader = ScenarioLoader()
    return loader.get_scenario("url-shortener")
```

#### Mocking
- Use `unittest.mock` for mocking external dependencies
- Mock API calls, file I/O, and network requests
- Use `AsyncMock` for async functions
- Example:
```python
from unittest.mock import AsyncMock, patch

@patch('backend.interview.scoring_engine.some_external_call')
def test_something(mock_external):
    mock_external.return_value = {"result": "success"}
```

#### Test Guidelines
- **Isolate tests**: No network calls, no file I/O (unless testing those specifically)
- **Use helper functions**: Prefix with underscore (e.g., `_make_session()`)
- **Test edge cases**: Boundary values, empty inputs, invalid states
- **Descriptive assertions**: Make failures easy to debug
- **Docstrings**: Brief description of what the test validates

#### Running Tests
```bash
# Run all tests
pytest backend/tests/

# Run specific test file
pytest backend/tests/test_scoring_engine.py

# Run specific test
pytest backend/tests/test_scoring_engine.py::test_hire_signal_thresholds

# Run with coverage
pytest --cov=backend backend/tests/
```

### Frontend Tests
_Not yet implemented. Add tests when frontend is built._

## Git Workflow

### Commit Message Format

Use **Conventional Commits** or descriptive action-based messages:

#### Conventional Commits (Preferred)
```
<type>: <description>

[optional body]
[optional footer]
```

**Types**:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Adding or updating tests
- `refactor:` - Code refactoring without changing behavior
- `chore:` - Maintenance tasks, dependency updates

**Examples**:
```
feat: Add staff-level adaptive three-tier probing system
fix: Resolve mypy type errors and Bandit warnings
docs: Add comprehensive interviewer behavior guide
test: Add tests for scoring engine
```

#### Action-Based Messages (Also Acceptable)
Start with an action verb:
```
Add interviewer conciseness rules and fix Cartesia TTS diagnostics
Fix LiveKit Agents 1.4+ API compatibility issues
Update interviewer to sound like real Staff engineer
```

#### Sprint-Based Messages (For Major Features)
```
Sprint 3: Post-interview scoring engine
Sprint 2: Add [CONTEXT:] tag for situational elaboration
Sprint 1: Stream spoken text to TTS via inline tags
```

### Branch Naming
- Use descriptive branch names
- Common patterns: `feature/<name>`, `fix/<name>`, `ai/<task-id>`
- Example: `feature/real-time-voice-scaffolding`, `ai/task-5bodnpi7o5jsptv`

### Pull Requests
- Include PR number in commit message when merging: `(#39)`
- Squash commits before merging for clean history

## Development Workflow

### Setup

1. **Clone the repository**:
```bash
git clone <repo-url>
cd InterviewOS
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your API keys
```

Required API keys:
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` - LiveKit (free tier at livekit.io)
- `DEEPGRAM_API_KEY` - Deepgram ($200 free credits)
- `ANTHROPIC_API_KEY` - Claude API
- `OPENAI_API_KEY` - OpenAI (for TTS fallback)
- `CARTESIA_API_KEY` - Cartesia (for primary TTS)

4. **Validate setup**:
```bash
python backend/test_setup.py
```
Should show all green checkmarks ✓

### Running the Interview Agent

**Basic run**:
```bash
python backend/run_interview.py
```

**With custom scenario**:
```bash
python backend/run_interview.py "Design a payment gateway"
```

**Connect to interview**:
- Agent creates a LiveKit room and outputs connection URL
- Connect via LiveKit client (web or mobile)
- Start speaking naturally - no push-to-talk needed

### Development Commands

**Run tests**:
```bash
pytest backend/tests/
```

**Validate configuration**:
```bash
python backend/test_setup.py
```

**Check code quality** (if linters are configured):
```bash
# mypy for type checking
mypy backend/

# bandit for security checks
bandit -r backend/
```

## File Modification Guidelines

### When to Create New Files
- **New feature/module**: Create new file in appropriate directory
- **New test**: Create `test_<module>.py` in `backend/tests/`
- **New scenario**: Add JSON file to `backend/scenarios/`
- **New data model**: Add to `backend/models/` or `app/engine/`

### When to Edit Existing Files
- **Bug fixes**: Edit the file containing the bug
- **Feature enhancement**: Edit existing module if it's a logical extension
- **Configuration changes**: Edit `backend/config.py` or `app/config.py`
- **Documentation updates**: Edit relevant `.md` files

### Code Organization Preferences
- **Modularity**: Keep modules focused on single responsibility
- **Separation of Concerns**: Interview engine ≠ Transport layer
- **Adapter Pattern**: Use adapters for swappable components (STT, LLM, TTS)
- **Dataclasses for Models**: Use `@dataclass` for data containers
- **Type Safety**: Always use type hints
- **Configuration-Driven**: Prefer configuration over hardcoding

### Anti-Patterns to Avoid
- **Tight Coupling**: Don't mix transport logic with interview engine
- **Hardcoded Values**: Use environment variables or config
- **Missing Type Hints**: Always add type annotations
- **Long Functions**: Break down into smaller, focused functions
- **Mutable Defaults**: Use `field(default_factory=...)` for lists/dicts in dataclasses
- **Network Calls in Tests**: Mock external dependencies

## Key Documentation References

When working on this project, consult these documents for detailed specifications:

- **ARCHITECTURE.md**: System architecture, design principles, folder structure
- **INTERVIEWER_BEHAVIOR.md**: AI interviewer behavioral rules and response guidelines
- **INTERVIEW_PROTOCOL.md**: Interview phase specifications and timing
- **README.md**: User-facing setup and quick start guide
- **backend/README.md**: Backend architecture, hooks, and troubleshooting
- **STRUCTURED_LOGGING.md**: Structured logging format and integration guide
- **SENTRY_INTEGRATION.md**: Sentry/GlitchTip error tracking integration

## Working with AI Agents

If you are an AI agent (like Claude Code) working with this codebase:

1. **Read before modifying**: Always read existing code before making changes
2. **Follow conventions**: Match the existing code style and patterns
3. **Test your changes**: Add tests for new functionality
4. **Type hints required**: Never write untyped Python code
5. **Respect architecture**: Don't break the separation between engine and transport
6. **Update docs**: If you change behavior, update relevant documentation
7. **Commit properly**: Use conventional commit format
8. **Ask when unsure**: Use the documentation files to understand design decisions

## Cost Considerations

Per 45-minute interview session:
- LiveKit: Free tier (5K participant-minutes/month)
- Deepgram STT: ~$0.35
- Claude Sonnet: ~$0.03
- OpenAI/Cartesia TTS: ~$0.05
- **Total**: ~$0.43/session

Keep cost efficiency in mind when modifying the pipeline.

## AI Agent Efficiency Guidelines

### Context Management
- Read this file FIRST, then go directly to the relevant files — don't explore the whole codebase
- For backend changes, the key files are almost always in `backend/agents/`, `backend/interview/`, or `backend/models/`
- For test changes, look at `backend/tests/` for existing patterns before writing new tests
- If modifying a file, read ONLY that file and its direct imports — not the entire directory
- Keep tool calls focused: use Grep to find specific patterns instead of reading entire files

### Most-Changed Files (Quick Reference)
- `backend/agents/interview_agent.py` — Main agent orchestration, llm_node, tts_node, AgentSession
- `backend/interview/response_parser.py` — JSON parsing with fallback chain
- `backend/interview/phase_manager.py` — Interview phase transitions and system prompts
- `backend/models/session.py` — SessionState, InterviewPhase, conversation history
- `backend/config.py` — All configuration and environment variables
- `backend/interview/scoring_engine.py` — Post-interview scoring logic

### Testing is Mandatory
Every PR must include tests. For every file you create or modify:
1. Add unit tests covering happy path AND error cases
2. If modifying async code, use `AsyncMock` and `pytest.mark.asyncio`
3. Mock ALL external services (Deepgram, Claude API, Cartesia, LiveKit)
4. Run `pytest backend/tests/` before committing to verify nothing is broken
5. Aim for: 1 test file per source file, minimum 3 tests per new function

### Code Quality Checklist (Before Committing)
- [ ] All functions have type hints
- [ ] All new classes/functions have docstrings
- [ ] No hardcoded values (use config.py or constants)
- [ ] Error handling for all external calls (try/except with logging)
- [ ] Tests pass: `pytest backend/tests/`
- [ ] Import order: stdlib → third-party → local

### Common Patterns in This Codebase
- **Error handling**: `try/except` with specific exceptions, log error, return fallback
- **Async operations**: `asyncio.wait_for(coro, timeout=X)` for timeouts
- **Configuration**: `AgentConfig.from_env()` pattern
- **Response parsing**: Always use the fallback chain (json → regex → raw)
- **Session state**: All state goes through `SessionState` dataclass, never globals
- **Structured logging**: Use `get_logger(__name__)` and async methods in voice loop (see STRUCTURED_LOGGING.md)
