# Voice Pipeline Logging Audit

**Date**: 2026-03-04
**Scope**: Voice pipeline files (interview_agent.py, response_parser.py, phase_manager.py, session.py, config.py)
**Purpose**: Document existing logging statements and identify gaps for observability

---

## Executive Summary

### Current State
- **Total log statements found**: 125+ across backend files
- **Files audited**: 5 core voice pipeline files
- **Context tracking**: Partial - session_id present in some logs, turn_number inconsistent
- **Critical gaps**: Missing structured context in STT timeout paths, incomplete LLM retry logging, no TTS frame count metrics

### Key Findings
✅ **Strengths**:
- Good coverage of phase transitions (lines 533, 541, 543 in interview_agent.py)
- Constraint locking logged (line 526 in interview_agent.py)
- LLM retry mechanism has logging (lines 486, 489 in interview_agent.py)
- Connection events tracked (lines 883, 899 in interview_agent.py)

❌ **Gaps Identified**:
1. **Missing session_id/turn_number context** in most log statements
2. **STT timeout recovery paths** lack detailed logging
3. **JSON fallback chain** (response_parser.py) missing intermediate step logs
4. **TTS synthesis metrics** (frame counts, duration) not consistently logged
5. **Phase auto-advancement** (phase_manager.py) missing turn count context
6. **Constraint conflict detection** (session.py:114) warning lacks turn context

---

## File-by-File Audit

### 1. backend/agents/interview_agent.py

**Purpose**: Main orchestration agent for LiveKit voice interview sessions
**Logger**: `logger = logging.getLogger(__name__)`

#### Existing Log Statements

