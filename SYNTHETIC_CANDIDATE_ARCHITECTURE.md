# Synthetic Candidate Architecture

Technical architecture for synthetic candidate generation in InterviewOS. This system generates configurable AI-powered interview candidates to enable automated testing, scoring calibration, and interview engine validation.

## Overview

The synthetic candidate system simulates realistic interview candidates with configurable skill levels, communication styles, and domain knowledge. It enables:

- **Automated testing**: Run full interviews without human candidates
- **Scoring calibration**: Validate that the scoring engine produces consistent, expected results across skill levels
- **Interview engine validation**: Ensure phase transitions, constraint locking, and probing work correctly
- **Regression testing**: Detect changes in interviewer behavior across code updates

## System Components

```
┌─────────────────────────────────────────────────────────────┐
│                  Synthetic Interview System                   │
│                                                              │
│  ┌──────────────────┐    ┌───────────────────────────────┐  │
│  │  CandidateProfile │    │  SyntheticCandidateGenerator  │  │
│  │  (Data Model)     │───▶│  (Profile → LLM Prompt)       │  │
│  │                   │    │                               │  │
│  │  • SkillLevel     │    │  • generate_profile()         │  │
│  │  • Persona        │    │  • build_candidate_prompt()   │  │
│  │  • ResponseConfig │    │  • generate_response()        │  │
│  └──────────────────┘    └───────────┬───────────────────┘  │
│                                      │                       │
│                                      ▼                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              SyntheticInterviewRunner                  │  │
│  │              (Orchestration Layer)                     │  │
│  │                                                       │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │  │
│  │  │ PhaseManager │  │ SessionState │  │  Scoring   │  │  │
│  │  │ (Existing)   │  │ (Existing)   │  │  Engine    │  │  │
│  │  └─────────────┘  └──────────────┘  └────────────┘  │  │
│  │                                                       │  │
│  │  • run_interview()   — full session orchestration     │  │
│  │  • run_single_turn() — one interviewer↔candidate turn │  │
│  │  • get_transcript()  — conversation history export    │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

```
1. CONFIGURATION
   User provides: scenario_id, target_skill_level (or full CandidateProfile)
                        │
                        ▼
2. PROFILE GENERATION
   SyntheticCandidateGenerator.generate_profile(skill_level, scenario_id)
   → Creates CandidateProfile with:
     • Persona (name, background, years_exp, communication_style)
     • Per-dimension skill levels (requirements, architecture, depth, etc.)
     • Response configuration (verbosity, technical_accuracy, structure)
                        │
                        ▼
3. PROMPT CONSTRUCTION
   SyntheticCandidateGenerator.build_candidate_prompt(profile, phase, history)
   → Produces system prompt instructing LLM to roleplay as candidate
   → Includes: skill calibration rules, communication style, knowledge gaps
                        │
                        ▼
4. INTERVIEW LOOP (managed by SyntheticInterviewRunner)
   ┌─────────────────────────────────────────────────┐
   │  For each turn:                                  │
   │                                                  │
   │  a. PhaseManager generates interviewer prompt    │
   │  b. LLM generates interviewer question           │
   │  c. SyntheticCandidateGenerator generates        │
   │     candidate response using candidate prompt    │
   │  d. SessionState records messages, constraints   │
   │  e. PhaseManager checks time budget / advance    │
   │                                                  │
   │  Loop until WRAP phase completes                 │
   └─────────────────────────────────────────────────┘
                        │
                        ▼
5. SCORING
   ScoringEngine.score_interview(session)
   → Produces InterviewScorecard with per-dimension scores
   → Validates against expected score range from CandidateProfile
```

## Component Details

### 1. CandidateProfile Model (`backend/models/candidate_profile.py`)

#### SkillLevel Enum
Maps to expected scoring outcomes:
| SkillLevel | Expected Score Range | Description |
|------------|---------------------|-------------|
| NOVICE     | 1.0 – 1.9          | No system design experience |
| JUNIOR     | 2.0 – 2.9          | Basic knowledge, needs heavy prompting |
| MID        | 3.0 – 3.4          | Solid fundamentals, some depth |
| SENIOR     | 3.5 – 4.4          | Strong across dimensions |
| STAFF      | 4.5 – 5.0          | Exceptional, proactive, deep expertise |

#### CommunicationStyle Enum
Controls how the synthetic candidate communicates:
- **STRUCTURED**: Uses frameworks, numbered lists, clear signposting
- **VERBOSE**: Over-explains, tends to ramble, adds unnecessary detail
- **CONCISE**: Brief, direct answers, may need prompting for detail
- **RAMBLING**: Disorganized, jumps between topics, hard to follow

#### CandidatePersona Dataclass
```python
@dataclass
class CandidatePersona:
    name: str                          # "Alex Chen"
    background: str                    # "Senior backend engineer at a fintech startup"
    years_of_experience: int           # 7
    communication_style: CommunicationStyle
    strengths: List[str]               # ["distributed systems", "database design"]
    weaknesses: List[str]              # ["frontend", "cost optimization"]
