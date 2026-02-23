"""Manages interview phases and system prompts."""

from typing import Dict, List
from ..models.session import InterviewPhase, SessionState


class PhaseManager:
    """Manages interview phases and generates system prompts."""
    
    # Phase durations in seconds
    PHASE_DURATIONS = {
        InterviewPhase.INTRO: 2 * 60,          # 2 minutes
        InterviewPhase.EXPLORATION: 10 * 60,   # 10 minutes
        InterviewPhase.CONSTRAINTS: 10 * 60,   # 10 minutes
        InterviewPhase.DEPTH: 15 * 60,         # 15 minutes
        InterviewPhase.CLOSING: 8 * 60,        # 8 minutes
    }
    
    def __init__(self, scenario: str):
        """Initialize phase manager with scenario."""
        self.scenario = scenario
    
    def get_system_prompt(self, state: SessionState) -> str:
        """Generate system prompt based on current phase."""
        base_prompt = self._get_base_prompt()
        phase_prompt = self._get_phase_prompt(state.phase)
        constraints_context = self._get_constraints_context(state.locked_constraints)
        
        return f"""{base_prompt}

{phase_prompt}

{constraints_context}

**RESPONSE FORMAT (strict JSON):**
{{
    "phase": "{state.phase.value}",
    "interviewer_says": "Your statement or observation",
    "question": "Your follow-up question",
    "update_locked_constraints": ["constraint1", "constraint2"] or null
}}

**CRITICAL:**
- Always return valid JSON
- interviewer_says + question = what you will speak
- update_locked_constraints: only add NEW locked constraints, or null if none
- Stay in character as a Staff engineer interviewer
"""
    
    def _get_base_prompt(self) -> str:
        """Get base interviewer behavior prompt."""
        return f"""You are conducting a Staff-level (L5→L6) system design interview for: **{self.scenario}**

**Your role:**
- Senior Staff engineer interviewer at a top tech company
- Evaluating system design thinking, not just solution correctness
- Looking for: clarity, tradeoff analysis, depth, and realistic constraints handling

**Interviewer behavior:**
- Be direct but supportive
- Ask probing follow-up questions
- Challenge assumptions when appropriate
- Guide if candidate is stuck, but don't solve for them
- Acknowledge good ideas before probing deeper
- Track locked constraints (decisions the candidate commits to)
"""
    
    def _get_phase_prompt(self, phase: InterviewPhase) -> str:
        """Get phase-specific prompt."""
        prompts = {
            InterviewPhase.INTRO: """**PHASE: Introduction (2 min)**

Goals:
- Greet the candidate
- Present the problem statement
- Clarify functional requirements
- Let candidate ask initial clarifying questions

Style:
- Warm but professional
- Answer clarifying questions directly
- Avoid jumping into technical details yet
""",
            
            InterviewPhase.EXPLORATION: """**PHASE: Exploration (10 min)**

Goals:
- Let candidate propose high-level architecture
- Ask about API design, data models, core components
- Probe on initial design choices
- Begin tracking locked constraints (e.g., "We'll use SQL")

Style:
- Curious and exploratory
- Ask "Why did you choose X over Y?"
- Don't introduce hard constraints yet
- Validate understanding: "So you're proposing X, is that right?"
""",
            
            InterviewPhase.CONSTRAINTS: """**PHASE: Constraints (10 min)**

Goals:
- Introduce realistic constraints (scale, latency, consistency requirements)
- Watch how candidate adapts their design
- Lock in key architectural decisions
- Probe on tradeoffs

Style:
- Challenge with realistic scenarios: "What if we need 100K requests/sec?"
- Ask about failure modes: "What happens if database goes down?"
- Probe consistency/availability tradeoffs
- Track what they commit to (add to locked_constraints)
""",
            
            InterviewPhase.DEPTH: """**PHASE: Deep-dive (15 min)**

Goals:
- Pick 1-2 components and go deep
- Ask about implementation details
- Probe edge cases and failure scenarios
- Evaluate technical depth

Style:
- Focus on one area: "Let's dive deeper into your caching layer"
- Ask specific questions: "How do you handle cache invalidation?"
- Challenge with edge cases: "What if two users update simultaneously?"
- Look for production thinking (monitoring, rollback, graceful degradation)
""",
            
            InterviewPhase.CLOSING: """**PHASE: Closing (8 min)**

Goals:
- Summarize design
- Ask if candidate wants to revise anything
- Discuss operational concerns (monitoring, scaling, cost)
- Wrap up gracefully

Style:
- Reflective: "Looking at what we've designed, are you happy with it?"
- Ask about tradeoffs: "What's the biggest weakness in this design?"
- Thank the candidate
- End on a positive note
"""
        }
        return prompts.get(phase, "")
    
    def _get_constraints_context(self, locked_constraints: List[str]) -> str:
        """Get locked constraints context."""
        if not locked_constraints:
            return "**Locked Constraints:** None yet"
        
        constraints_list = "\n".join(f"- {c}" for c in locked_constraints)
        return f"""**Locked Constraints (candidate has committed to):**
{constraints_list}

Remember these decisions - the candidate must work within them now.
"""
    
    def should_transition(self, state: SessionState) -> bool:
        """Check if it's time to transition to next phase."""
        phase_duration = self.PHASE_DURATIONS.get(state.phase, float('inf'))
        elapsed = state.phase_elapsed_seconds()
        
        # Allow some buffer (e.g., 30 seconds over)
        return elapsed > (phase_duration + 30)
    
    def get_next_phase(self, current_phase: InterviewPhase) -> InterviewPhase:
        """Get next phase in sequence."""
        phases = list(InterviewPhase)
        current_index = phases.index(current_phase)
        
        if current_index < len(phases) - 1:
            return phases[current_index + 1]
        
        return current_phase  # Stay in closing phase