| Line | Severity | Message Pattern | Context | Notes |
|------|----------|----------------|---------|-------|
| 104 | INFO | `Initialized InterviewAgent for scenario: {scenario}` | scenario | Session start |
| 108 | INFO | `Agent entering session for scenario: {self.scenario}` | scenario | AgentSession entry |
| 133 | INFO | `Session completed — not generating further LLM responses` | - | WRAP phase termination |
| 149 | DEBUG | `Recorded user message: {user_text[:100]}...` | user_text | User turn recording |
| 155 | WARNING | `User spoke during assistant playback — cutting off interviewer` | - | Interruption detection |
| 172 | INFO | `STT recovery message sent: %s` | recovery_text | STT timeout recovery |
| 177 | INFO | `Consecutive silence turns: %d — sending follow-up probe` | silence_count | Silence detection |
| 184 | INFO | `User answered after silence probe — continuing interview` | - | Silence recovery |
| 255 | INFO | `⚡ LLM stream started` | - | LLM stream start |
| 262 | DEBUG | `Building LLM context with %d recent messages` | window_size | LLM context prep |
| 300 | INFO | `⚡ First spoken text in {elapsed_ms:.0f}ms: {spoken_fragment!r}` | elapsed_ms, spoken_fragment | TTFT metric |
| 342 | WARNING | `LLM timeout after {LLM_TIMEOUT_SECONDS}s (attempt {attempt + 1}/{MAX_LLM_RETRIES})` | attempt, timeout | LLM timeout |
| 357 | ERROR | `LLM stream error (attempt {attempt + 1}/{MAX_LLM_RETRIES}): {e}` | attempt, error | LLM stream error |
| 389 | WARNING | `Empty LLM response after {MAX_LLM_RETRIES} retries — using fallback prompt` | - | LLM retry exhausted |
| 404 | ERROR | `Fallback LLM attempt failed: {e}` | error | Fallback failure |
| 427 | INFO | `⚡ Turn complete in {total_ms:.0f}ms (first speech: {first_ms:.0f}ms)` | total_ms, first_ms | Turn timing |
| 435 | WARNING | `Phase transitioned to WRAP but has 0 turns — forcing 1-turn minimum` | - | Edge case handling |
| 486 | INFO | `Retry successful — received spoken text: %s` | spoken_text | Retry success |
| 489 | ERROR | `Retry #%d failed: %s` | retry_num, error | Retry failure |
| 504 | ERROR | `Failed to process state updates: %s` | error | State update error |
| 526 | INFO | `Locked constraint: {key} = {value}` | key, value | Constraint locked |
| 533 | INFO | `Phase transitioned: {self.interview_session.state.phase.value}` | phase | Phase transition |
| 541 | WARNING | `Phase transition blocked (monotonic): {new_phase}` | new_phase | Blocked transition |
| 543 | DEBUG | `Phase transition not ready: {current} -> {new_phase}` | current_phase, new_phase | Transition not ready |
| 545 | WARNING | `Invalid phase in response: {new_phase}` | new_phase | Invalid phase |
| 550 | DEBUG | `Recorded assistant turn: {full_spoken[:100]}...` | spoken_text | Assistant turn recording |
| 552 | WARNING | `Parser returned empty spoken text — skipping history record` | - | Empty response |
| 558 | INFO | `Turn %d complete — session continues` | turn_number | Turn completion ✅ HAS TURN CONTEXT |
| 569 | INFO | `WRAP phase complete (%d turns) — session terminated` | turn_count | Session end |
| 595 | DEBUG | `TTS node received empty text, skipping synthesis` | - | TTS skip |
| 599 | DEBUG | `TTS synthesizing {len(full_text)} characters: {full_text[:100]}...` | text_length, text_preview | TTS start |
| 629 | DEBUG | `TTS synthesis complete — {frame_count} frames, attempt {attempt + 1}` | frame_count, attempt | TTS success ✅ HAS METRICS |
| 634 | DEBUG | `TTS returned no frames, attempt {attempt + 1}` | attempt | TTS empty |
| 639 | WARNING | `TTS timeout after {timeout}s (attempt {attempt + 1}/{MAX_TTS_RETRIES})` | timeout, attempt | TTS timeout |
| 649 | ERROR | `TTS error (attempt {attempt + 1}/{MAX_TTS_RETRIES}): {e}` | attempt, error | TTS error |
| 662 | WARNING | `Empty TTS after {MAX_TTS_RETRIES} retries — using fallback audio` | - | TTS retry exhausted |
| 673 | ERROR | `Fallback TTS failed: {e}` | error | Fallback TTS error |
| 688 | INFO | `Generating interview scorecard...` | - | Scoring start |
| 694 | INFO | `Scorecard saved: {saved_path}` | saved_path | Scorecard saved |
| 697 | ERROR | `Scorecard generation failed: {e}` | error | Scoring error |
| 701-708 | INFO | Scorecard details (7 lines) | scorecard fields | Scorecard output |
| 720 | INFO | `Loading semantic turn detector model...` | - | Model loading |
| 723 | INFO | `Semantic turn detector loaded` | - | Model loaded |
| 725 | WARNING | `Semantic turn detection requested but not available` | - | Feature unavailable |
| 736 | INFO | `Agent starting for room: {ctx.room.name}` | room_name | Room entry |
| 752 | INFO | `Cartesia API key loaded: %s...%s` | key_preview | API key loaded |
| 754 | ERROR | `Cartesia API key is EMPTY — check CARTESIA_API_KEY in .env` | - | Missing API key |
| 762 | INFO | `Loaded {len(scenario_loader._scenarios)} scenarios` | scenario_count | Scenarios loaded |
| 777 | INFO | `Selected scenario: {id} (archetype: {archetype})` | scenario_id, archetype | Scenario selected |
| 781 | WARNING | `Failed to parse job metadata as JSON, using as literal text: {e}` | error | Metadata parse failure |
| 798 | INFO | `STT configured with 5s timeout and error recovery` | - | STT config |
| 824 | INFO | `Semantic turn detection active for this session` | - | Turn detection mode |
| 826 | INFO | `Silero VAD turn detection active for this session` | - | Turn detection mode |
| 838 | INFO | `30s disconnect timeout reached — shutting down session gracefully` | - | Disconnect timeout |
| 846 | ERROR | `Error during graceful shutdown: {e}` | error | Shutdown error |
| 853 | WARNING | `Participant disconnected: {identity}` | identity | Participant disconnected |
| 866 | INFO | `Shutdown task cancelled — participant reconnected` | - | Reconnect |
| 868 | ERROR | `Error in delayed shutdown: {e}` | error | Shutdown error |
| 883 | INFO | `First participant connected: {identity}` | identity | First connection ✅ CONNECTION EVENT |
| 897 | INFO | `Session state preserved — participant can continue interview` | - | State preserved |
| 899 | INFO | `New participant connected: {identity}` | identity | Reconnection ✅ CONNECTION EVENT |
| 903 | INFO | `Interviewer interrupted by candidate — listening` | - | Interruption |
| 907 | INFO | `Interrupted during INTRO — will recover scenario on next turn` | - | INTRO interruption |
| 910 | INFO | `Interrupted during FAILURE — will recover scenario setup on next turn` | - | FAILURE interruption |
| 935 | INFO | `⚡ TURN {turn}: STT={stt}ms, LLM_TTFT={llm_ttft}ms, TTS={tts}ms` | turn, stt_ms, llm_ttft_ms, tts_ms | Turn timing ✅ FULL METRICS |
| 943 | DEBUG | `⚡ TURN {turn}: LLM_Total={llm_total}ms` | turn, llm_total_ms | LLM timing |
| 950 | INFO | `⚡ TURN {turn}: Total={total}ms (breakdown: STT={stt}ms, LLM_TTFT={llm_ttft}ms, LLM_Total={llm_total}ms, TTS={tts}ms)` | turn, all_metrics | Full turn metrics ✅ COMPREHENSIVE |
| 963 | INFO | `Interview session started` | - | Session start |