```

#### CandidateProfile Dataclass
```python
@dataclass
class CandidateProfile:
    persona: CandidatePersona
    overall_skill_level: SkillLevel
    dimension_skills: Dict[str, SkillLevel]  # Per-dimension overrides
    response_config: ResponseConfig          # Verbosity, accuracy settings
    target_score_range: Tuple[float, float]  # Expected overall score (min, max)
    scenario_id: str                         # "url-shortener"
```

### 2. SyntheticCandidateGenerator (`backend/interview/synthetic_candidate.py`)

Responsible for creating candidate profiles and generating LLM prompts that make Claude roleplay as a candidate at a specific skill level.

#### Key Methods

- **`generate_profile(skill_level, scenario_id)`**: Creates a complete CandidateProfile with randomized persona traits appropriate for the skill level
- **`build_candidate_prompt(profile, phase, context)`**: Constructs a system prompt that instructs the LLM to respond as the candidate, including:
  - Skill-level calibration rules (what to know, what to miss)
  - Communication style directives
  - Phase-appropriate behavior (scoping questions vs. architecture details)
  - Knowledge boundaries (what the candidate should and shouldn't know)
- **`generate_response(profile, interviewer_message, conversation_history)`**: Produces a candidate response given the profile and conversation context

#### LLM Integration Strategy

The synthetic candidate uses the same Anthropic API as the scoring engine (direct SDK, not through LiveKit):

```python
client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
response = await client.messages.create(
    model=config.llm_model,
    system=candidate_system_prompt,  # Built from CandidateProfile
    messages=conversation_history,
    max_tokens=1024,
    temperature=0.7,  # Some variation for realistic responses
)
```

**Temperature calibration by skill level:**
- STAFF/SENIOR: temperature=0.3 (consistent, high-quality responses)
- MID: temperature=0.5 (moderate variation)
- JUNIOR/NOVICE: temperature=0.7 (more erratic, realistic for lower skill)

### 3. SyntheticInterviewRunner (`backend/interview/synthetic_runner.py`)

Orchestrates a complete synthetic interview by coordinating existing components:

#### Key Methods

- **`run_interview(profile, config)`**: Runs a full interview from INTRO through WRAP
- **`run_single_turn(interviewer_message)`**: Executes one interviewer→candidate exchange
- **`get_results()`**: Returns the session with transcript and optional scorecard

#### Integration with Existing Components

```
SyntheticInterviewRunner
├── uses PhaseManager          (existing) — generates interviewer prompts
├── uses SessionState          (existing) — tracks conversation state
├── uses InterviewSession      (existing) — wraps session data
├── uses ScenarioLoader        (existing) — loads scenario metadata
├── uses SyntheticCandidateGenerator (new) — generates candidate responses
└── optionally uses ScoringEngine (existing) — scores the interview
```

## Configuration

Synthetic candidate settings integrate with the existing `AgentConfig` pattern:

```python
# In backend/config.py (future addition)
synthetic_candidate_temperature: float = 0.5
synthetic_max_turns_per_phase: int = 8
synthetic_default_skill_level: str = "mid"
```

## File Structure

```
backend/
├── models/
│   ├── candidate_profile.py    # NEW: CandidateProfile, SkillLevel, etc.
│   ├── session.py              # EXISTING: SessionState, InterviewSession
│   └── scorecard.py            # EXISTING: InterviewScorecard
├── interview/
│   ├── synthetic_candidate.py  # NEW: SyntheticCandidateGenerator
│   ├── synthetic_runner.py     # NEW: SyntheticInterviewRunner
│   ├── phase_manager.py        # EXISTING: used by runner
│   ├── scoring_engine.py       # EXISTING: used for post-interview scoring
│   └── scenario_loader.py      # EXISTING: used for scenario metadata
└── tests/
    ├── test_candidate_profile.py    # NEW: model tests
    ├── test_synthetic_candidate.py  # NEW: generator tests
    └── test_synthetic_runner.py     # NEW: runner tests
```

## Preset Candidate Profiles

The system includes built-in presets for common testing scenarios:

| Preset | Skill Level | Communication | Purpose |
|--------|-------------|---------------|---------|
| `strong_hire` | STAFF | STRUCTURED | Validate high-score path |
| `borderline` | MID | CONCISE | Test scoring boundary (3.0-3.5) |
| `weak_candidate` | JUNIOR | RAMBLING | Validate low-score path |
| `silent_candidate` | MID | CONCISE | Test silence recovery |
| `over_explainer` | SENIOR | VERBOSE | Test time budget enforcement |

## Future Extensions

1. **Batch runner**: Run multiple synthetic interviews in parallel with different profiles
2. **Score drift detection**: Compare scorecard outputs across code versions
3. **Custom personas**: Load candidate profiles from YAML files
4. **Multi-model testing**: Test with different LLM providers as the candidate
5. **Transcript replay**: Replay recorded transcripts through updated scoring engine
