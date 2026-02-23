"""Interview agent using LiveKit Agents 1.0 API with custom nodes."""

import logging
import uuid
from typing import AsyncIterable

from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, llm, cli
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
        super().__init__()
        
        self.config = config
        self.scenario = scenario
        
        # Create session
        session_id = str(uuid.uuid4())
        self.session = InterviewSession(session_id=session_id, scenario=scenario)
        
        # Initialize interview engine components
        self.phase_manager = PhaseManager(scenario)
        self.response_parser = ResponseParser()
        
        # Track user input for history
        self.pending_user_input = None
        
        logger.info(f"Initialized InterviewAgent for scenario: {scenario}")
    
    async def on_enter(self):
        """Called when agent becomes active in session."""
        logger.info(f"Agent entering session for scenario: {self.scenario}")
        
        # Initial greeting
        greeting = f"Hello! I'm ready to begin your system design interview for: {self.scenario}. Are you ready to start?"
        await self.say(greeting)
    
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
        # Record user's latest message (if present)
        if chat_ctx.messages:
            latest_msg = chat_ctx.messages[-1]
            if latest_msg.role == "user":
                # Extract text content
                user_text = ""
                for content in latest_msg.content:
                    if isinstance(content, llm.ChatText):
                        user_text += content.text
                
                if user_text:
                    self.session.state.add_message("user", user_text)
                    logger.debug(f"Recorded user message: {user_text[:100]}...")
        
        # Build phase-aware system prompt
        system_prompt = self.phase_manager.get_system_prompt(self.session.state)
        
        # Update chat context with interview-specific system prompt
        chat_ctx.messages[0] = llm.ChatMessage(
            role="system",
            content=[llm.ChatText(text=system_prompt)]
        )
        
        logger.debug(f"LLM node - Phase: {self.session.state.phase.value}, Turn: {self.session.state.phase_turn_count}")
        
        # Use default LLM implementation
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            yield chunk
    
    async def tts_node(
        self,
        text: AsyncIterable[str],
        model_settings: agents.ModelSettings,
    ):
        """
        Custom TTS node - processes LLM output before speech synthesis.
        
        This is where we:
        1. Collect full LLM response
        2. Parse JSON to extract spoken text, phase updates, and constraint updates
        3. Update session state (locked constraints, phase transitions)
        4. Return only the spoken text for TTS
        """
        # Collect full response from LLM
        full_response = ""
        async for text_chunk in text:
            full_response += text_chunk
        
        logger.debug(f"Raw LLM response: {full_response[:200]}...")
        
        # Parse response
        spoken_text, new_phase, updated_constraints = self.response_parser.parse(full_response)
        
        # Update locked constraints
        if updated_constraints:
            for key, value in updated_constraints.items():
                self.session.state.lock_constraint(key, value)
                logger.info(f"Locked constraint: {key} = {value}")
        
        # Handle phase transition
        if new_phase:
            try:
                requested_phase = InterviewPhase(new_phase)
                
                # Check if transition is allowed (content + time-based)
                if self.phase_manager.should_transition_phase(self.session.state, requested_phase):
                    if self.session.state.advance_phase(requested_phase):
                        logger.info(f"Phase transitioned: {self.session.state.phase.value}")
                    else:
                        logger.warning(f"Phase transition blocked (monotonic): {new_phase}")
                else:
                    logger.debug(f"Phase transition not ready: {self.session.state.phase.value} -> {new_phase}")
            except ValueError:
                logger.warning(f"Invalid phase in response: {new_phase}")
        
        # Record assistant message
        self.session.state.add_message("assistant", spoken_text)
        
        logger.debug(f"Spoken text: {spoken_text[:100]}...")
        logger.info(f"State: Phase={self.session.state.phase.value}, "
                   f"Turn={self.session.state.phase_turn_count}, "
                   f"Constraints={len(self.session.state.locked_constraints)}")
        
        # Create async generator from spoken text and pass to default TTS
        async def text_stream():
            yield spoken_text
        
        # Use default TTS implementation
        async for audio_frame in Agent.default.tts_node(self, text_stream(), model_settings):
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
        # Models
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
        
        # VAD configuration
        vad=silero.VAD.load(
            min_silence_duration=config.silence_threshold_ms / 1000.0,
            min_speech_duration=0.2,  # 200ms minimum speech
        ),
        
        # Chat context
        chat_ctx=llm.ChatContext(),
    )
    
    # Start session with our custom agent
    await session.start(ctx.room, interview_agent)
    
    logger.info("Interview session started")


def run_agent(config: AgentConfig, scenario: str):
    """
    Run the interview agent.
    
    Args:
        config: Agent configuration
        scenario: Interview scenario
    """
    # Create worker
    worker = agents.Worker(
        entrypoint_fnc=entrypoint,
        opts=WorkerOptions(
            api_key=config.livekit_api_key,
            api_secret=config.livekit_api_secret,
            ws_url=config.livekit_url,
        ),
    )
    
    # Run worker (blocks until stopped)
    cli.run_app(worker)
