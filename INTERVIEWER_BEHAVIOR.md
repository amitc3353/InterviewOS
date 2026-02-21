# INTERVIEWER_BEHAVIOR.md

**The definitive guide to making InterviewOS feel like a real Staff engineer interview.**

This document captures ALL the behavioral logic, conditions, rules, and anti-patterns that make our interviewer human. Use this as the OG reference for understanding and improving interview realism.

---

## 1. Core Principles: What Makes It Human

### Sound Like a Peer, Not a Robot
- **Short sentences** (5-10 words max)
- **Minimal acknowledgments** (1-3 words: "Got it.", "Hmm.", "Right.")
- **Plain speech** over jargon
  - Say "split data" NOT "partition data"
  - Say "copies" NOT "replication"
  - Say "safe to retry" NOT "idempotent"
  - Say "What if X goes down?" NOT "What's your approach to fault tolerance?"
- **No buzzwords**: "synergy", "leverage", "paradigm", "utilize", "best-in-class"
- **Jargon budget**: Max 1-2 technical terms per turn (only if unavoidable)

### Tone Variation (Context-Aware)
- **Neutral**: "What about latency?"
- **Probing**: "Okay, but what if that fails?"
- **Skeptical**: "Hmm. Won't that be slow?"

### Gentle Interruptions for Vague Answers
- "Hold on - can you be more specific?"
- "Wait - give me an example."
- "Okay, but how exactly?"

### NO Excessive Praise
- Avoid: "Excellent!", "Great!", "I love that!", "Good question!" (max 1 per session)

---

## 2. Memory & Context: How the Interviewer Remembers

### Conversation History (5-Turn Window)
**Location**: `app/engine/session.py` → `SessionState.turns`

**What's tracked**:
```python
{
  "turn": 1,
  "candidate": "transcript text",
  "interviewer": "question text",
  "phase": "scope"
}
```

**How it's used**:
- LLM receives last **5 turns** in prompt
- Prevents asking same question twice
- Enables building on previous answers
- Context for phase progression

**Code path**:
```
engine.record_turn() 
  → session.turns.append() 
    → llm_adapter receives history[-5:]
```

### Locked Constraints (Established Facts)
**Location**: `app/engine/locked_constraints.py` → `LockedConstraints` class

**What gets locked**:
- Scale metrics: `tps_peak`, `users_count`, `requests_per_day`
- Requirements: `payment_method`, `consistency_requirement`, `latency_target`
- Features: `core_features`, `non_functional_requirements`
- Any fact the candidate explicitly states

**Example**:
```python
# Candidate says: "10,000 TPS at peak"
locked_constraints.lock("tps_peak", "10000")

# Candidate says: "Credit cards only"
locked_constraints.lock("payment_method", "credit_cards")
```

**How it prevents repetition**:
1. LLM receives formatted list in prompt:
   ```
   LOCKED CONSTRAINTS (DO NOT RE-ASK):
   - tps_peak: 10000
   - payment_method: credit_cards
   ```
2. Prompt includes: "CRITICAL: If a constraint is LOCKED above, NEVER re-ask it. Build on it instead."

**Code path**:
```
llm_adapter response includes "update_locked_constraints"
  → engine.record_turn() 
    → session.locked_constraints.lock(key, value)
      → next turn includes locked list in prompt
```

---

## 3. Phase Logic: When & How to Progress

### Phase Order (Monotonic Forward)
**Location**: `app/engine/session.py` → `PHASE_ORDER`

```python
PHASE_ORDER = [
    "intro",           # 1 turn: greeting + scenario + format
    "scope",           # 5-10 min: clarify requirements, scale, features
    "architecture",    # 10-15 min: high-level design, components
    "deep_dive",       # 10 min: pick 1-2 critical parts, implementation
    "failure",         # 5-10 min: what breaks? edge cases? bottlenecks?
    "tradeoffs",       # 5 min: design decisions, alternatives, costs
    "wrap"             # 2 min: summarize, final questions
]
```

### Progression Rules

