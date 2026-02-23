"""Interview agent using LiveKit Agents 1.0 API with custom nodes."""

import logging
import uuid
from typing import AsyncIterable

from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, AgentServer, JobContext, WorkerOptions, llm, cli
from livekit.plugins import deepgram, openai, silero, anthropic

from ..config import AgentConfig
from ..models.session import InterviewSession, SessionState, InterviewPhase
from ..interview.phase_manager import PhaseManager
from ..interview.response_parser import ResponseParser

logger = logging.getLogger(__name__)


class InterviewAgent(Agent):
    """
    Custom Agent that conducts system design interviews.
    
    Uses LiveKit Agents 1.0 API with llm_node and tts_node overrides.
    """
    
    def __init__(self, config: AgentConfig, scenario: str):
        """
        Initialize interview agent.
        
        Args:
            config: Agent configuration
            scenario: Interview scenario (e.g., "Design a payment gateway")
        """
        # Minimal placeholder instructions - real instructions come from phase_manager.get_system_prompt()
        # injected in llm_node to prevent competing system prompts
        instructions = "You are a technical interviewer. Follow the system prompt provided in context."

        # Initialize parent Agent class
        super().__init__(instructions=instructions)
        
        self.config = config
        self.scenario = scenario
        
        # Create interview session (renamed to avoid collision with Agent.session property)
        session_id = str(uuid.uuid4())
        self.interview_session = InterviewSession(session_id=session_id, scenario=scenario)
        
        # Initialize interview engine components
        self.phase_manager = PhaseManager(scenario)
        self.response_parser = ResponseParser()
        
        # Track user input for history
        self.pending_user_input = None
        
        logger.info(f"Initialized InterviewAgent for scenario: {scenario}")
    
    async def on_enter(self):
        """Called when agent becomes active in session."""
        logger.info(f"Agent entering session for scenario: {self.scenario}")
        
        # Initial greeting - access session via self if available
        # Note: In LiveKit 1.4+, the pattern is to use session.generate_reply
        # For now, we'll handle the greeting in the entrypoint instead
        pass
    
    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        model_settings: agents.ModelSettings,
    ):
        """
        Custom LLM node - modifies chat context before LLM inference.
        
        This is where we:
        1. Record user input to conversation history
        2. Inject phase-aware system prompt with INTERVIEWER_BEHAVIOR rules
        3. Include locked constraints and recent history
        """
        # Get messages list (messages() is a method in LiveKit 1.4+)
        messages_list = chat_ctx.messages()
        
        # Record user's latest message (if present)
        if messages_list:
            latest_msg = messages_list[-1]
            if latest_msg.role == "user":
                # Extract text content
                user_text = ""
                for content in latest_msg.content:
                    if isinstance(content, str):
                        user_text += content
                    elif isinstance(content, llm.ChatText):
                        user_text += content.text
                
                if user_text:
                    self.interview_session.state.add_message("user", user_text)
                    logger.debug(f"Recorded user message: {user_text[:100]}...")
        
        # Build phase-aware system prompt
        system_prompt = self.phase_manager.get_system_prompt(self.interview_session.state)
        
        # Update chat context with interview-specific system prompt
        # In LiveKit 1.4+, we modify chat_ctx.items directly (it's a list)
        if chat_ctx.items and len(chat_ctx.items) > 0:
            # First item should be the system message - update it
            chat_ctx.items[0] = llm.ChatMessage(
                role="system",
                content=[system_prompt]  # content can be a list of strings
            )
        else:
            # No items yet, add system message
            chat_ctx.add_message(role="system", content=system_prompt)
        
        logger.debug(f"LLM node - Phase: {self.interview_session.state.phase.value}, Turn: {self.interview_session.state.phase_turn_count}")
        
        # Buffer the entire LLM response to parse JSON before streaming
        # This prevents raw JSON from leaking to the user
        # Trade-off: Removes streaming behavior but ensures clean output
        full_response = ""
        last_chunk_id = "parsed_response"  # Track last chunk ID explicitly
        
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            # Track chunk ID for later use
            if chunk.id:
                last_chunk_id = chunk.id
            
            # Accumulate text content only (interviews don't use tool calls)
            if chunk.delta and chunk.delta.content:
                full_response += chunk.delta.content
        
        # Parse the complete response
        spoken_text, new_phase, updated_constraints = self.response_parser.parse(full_response)
        
        # Update state before yielding (so it's ready for next turn)
        if updated_constraints:
            for key, value in updated_constraints.items():
                self.interview_session.state.lock_constraint(key, value)
                logger.info(f"Locked constraint: {key} = {value}")
        
        if new_phase:
            try:
                requested_phase = InterviewPhase(new_phase)
                if self.phase_manager.should_transition_phase(self.interview_session.state, requested_phase):
                    if self.interview_session.state.advance_phase(requested_phase):
                        logger.info(f"Phase transitioned: {self.interview_session.state.phase.value}")
                    else:
                        logger.warning(f"Phase transition blocked (monotonic): {new_phase}")
                else:
                    logger.debug(f"Phase transition not ready: {self.interview_session.state.phase.value} -> {new_phase}")
            except ValueError:
                logger.warning(f"Invalid phase in response: {new_phase}")
        
        # Record assistant message with clean spoken text
        self.interview_session.state.add_message("assistant", spoken_text)
        
        logger.debug(f"Parsed spoken text: {spoken_text[:100]}...")
        logger.info(f"State: Phase={self.interview_session.state.phase.value}, "
                   f"Turn={self.interview_session.state.phase_turn_count}, "
                   f"Constraints={len(self.interview_session.state.locked_constraints)}")
        
        # Yield ONLY the clean spoken text (no JSON, no internal fields)
        # Use explicitly tracked chunk ID
        yield llm.ChatChunk(
            id=last_chunk_id,
            delta=llm.ChoiceDelta(
                role="assistant",
                content=spoken_text
            )
        )
    
    async def tts_node(
        self,
        text: AsyncIterable[str],
        model_settings: agents.ModelSettings,
    ):
        """
        Custom TTS node - pass through clean text to TTS.
        
        Parsing is now done in llm_node, so we just stream the text directly to TTS.
        """
        # The text coming in has already been parsed and cleaned in llm_node
        # Just pass it through to default TTS
        async for audio_frame in Agent.default.tts_node(self, text, model_settings):
            yield audio_frame