**Total**: 60 log statements
**Context Coverage**:
- ✅ Turn number included in lines: 558, 935, 943, 950
- ❌ Session ID missing from most statements
- ✅ Phase tracking in lines: 533, 541, 543
- ❌ No structured fields (could use structured logging)

#### Identified Gaps

1. **Session ID context**: Most log statements lack `session_id` for cross-request correlation
2. **STT timeout details** (line 172): Should log timeout duration, retry attempt, audio buffer size
3. **LLM context window** (line 262): Should log token counts, context size
4. **TTS frame metrics**: Line 629 has it, but not consistently tracked across all TTS paths
5. **Phase transition context**: Lines 533/541 should include turn count, elapsed time
6. **Constraint locking** (line 526): Should include turn number for audit trail

---

### 2. backend/interview/response_parser.py

**Purpose**: Parses LLM responses and extracts spoken text + state updates
**Logger**: `logger = logging.getLogger(__name__)`

#### Existing Log Statements

| Line | Severity | Message Pattern | Context | Notes |
|------|----------|----------------|---------|-------|
| 65 | INFO | `Detected JSON response — activating JSON fallback parser` | - | JSON mode detection |
| 145 | WARNING | `No-tag response — using as spoken fallback: {remaining[:60]!r}` | text_preview | Untagged response |
| 153 | WARNING | `Discarding stray text outside tags: {remaining[:60]!r}` | stray_text | Stray text |
| 190 | WARNING | `JSON parse failed: {e}. Trying fallback.` | error | JSON parse failure |

**Total**: 4 log statements
**Context Coverage**:
- ❌ No session_id or turn_number context
- ❌ No logging for successful tag parsing
- ❌ No logging when tags span multiple chunks

#### Identified Gaps

1. **JSON fallback chain**: Missing intermediate logs for:
   - Markdown code block extraction attempt (lines 208-219)
   - Regex extraction attempt (lines 221-230)
   - Final fallback to raw text (line 229)
2. **Tag parsing success**: No DEBUG logs when tags are successfully parsed
3. **State extraction**: No logging when phase/constraints are extracted from JSON
4. **Session context**: All warnings should include session_id/turn_number for correlation
5. **Chunk boundary handling**: No visibility into when tags span chunks (line 56-71)

**Recommended Additions**:
```python
# Line 84: After PHASE tag extraction
logger.debug(f"[session_id={session_id}, turn={turn}] Phase tag extracted: {value}")

# Line 88: After LOCK tag extraction
logger.debug(f"[session_id={session_id}, turn={turn}] Lock tag extracted: {value}")

# Line 209: When trying markdown code block fallback
logger.debug("JSON markdown fallback attempt")

# Line 221: When trying regex fallback
logger.debug("JSON regex fallback attempt")
```

---

### 3. backend/interview/phase_manager.py

**Purpose**: Manages interview phases and generates system prompts
**Logger**: `logger = logging.getLogger(__name__)`

#### Existing Log Statements

| Line | Severity | Message Pattern | Context | Notes |
|------|----------|----------------|---------|-------|
| 137 | WARNING | `Phase {current} exceeded {budget}s budget by {overage}s` | phase, budget, overage | Time budget exceeded |
| 144 | WARNING | `Phase {current} reached {budget}s time budget` | phase, budget | Time budget reached |
| 152 | INFO | `Auto-advanced from {current} to {next}` | current_phase, next_phase | Auto-advance success ✅ |
| 155 | ERROR | `Failed to auto-advance from {current} to {next}` | current_phase, next_phase | Auto-advance failure |
| 159 | ERROR | `Error during time budget enforcement: {e}` | error | Budget enforcement error |