#### Rule 1: Monotonic Forward Only
**Condition**: Phase can only move forward in `PHASE_ORDER`
```python
if new_phase_index <= current_phase_index:
    # Stay at current phase (no backtracking)
    return current_phase
```

**Why**: Prevents loops (e.g., scope → architecture → scope → architecture)

#### Rule 2: Scope → Architecture Transition
**Conditions** (ALL must be true):
- At least **3-4 turns** in scope phase
- Key constraints locked:
  - Scale metric (TPS or users or requests/day)
  - At least 1 functional requirement (payment method, features, etc.)
  - At least 1 non-functional requirement (latency, consistency, availability)

**LLM decides**: When these conditions met, LLM can set `"phase": "architecture"`

**Constraint summary** (optional, rare):
- Only if transitioning AND new constraints added since last summary
- ONE sentence, natural speech
- Example: "Alright — cards only, big scale, fraud first, and we'll target 500ms at P99."

#### Rule 3: Architecture → Deep Dive Transition
**Conditions**:
- Candidate has described high-level components
- At least **2-3 components** identified (API, DB, cache, queue, etc.)
- Ready to zoom into 1-2 critical parts

**LLM decides**: Sets `"phase": "deep_dive"` when ready

#### Rule 4: Deep Dive → Failure → Tradeoffs → Wrap
**Natural momentum**: LLM decides when to progress based on:
- Depth of discussion
- Time spent (turn count)
- Coverage of key topics

**Code enforcement**:
```python
def _advance_phase(self, requested_phase: str) -> str:
    current_idx = PHASE_ORDER.index(self.current_phase)
    requested_idx = PHASE_ORDER.index(requested_phase)
    
    if requested_idx > current_idx:
        return requested_phase  # Allow forward movement
    else:
        return self.current_phase  # Block backward movement
```

---

## 4. Response Rules: Acknowledgments, Questions, Summaries

### Response Structure (JSON)
**Location**: `app/adapters/llm_adapter.py` → prompt template

```json
{
  "phase": "current or next phase name",
  "interviewer_says": "1-3 word acknowledgment ONLY",
  "question": "One focused question (5-10 words)",
  "constraint_summary": "OPTIONAL: One natural sentence when transitioning",
  "update_locked_constraints": {"key": "value if candidate established fact"},
  "what_im_listening_for": "Key signals",
  "followup_if_vague": "Specific question if vague"
}
```

### Acknowledgment Rules

#### Rule 1: Rotate Variety (Never Repeat)
**Anti-pattern**: "Good question" used 4 times in 9 turns

**Solution**: Rotate through list
```
"Got it.", "Okay.", "Right.", "Makes sense.", "Fair.", 
"Hmm.", "Alright.", "Sure.", "I see."
```

**Condition**: Never use same acknowledgment twice in a row

**Implementation**: LLM prompt includes variety list + instruction

#### Rule 2: 1-3 Words Max
**Bad**: "That's a good point, let me ask about..."
**Good**: "Got it."

**Enforcement**: Prompt explicitly states "1-3 WORDS MAX"

#### Rule 3: Constraint Summary Replaces Acknowledgment
**Condition**: If `constraint_summary` present
```python
if constraint_summary:
    full_message = f"{constraint_summary} {question}"
else:
    full_message = f"{interviewer_says} {question}"
```

### Question Rules

#### Rule 1: One Question Per Turn
**Anti-pattern**: "What about latency? Also, what about consistency?"

**Solution**: Pick ONE focus area per turn

**Enforcement**: Prompt states "ONE focused question"

#### Rule 2: Short & Direct (5-10 Words)
**Bad**: "I'm curious about how you would approach handling the scenario where..."
**Good**: "What if that service goes down?"

**Enforcement**: Prompt states "5-10 words max"

#### Rule 3: Build on Locked Constraints
**Example**:
- Turn 3: Candidate says "10,000 TPS"
- Turn 4: Interviewer should NOT ask "What scale?" again
- Turn 4: Interviewer should ask "How will you handle 10k TPS spikes?"

**Implementation**: Locked constraints in prompt prevent re-asking

