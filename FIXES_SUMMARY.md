# Fixes Applied - 2026-02-22

**All critical and medium issues from code review have been fixed.**

---

## Critical Issues Fixed ✅

### Issue #1: LiveKit API was wrong
**Problem:** Used non-existent `.on()` event listeners (`assistant.llm.on("before_llm_cb", ...`)  
**Fix:**
- Rewrote using LiveKit Agents 1.0 API
- Created `InterviewAgent` subclass of `Agent`
- Override `llm_node()` and `tts_node()` methods
- Call `Agent.default.llm_node()` and `Agent.default.tts_node()` for default behavior

**Files changed:**
- `backend/agents/interview_agent.py` (complete rewrite)

---

### Issue #2: Phase structure didn't match spec
**Problem:** Built 5 phases (intro → exploration → constraints → depth → closing) instead of spec's 7 phases  
**Fix:**
- Changed to correct 7-phase structure: **intro → scope → architecture → deep_dive → failure → tradeoffs → wrap**
- Added `PHASE_ORDER` list for monotonic enforcement
- Updated all phase logic to match INTERVIEWER_BEHAVIOR.md exactly

**Files changed:**
- `backend/models/session.py` (`InterviewPhase` enum, `PHASE_ORDER`)
- `backend/interview/phase_manager.py` (all phase instructions)

---

### Issue #3: Locked constraints wrong data structure
**Problem:** Stored as `List[str]` instead of `Dict[str, str]`  
**Fix:**
- Changed to `Dict[str, str]` for key-value pairs
- Added `lock_constraint(key, value)` method
- Added `has_constraint_category(category)` helper for checking constraint types

**Files changed:**
- `backend/models/session.py` (`SessionState.locked_constraints`)

---

### Issue #4: Phase transitions time-only (no content checks)
**Problem:** Only checked `elapsed > phase_duration`, advanced even without requirements met  
**Fix:**
- Added `should_transition_scope_to_architecture()` with content checks:
  - At least 3-4 turns in scope
  - At least 1 scale metric locked
  - At least 1 functional requirement locked
  - At least 1 non-functional requirement locked
- Added `should_transition_phase()` combining time + content checks
- Phase manager now validates transitions before allowing

**Files changed:**
- `backend/interview/phase_manager.py` (`should_transition_scope_to_architecture()`, `should_transition_phase()`)
- `backend/agents/interview_agent.py` (calls `should_transition_phase()` before advancing)

---