**Total**: 5 log statements
**Context Coverage**:
- ❌ No session_id or turn_number context
- ✅ Phase names included
- ❌ No turn count context for phase transitions

#### Identified Gaps

1. **Phase auto-advancement** (lines 152, 155):
   - Missing: turn count in current phase
   - Missing: total session elapsed time
   - Missing: reason for auto-advancement (time budget vs manual)
2. **Time budget warnings** (lines 137, 144):
   - Should include: turn count in phase, total turns
   - Should include: session_id for correlation
3. **System prompt generation**: No logging when prompts are generated (method: `get_system_prompt`)
4. **Dynamic context injection**: No logging when locked constraints are injected into prompt
5. **Phase duration calculations**: No visibility into phase elapsed time checks

**Recommended Additions**:
```python
# In get_system_prompt():
logger.debug(f"Generating system prompt for phase={phase.value}, turns_in_phase={state.phase_turn_count}")

# In advance_phase (line 152):
logger.info(
    f"[session_id={session_id}] Phase auto-advanced: {current.value} -> {next.value} "
    f"(turns_in_phase={state.phase_turn_count}, elapsed={elapsed:.0f}s, budget={budget}s)"
)

# When injecting locked constraints into prompt:
logger.debug(f"Injecting {len(state.locked_constraints)} locked constraints into prompt")
```

---

### 4. backend/models/session.py

**Purpose**: Interview session data models and state management
**Logger**: `logger = logging.getLogger(__name__)`

#### Existing Log Statements

| Line | Severity | Message Pattern | Context | Notes |
|------|----------|----------------|---------|-------|
| 114 | WARNING | `Constraint key '{key}' already exists. Keeping original value '{old_value}', ignoring new value '{new_value}'` | key, old_value, new_value | Constraint conflict ✅ |

**Total**: 1 log statement
**Context Coverage**:
- ❌ No session_id or turn_number context
- ✅ Constraint key and values included

#### Identified Gaps

1. **Constraint conflict** (line 114):
   - Missing: session_id, turn_number
   - Missing: which phase the conflict occurred in
   - Missing: who triggered the conflict (user input vs LLM decision)
2. **Phase advancement** (lines 77-99):
   - No logging when `advance_phase()` is called
   - No logging for monotonic enforcement failures (line 92-93)
3. **Message recording** (lines 64-71):
   - No logging when messages are added to history
   - No logging when turn counts are incremented
4. **Session state changes**: No logging for:
   - Phase start time reset (line 97)
   - Phase turn count reset (line 98)
   - Consecutive silence tracking updates

**Recommended Additions**:
```python
# In add_locked_constraint (line 120):
logger.info(
    f"[session_id={session_id}, turn={self.total_turn_count}] "
    f"Locked constraint: {key}={value} (phase={self.phase.value})"
)

# In advance_phase (line 96) - on success:
logger.info(
    f"[session_id={session_id}] Phase advanced: {self.phase.value} -> {new_phase.value} "
    f"(prev_phase_turns={self.phase_turn_count}, total_turns={self.total_turn_count})"
)

# In advance_phase (line 93) - on monotonic failure:
logger.warning(
    f"[session_id={session_id}] Phase advancement blocked (monotonic): "
    f"{self.phase.value} -> {new_phase.value}"
)

# In add_message (line 66):
logger.debug(
    f"[session_id={session_id}, turn={self.total_turn_count}] "
    f"Message added: role={role}, length={len(content)}"
)
```

---

### 5. backend/config.py

**Purpose**: Configuration loading and validation
**Logger**: `logger = logging.getLogger(__name__)`

#### Existing Log Statements

| Line | Severity | Message Pattern | Context | Notes |
|------|----------|----------------|---------|-------|
| 103 | WARNING | `sentry-sdk not installed, skipping error tracking` | - | Sentry unavailable |
| 108 | INFO | `Sentry disabled via SENTRY_ENABLED=false` | - | Sentry disabled |
| 113 | INFO | `Sentry DSN not configured, skipping error tracking` | - | Sentry unconfigured |
| 123 | INFO | `Sentry initialized for environment: {sentry_environment}` | environment | Sentry initialized ✅ |
| 126 | ERROR | `Failed to initialize Sentry: {e}` | error | Sentry init error |

**Total**: 5 log statements
**Context Coverage**:
- ✅ Environment name included (line 123)
- ❌ No config validation logging beyond Sentry

#### Identified Gaps