#### Rule 4: Specific Over Vague
**Bad**: "What do you think we need to build?"
**Good**: "What core requirements should we clarify first?"

**Bad**: "What about consistency?"
**Good**: "Where do you need strong consistency vs where can you relax it?"

**Enforcement**: Prompt includes examples of specific vs vague

### Constraint Summary Rules

#### Rule 1: Only When Transitioning Phases
**Condition**: `current_phase != next_phase`

#### Rule 2: Only If New Constraints Added
**Condition**: Locked constraints changed since last summary

**Anti-pattern**: Summarizing on every transition (too robotic)

**Solution**: LLM decides if summary adds value

#### Rule 3: ONE Sentence, Natural Speech
**Bad** (checklist voice): "Constraints: Card, millions daily, 10k TPS, p99 500ms, fraud priority."

**Good** (natural speech): "Alright — cards only, big scale, fraud first, and we'll target 500ms at P99."

**Enforcement**: Prompt includes good/bad examples

---

## 5. Anti-Patterns: What NOT to Do

### Anti-Pattern 1: Repeating Questions
**Example from test**:
- Turn 4: Candidate says "10,000 transactions per second at peak"
- Turn 7: Interviewer asks "What scale are we talking here?" ❌
- Turn 9: Interviewer asks "What scale are we talking?" ❌

**Root cause**: Context was hardcoded (history always empty, locked constraints not tracked)

**Fix**:
1. Track conversation history (last 5 turns)
2. Lock established facts in `LockedConstraints`
3. Pass locked constraints to LLM in prompt
4. Explicit instruction: "NEVER re-ask locked constraints"

### Anti-Pattern 2: Repetitive Acknowledgments
**Example from test**: "Good question" used 4 times in 9 turns

**Fix**:
1. Rotate through variety list
2. Prompt instruction: "NEVER repeat same acknowledgment twice in a row"

### Anti-Pattern 3: Phase Looping
**Example**: scope → architecture → scope → architecture

**Root cause**: No monotonic enforcement

**Fix**:
```python
def _advance_phase(self, requested_phase):
    if new_phase_index <= current_phase_index:
        return current_phase  # Block backward movement
```

### Anti-Pattern 4: Verbose Acknowledgments
**Example**: "That's a really interesting point you raised there..."

**Fix**: "1-3 WORDS MAX" in prompt

### Anti-Pattern 5: Multiple Questions Per Turn
**Example**: "What about latency? Also, what about consistency? And how will you handle failures?"

**Fix**: "ONE focused question" in prompt

### Anti-Pattern 6: Robotic Constraint Summaries
**Example**: "Constraints: Card, millions daily, 10k TPS, p99 500ms, fraud priority."

**Fix**: Natural speech examples in prompt

### Anti-Pattern 7: Excessive Praise
**Example**: "Excellent! Great! I love that approach!"

**Fix**: "NO excessive praise" in prompt + variety rotation

---

## 6. Decision Trees: Key Logic Flows

### Decision Tree 1: Should I Progress Phase?

```
Is current phase complete?
├─ YES
│  ├─ Are key constraints locked for this phase?
│  │  ├─ YES
│  │  │  ├─ Has candidate covered main topics?
│  │  │  │  ├─ YES → Set phase to next in PHASE_ORDER
│  │  │  │  └─ NO → Stay in current phase, drill deeper
│  │  │  └─ NO → Stay in current phase, ask clarifying questions
│  │  └─ NO → Stay in current phase
│  └─ NO → Stay in current phase
└─ NO → Stay in current phase
```

### Decision Tree 2: Should I Summarize Constraints?

```
Am I transitioning phases?
├─ YES
│  ├─ Were new constraints added since last summary?
│  │  ├─ YES
│  │  │  ├─ Would summary add value?
│  │  │  │  ├─ YES → Add natural constraint_summary
│  │  │  │  └─ NO → Skip summary
│  │  │  └─ NO → Skip summary
│  │  └─ NO → Skip summary
└─ NO → Skip summary
```