### Issue #5: No conversation history in prompt
**Problem:** Stored messages but never passed to LLM  
**Fix:**
- Added `get_recent_history(window_size=5)` method to return last N messages
- Phase manager formats recent history and includes in system prompt
- Prevents repeating questions (Anti-Pattern #1)

**Files changed:**
- `backend/models/session.py` (`get_recent_history()`)
- `backend/interview/phase_manager.py` (`_get_recent_history_context()`)

---

### Issue #6: No monotonic phase enforcement
**Problem:** `advance_phase()` just set phase directly, no guard against backward movement  
**Fix:**
- Added monotonic check in `advance_phase()`:
  ```python
  if new_phase_index <= current_phase_index:
      return False  # Block backward movement
  ```
- Returns `True` if phase changed, `False` if blocked

**Files changed:**
- `backend/models/session.py` (`advance_phase()`)

---

## Medium Issues Fixed ✅

### Issue #7: System prompt missing INTERVIEWER_BEHAVIOR rules
**Problem:** Generic prompt ("be supportive") instead of specific behavioral rules  
**Fix:**
- Added complete `_get_interviewer_behavior_rules()` method with:
  - All 9 core behavior rules (short sentences, plain speech, jargon budget, etc.)
  - Acknowledgment variety list
  - Tone examples (neutral, probing, skeptical)
  - Good/bad examples for questions, acknowledgments, summaries
- Full prompt includes: behavior rules + phase instructions + locked constraints + recent history + response format with examples

**Files changed:**
- `backend/interview/phase_manager.py` (complete system prompt overhaul)

---

### Issue #8: No turn counting
**Problem:** No per-phase turn counter for transition logic  
**Fix:**
- Added `phase_turn_count` (resets on phase transition)
- Added `total_turn_count` (session-wide)
- Added `last_constraint_summary_turn` (tracks when we last summarized)
- Incremented in `add_message()` when role is "user"

**Files changed:**
- `backend/models/session.py` (`SessionState` fields)

---

### Issue #9: constraint_summary field not handled
**Problem:** Response parser ignored `constraint_summary` field  
**Fix:**
- `_build_spoken_text()` now checks for `constraint_summary` first
- Priority: constraint_summary > interviewer_says > just question
- Properly implements phase transition summaries

**Files changed:**
- `backend/interview/response_parser.py` (`_build_spoken_text()`)
- `backend/interview/phase_manager.py` (response format includes `constraint_summary` with examples)

---

### Issue #10: User messages not recorded
**Problem:** Only assistant messages were captured  
**Fix:**
- `llm_node()` now extracts user's latest message from `chat_ctx.messages`
- Records user input via `add_message("user", text)` before LLM inference
- Conversation history now complete (both sides)

**Files changed:**
- `backend/agents/interview_agent.py` (`llm_node()`)

---

## Minor Issues Fixed ✅

### Issue #11: Provider config fields decorative
**Problem:** `stt_provider`, `llm_provider`, `tts_provider` fields exist but aren't used  
**Fix:**
- Added comment noting they're placeholders
- Added TODO to wire them properly
- Acknowledged as known limitation

**Files changed:**
- `backend/config.py` (added note)

---

### Issue #12: Hardcoded default scenario
**Problem:** "Design a URL shortener" hardcoded  
**Fix:**
- Now accepts scenario from command line: `python backend/run_interview.py "Design a payment gateway"`
- Falls back to default if not provided

**Files changed:**
- `backend/run_interview.py` (parses all args as scenario)

---

### Issue #13: .gitignore check
**Problem:** Concern about .env security  
**Fix:**
- Confirmed `.env` is in `.gitignore` (line 2)
- API keys are safe and not committed

**Files changed:**
- None (already correct)

---

## New Files Added

1. **INTERVIEWER_BEHAVIOR.md** - Definitive behavioral spec (saved to repo for reference)
2. **NEXT_STEPS_REALTIME.md** - Implementation plan (planning doc, not in PR)
3. **REALTIME_VOICE_PLAN.md** - Technical deep-dive (planning doc, not in PR)

---

## Testing Checklist

Before merging, validate:

- [ ] Code compiles (no syntax errors)
- [ ] Test script passes: `python backend/test_setup.py`
- [ ] Dependencies install: `pip install -r requirements.txt`
- [ ] Agent starts: `python backend/run_interview.py`
- [ ] 7 phases present in code (intro, scope, architecture, deep_dive, failure, tradeoffs, wrap)
- [ ] Locked constraints are Dict (not List)
- [ ] Phase transitions check content (not just time)
- [ ] Conversation history tracked (last 5 turns in prompt)
- [ ] Monotonic phase enforcement works
- [ ] Full INTERVIEWER_BEHAVIOR rules in prompt

---

## What's Next

1. **Test end-to-end** with LiveKit client connection
2. **Validate conversation quality** (does it sound human?)
3. **Tune VAD sensitivity** for your environment
4. **Test phase transitions** (do they happen at right times?)
5. **Verify constraint tracking** (are facts locked and remembered?)

---

## Summary

**All 13 issues addressed:**
- 6 critical (blocking) ✅
- 4 medium (should fix) ✅
- 3 minor (noted) ✅

**Code is now:**
- Using correct LiveKit Agents 1.0 API
- Following INTERVIEWER_BEHAVIOR.md spec exactly
- Properly tracking state (constraints, history, turns)
- Validating phase transitions (content + time)
- Including full behavioral rules in prompts

**Ready for testing.**