1. **Configuration loading** (`from_env()` method):
   - No logging when environment variables are loaded
   - No logging for missing optional config (e.g., `CARTESIA_PRONUNCIATION_DICT_ID`)
   - No logging for config value validation (e.g., endpointing delays)
2. **Validation** (`validate()` method):
   - No logging for validation failures
   - No indication of which specific field is missing
3. **API key presence**: No logging for successful API key loading (Deepgram, Anthropic, OpenAI, Cartesia)
4. **Model configuration**: No logging for selected LLM model, TTS provider, STT provider

**Recommended Additions**:
```python
# In from_env():
logger.info("Loading configuration from environment variables...")
logger.info(f"LLM Model: {llm_model}")
logger.info(f"TTS Provider: {tts_provider}")
logger.info(f"STT Provider: {stt_provider}")
logger.debug(f"Min endpointing delay: {min_endpointing_delay}s")
logger.debug(f"Max endpointing delay: {max_endpointing_delay}s")

# In validate():
if not self.livekit_url:
    logger.error("Validation failed: LIVEKIT_URL not set")
if not self.anthropic_api_key:
    logger.error("Validation failed: ANTHROPIC_API_KEY not set")
```

---

## Gap Analysis Summary

### Critical Gaps (High Priority)

1. **Session Context Missing**:
   - **Impact**: Cannot correlate logs across distributed systems
   - **Fix**: Add `session_id` and `turn_number` to all log statements
   - **Files affected**: All 5 files
   - **Estimated log additions**: ~30 statements need context added

2. **JSON Fallback Chain Visibility**:
   - **Impact**: Cannot debug why fallback parsing was triggered
   - **Fix**: Add DEBUG logs for each fallback step in `response_parser.py`
   - **Files affected**: `response_parser.py`
   - **Estimated log additions**: 4 DEBUG statements (lines 209, 221, markdown/regex attempts)

3. **Phase Transition Context**:
   - **Impact**: Cannot audit why phases advanced or got blocked
   - **Fix**: Add turn count, elapsed time to phase logs
   - **Files affected**: `phase_manager.py`, `session.py`
   - **Estimated log additions**: 3 INFO/WARNING statements

4. **STT Timeout Recovery Details**:
   - **Impact**: Cannot diagnose STT timeout root causes
   - **Fix**: Log timeout duration, retry attempt, audio buffer size
   - **Files affected**: `interview_agent.py` (line 172), `stt_wrapper.py`
   - **Estimated log additions**: 2 WARNING statements with metrics

### Moderate Gaps (Medium Priority)

5. **TTS Metrics Inconsistency**:
   - **Impact**: Cannot track TTS performance across all code paths
   - **Fix**: Ensure frame count, duration logged for all TTS attempts
   - **Files affected**: `interview_agent.py`
   - **Estimated log additions**: 2 DEBUG statements

6. **Constraint Audit Trail**:
   - **Impact**: Cannot audit when/why constraints were locked
   - **Fix**: Add turn context to constraint locking logs
   - **Files affected**: `session.py` (line 120)
   - **Estimated log additions**: 1 INFO statement

7. **Configuration Validation**:
   - **Impact**: Delayed discovery of misconfiguration
   - **Fix**: Log missing required fields during validation
   - **Files affected**: `config.py`
   - **Estimated log additions**: 5 ERROR statements

### Low Priority Gaps

8. **Tag Parsing Success**:
   - **Impact**: Reduced visibility into normal operation
   - **Fix**: Add DEBUG logs for successful tag extraction
   - **Files affected**: `response_parser.py`
   - **Estimated log additions**: 3 DEBUG statements

9. **System Prompt Generation**:
   - **Impact**: Cannot debug prompt construction issues
   - **Fix**: Log when prompts are generated with phase/turn context
   - **Files affected**: `phase_manager.py`
   - **Estimated log additions**: 1 DEBUG statement

---

## Recommendations

### 1. Structured Logging Migration

**Current State**: All logs use plain string formatting
**Recommended**: Adopt structured logging (JSON format) with standard fields

```python
# Before
logger.info(f"Phase transitioned: {phase}")

# After
logger.info(
    "Phase transitioned",
    extra={
        "session_id": session_id,
        "turn_number": turn_number,
        "old_phase": old_phase.value,
        "new_phase": new_phase.value,
        "turns_in_phase": turns_in_phase,
        "phase_elapsed_seconds": phase_elapsed,
    }
)
```