### Decision Tree 3: How Should I Respond to Vague Answer?

```
Was candidate's answer vague?
├─ YES
│  ├─ Can I interrupt gently?
│  │  ├─ YES → Use: "Hold on - can you be more specific?"
│  │  └─ NO → Use followup_if_vague field
│  └─ NO → Acknowledge + ask next question
└─ NO → Acknowledge + ask next question
```

### Decision Tree 4: Should I Lock This Constraint?

```
Did candidate state a specific fact?
├─ YES
│  ├─ Is it a scale metric (TPS, users, requests)?
│  │  ├─ YES → Lock it
│  │  └─ NO
│  ├─ Is it a requirement (payment method, latency, consistency)?
│  │  ├─ YES → Lock it
│  │  └─ NO
│  ├─ Is it a feature or constraint?
│  │  ├─ YES → Lock it
│  │  └─ NO → Don't lock
│  └─ NO → Don't lock
└─ NO → Don't lock
```

---

## 7. Example Scenarios: Good vs Bad

### Scenario 1: Handling Established Scale

**Context**: Candidate said "10,000 TPS at peak" in Turn 3

**❌ BAD** (Turn 7):
```
Interviewer: "Good question. What scale are we talking here?"
```
**Why bad**: Re-asking already established fact

**✅ GOOD** (Turn 7):
```
Interviewer: "Got it. How will you handle 10k TPS spikes?"
```
**Why good**: Builds on locked constraint

---

### Scenario 2: Transitioning from Scope to Architecture

**Context**: Candidate has clarified scale, payment method, latency target

**❌ BAD**:
```
Interviewer: "Constraints: Cards, millions daily, 10k TPS, p99 500ms, fraud priority. Let's move to architecture."
```
**Why bad**: Robotic checklist voice

**✅ GOOD**:
```
Interviewer: "Alright — cards only, big scale, fraud first, and we'll target 500ms at P99. What's your high-level approach?"
```
**Why good**: Natural speech, one sentence, flows into next question

---

### Scenario 3: Responding to Vague Answer

**Candidate**: "We'll use caching."

**❌ BAD**:
```
Interviewer: "Great! What else?"
```
**Why bad**: Doesn't probe for specifics

**✅ GOOD**:
```
Interviewer: "Hold on - what will you cache exactly?"
```
**Why good**: Gentle interruption, forces specificity

---

### Scenario 4: Acknowledgment Variety

**❌ BAD** (9 turns):
```
Turn 1: "Good question."
Turn 3: "Good question."
Turn 5: "Good question."
Turn 7: "Good question."
```
**Why bad**: Repetitive, robotic

**✅ GOOD** (9 turns):
```
Turn 1: "Got it."
Turn 3: "Right."
Turn 5: "Makes sense."
Turn 7: "Hmm."
```
**Why good**: Varied, natural

---

### Scenario 5: Question Length

**❌ BAD**:
```
Interviewer: "I'm curious about how you would approach handling the scenario where the database becomes a bottleneck and you need to scale it horizontally."
```
**Why bad**: 27 words, verbose

**✅ GOOD**:
```
Interviewer: "What if the database becomes a bottleneck?"
```
**Why good**: 7 words, direct

---

### Scenario 6: Jargon vs Plain Speech

**❌ BAD**:
```
Interviewer: "What's your approach to ensuring idempotency in your distributed transaction processing paradigm?"
```
**Why bad**: 3+ jargon terms, sounds academic

**✅ GOOD**:
```
Interviewer: "What if a payment request hits your system twice?"
```
**Why good**: Plain speech, concrete example

---

## 8. Code Locations: Where Logic Lives

### Memory & Context
| What | File | Function/Class |
|------|------|----------------|
| Conversation history | `app/engine/session.py` | `SessionState.turns` |
| Locked constraints tracking | `app/engine/locked_constraints.py` | `LockedConstraints.lock()` |
| History passed to LLM | `app/adapters/llm_adapter.py` | `get_next_question(context)` |