async def entrypoint(ctx: JobContext):
    """
    Entrypoint for LiveKit agent.
    
    Called when a participant joins the room.
    """
    logger.info(f"Agent starting for room: {ctx.room.name}")
    
    # Load config
    from ..config import AgentConfig
    config = AgentConfig.from_env()
    
    # Get scenario from job metadata or use default
    # Note: metadata is a string, not a dict - parse safely
    scenario = "Design a URL shortener"
    if hasattr(ctx.job, 'metadata') and ctx.job.metadata:
        # Metadata is a string - use it directly if it looks like a scenario
        if isinstance(ctx.job.metadata, str) and len(ctx.job.metadata) > 5:
            scenario = ctx.job.metadata
    
    # Create interview agent
    interview_agent = InterviewAgent(config, scenario)
    
    # Create agent session
    session = AgentSession(
        stt=deepgram.STT(
            api_key=config.deepgram_api_key,
            model="nova-2"
        ),
        llm=anthropic.LLM(
            model=config.llm_model,
            api_key=config.anthropic_api_key,
        ),
        tts=openai.TTS(
            voice=config.tts_voice,
            api_key=config.openai_api_key,
        ),
        vad=silero.VAD.load(
            min_silence_duration=config.silence_threshold_ms / 1000.0,
        ),
    )
    
    # Start session with our custom agent
    await session.start(
        room=ctx.room,
        agent=interview_agent,
    )
    
    # Send initial greeting using session.generate_reply
    await session.generate_reply(
        instructions=f"Greet the candidate warmly. You are conducting a system design interview for: {scenario}. "
        "Introduce yourself briefly and ask if they're ready to begin."
    )
    
    logger.info("Interview session started")


def run_agent(config: AgentConfig, scenario: str):
    """
    Run the interview agent.
    
    Args:
        config: Agent configuration
        scenario: Interview scenario (currently unused - passed via job metadata)
    """
    # Create worker options with entrypoint as first positional arg
    worker_opts = WorkerOptions(
        entrypoint_fnc=entrypoint,
        ws_url=config.livekit_url,
        api_key=config.livekit_api_key,
        api_secret=config.livekit_api_secret,
    )
    
    # Run agent server (cli.run_app accepts WorkerOptions directly)
    cli.run_app(worker_opts)