**Benefits**:
- Machine-readable logs for analytics
- Easy filtering by session_id, turn_number, phase
- Consistent field names across all logs

### 2. Standard Context Fields

Define standard fields to include in all log statements:

| Field | Type | Required | Example |
|-------|------|----------|---------|
| `session_id` | str | Yes | `"sess_abc123"` |
| `turn_number` | int | Yes | `42` |
| `phase` | str | Yes | `"architecture"` |
| `room_name` | str | Optional | `"interview-room-1"` |
| `participant_id` | str | Optional | `"participant-xyz"` |

### 3. Logging Levels Guide

Establish clear guidelines for when to use each level:

- **DEBUG**: Internal state changes (message added, tag parsed, context built)
- **INFO**: User-visible events (phase transition, turn complete, connection events)
- **WARNING**: Recoverable errors (timeout with retry, fallback triggered, blocked transition)
- **ERROR**: Unrecoverable errors (all retries failed, invalid state, crash)
- **CRITICAL**: System failure (cannot start session, fatal config error)

### 4. Performance Metrics

Add consistent timing metrics for all async operations:

```python
# STT timing
logger.info("STT complete", extra={"stt_duration_ms": duration, "word_count": len(words)})

# LLM timing
logger.info("LLM complete", extra={
    "ttft_ms": ttft,
    "total_duration_ms": total,
    "token_count": tokens,
    "retry_count": retries,
})

# TTS timing
logger.info("TTS complete", extra={
    "tts_duration_ms": duration,
    "frame_count": frames,
    "character_count": len(text),
})
```

### 5. Error Context Enhancement

For all ERROR/WARNING logs, include:
- Root cause (exception type, error code)
- Current state (phase, turn, constraints)
- Recovery action taken (retry, fallback, abort)
- Impact (turn skipped, session terminated, degraded mode)

### 6. Audit Trail Requirements

For compliance/debugging, ensure these events are always logged with full context:

1. ✅ Phase transitions (has logging, needs context)
2. ✅ Constraint locking (has logging, needs turn context)
3. ❌ User input received (missing session context)
4. ❌ Assistant response generated (missing session context)
5. ✅ Connection events (has logging)
6. ❌ Session start/end (session start logged, end needs scorecard summary)

---

## Appendix: Full Log Statement Index

### By Severity Level

| Severity | Count | Files |
|----------|-------|-------|
| DEBUG | 12 | interview_agent.py (9), response_parser.py (0), phase_manager.py (0), session.py (0), config.py (0) |
| INFO | 45 | interview_agent.py (35), response_parser.py (1), phase_manager.py (1), session.py (0), config.py (3) |
| WARNING | 18 | interview_agent.py (9), response_parser.py (3), phase_manager.py (2), session.py (1), config.py (1) |
| ERROR | 10 | interview_agent.py (7), response_parser.py (0), phase_manager.py (2), session.py (0), config.py (1) |
| CRITICAL | 0 | - |

### By Category

| Category | Count | Examples |
|----------|-------|----------|
| Phase transitions | 6 | Lines 533, 541, 543, 152, 155 |
| Constraint locking | 2 | Lines 526, 114 |
| STT events | 5 | Lines 172, 177, 184, 798 |
| LLM events | 12 | Lines 255, 300, 342, 357, 389, 404, 486, 489 |
| TTS events | 9 | Lines 595, 599, 629, 634, 639, 649, 662, 673 |
| Connection events | 8 | Lines 883, 899, 853, 866, 838, 897 |
| Timing metrics | 5 | Lines 427, 935, 943, 950 |
| Configuration | 8 | Lines 103, 108, 113, 123, 126, 752, 754, 798 |
| Error handling | 15 | Lines 357, 404, 489, 504, 649, 673, 697, 846, 868 |

---

## Next Steps

1. **Immediate (Sprint 1)**:
   - Add session_id/turn_number context to top 20 most critical log statements
   - Add JSON fallback chain logging in response_parser.py
   - Enhance phase transition logging with turn counts

2. **Short-term (Sprint 2)**:
   - Migrate to structured logging (JSON format)
   - Add STT timeout recovery details
   - Add TTS frame count metrics consistently

3. **Long-term (Sprint 3)**:
   - Implement centralized logging configuration
   - Add log aggregation (e.g., Elasticsearch, CloudWatch)
   - Create dashboards for real-time monitoring
   - Add log-based alerting for error patterns

---

**Audit Completed**: 2026-03-04
**Auditor**: Claude Code Agent
**Version**: 1.0