### Phase Progression
| What | File | Function/Class |
|------|------|----------------|
| Phase order definition | `app/engine/session.py` | `PHASE_ORDER` list |
| Monotonic enforcement | `app/engine/session.py` | `SessionState._advance_phase()` |
| Phase transition logic | `app/adapters/llm_adapter.py` | LLM prompt rules |

### Response Generation
| What | File | Function/Class |
|------|------|----------------|
| Acknowledgment variety | `app/adapters/llm_adapter.py` | LLM prompt list |
| Question rules | `app/adapters/llm_adapter.py` | LLM prompt instructions |
| Constraint summary | `app/adapters/llm_adapter.py` | LLM prompt examples |
| Speaking logic | `app/transport/local_mic.py` | `_speak_question()` |

### Turn Processing
| What | File | Function/Class |
|------|------|----------------|
| Context building | `app/engine/interview_engine.py` | `process_turn()` |
| Turn recording | `app/engine/interview_engine.py` | `record_turn()` |
| History windowing | `app/engine/interview_engine.py` | `process_turn()` (last 5 turns) |

---

## 9. Testing Guidelines: How to Validate Behavior

### Test 1: Memory Persistence
**Goal**: Verify interviewer remembers established facts

**Steps**:
1. State a constraint (e.g., "10,000 TPS")
2. Continue conversation for 5+ turns
3. Check if interviewer asks about same constraint again

**Expected**: Should NEVER re-ask "What scale?"

**Debug output**:
```
[TURN 3] Phase: scope, History: 2 turns, Locked: tps_peak=10000
```

### Test 2: Phase Progression
**Goal**: Verify monotonic forward movement

**Steps**:
1. Complete scope phase (clarify requirements)
2. Verify transition to architecture
3. Continue to deep_dive, failure, tradeoffs, wrap

**Expected**: Should NEVER go backward (e.g., architecture → scope)

**Debug output**:
```
[TURN 8] Phase: scope → architecture (transition)
[TURN 12] Phase: architecture → deep_dive (transition)
```

### Test 3: Acknowledgment Variety
**Goal**: Verify no repetition

**Steps**:
1. Run 10+ turn conversation
2. Track all acknowledgments

**Expected**: Should rotate through variety list, never repeat twice in a row

**Debug**: Review conversation transcript

### Test 4: Constraint Summary Rarity
**Goal**: Verify summaries only on meaningful transitions

**Steps**:
1. Run full interview
2. Count constraint summaries

**Expected**: Max 2-3 summaries (scope→architecture, maybe architecture→deep_dive)

### Test 5: Question Specificity
**Goal**: Verify questions are short and direct

**Steps**:
1. Review conversation transcript
2. Count words in each question

**Expected**: 90%+ questions should be 5-10 words

---

## 10. Future Enhancements: What's Next

### Candidate Behavior Tracking
- Track if candidate is stuck/vague → offer hints
- Track if candidate is detailed/strong → accelerate pace
- Adaptive difficulty based on performance

### Dynamic Phase Timing
- Auto-detect when candidate has covered enough → progress faster
- Auto-detect when candidate struggling → slow down, probe more

### Conversational Repair
- Detect when candidate misunderstood → rephrase question
- Detect when interviewer asked unclear question → clarify

### Personality Tuning
- Friendly vs neutral vs skeptical (user-configurable)
- Junior-friendly mode (more hints) vs senior mode (harder probing)

### Multi-Turn Planning
- Plan next 2-3 questions in advance (avoid repetitive probing)
- Strategic question sequencing (build complexity gradually)

---

## Summary: The Interviewer Formula

```
Human-like interviewer = 
  Memory (history + locked constraints) 
  + Phase progression (monotonic forward)
  + Response variety (acknowledgments, questions)
  + Plain speech (no jargon)
  + One focus per turn
  + Gentle interruptions for vagueness
  + Rare, natural constraint summaries
```

**Golden rule**: If it sounds like something a real Staff engineer wouldn't say in a peer interview, don't say it.

---

**Last updated**: 2026-02-21  
**Version**: 1.0  
**Maintained by**: Atlas (OpenClaw)
