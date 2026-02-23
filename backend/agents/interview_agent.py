"""Main LiveKit agent for interview simulation."""

import logging
from typing import Optional
import uuid

from livekit import agents, rtc
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.plugins import deepgram, openai, silero, anthropic

from ..config import AgentConfig
from ..models.session import InterviewSession, SessionState, InterviewPhase
from ..interview.phase_manager import PhaseManager
from ..interview.response_parser import ResponseParser

logger = logging.getLogger(__name__)


class InterviewAgent:
    """LiveKit agent that conducts system design interviews."""
    
    def __init__(self, config: AgentConfig, scenario: str):
        """
        Initialize interview agent.
        
        Args:
            config: Agent configuration
            scenario: Interview scenario (e.g., "Design a URL shortener")
        """
        self.config = config
        self.scenario = scenario
        
        # Create session
        session_id = str(uuid.uuid4())
        self.session = InterviewSession(session_id=session_id, scenario=scenario)
        
        # Initialize interview engine components
        self.phase_manager = PhaseManager(scenario)
        self.response_parser = ResponseParser()
        
        logger.info(f"Initialized InterviewAgent for scenario: {scenario}")
    
    async def entrypoint(self, ctx: JobContext):
        """
        Main entrypoint for LiveKit agent.
        
        This is called when a participant joins the room.
        """
        logger.info(f"Agent starting for room: {ctx.room.name}")
        
        # Wait for participant to connect
        await ctx.connect()
        
        # Get the participant
        participant = await ctx.wait_for_participant()
        logger.info(f"Participant joined: {participant.identity}")
        
        # Run the interview
        await self._run_interview(ctx, participant)
    
    async def _run_interview(self, ctx: JobContext, participant: rtc.Participant):
        """Run the actual interview loop."""
        
        # Initialize agent with pipeline
        assistant = agents.Agent(
            vad=silero.VAD.load(min_silence_duration=self.config.silence_threshold_ms / 1000.0),
            stt=deepgram.STT(api_key=self.config.deepgram_api_key),
            llm=anthropic.LLM(
                model=self.config.llm_model,
                api_key=self.config.anthropic_api_key,
            ),
            tts=openai.TTS(
                voice=self.config.tts_voice,
                api_key=self.config.openai_api_key,
            ),
            chat_ctx=agents.ChatContext(),
        )
        
        # Set up hooks
        assistant.llm.on("before_llm_cb", self._before_llm_callback)
        assistant.tts.on("before_tts_cb", self._before_tts_callback)
        
        # Start the agent
        assistant.start(ctx.room, participant)
        
        # Initial greeting
        await assistant.say("Hello! I'm ready to begin your system design interview. Are you ready to start?")
        
        logger.info("Interview started")
    
    def _before_llm_callback(self, chat_ctx: agents.ChatContext) -> agents.ChatContext:
        """
        Called before LLM processes input.
        
        This is where we inject the interview phase context and system prompt.
        """
        # Get current system prompt based on phase
        system_prompt = self.phase_manager.get_system_prompt(self.session.state)
        
        # Update chat context with phase-aware prompt
        chat_ctx.messages[0] = agents.ChatMessage(
            role="system",
            content=system_prompt
        )
        
        logger.debug(f"LLM callback - Phase: {self.session.state.phase.value}")
        
        return chat_ctx
    
    def _before_tts_callback(self, text: str) -> str:
        """
        Called before TTS converts text to speech.
        
        This is where we parse the JSON response, update session state,
        and extract only the spoken text.
        """
        # Parse LLM response
        spoken_text, updated_constraints = self.response_parser.parse(text)
        
        # Update session state
        if updated_constraints:
            # Add new constraints (deduplicate)
            for constraint in updated_constraints:
                if constraint not in self.session.state.locked_constraints:
                    self.session.state.locked_constraints.append(constraint)
                    logger.info(f"Locked constraint added: {constraint}")
        
        # Check if we should transition phases
        if self.phase_manager.should_transition(self.session.state):
            next_phase = self.phase_manager.get_next_phase(self.session.state.phase)
            logger.info(f"Transitioning from {self.session.state.phase.value} to {next_phase.value}")
            self.session.state.advance_phase(next_phase)
        
        # Add to conversation history
        self.session.state.add_message("assistant", spoken_text)
        
        logger.debug(f"TTS callback - Spoken text: {spoken_text[:100]}...")
        
        # Return only the spoken text (not the full JSON)
        return spoken_text


def run_agent(config: AgentConfig, scenario: str):
    """
    Run the interview agent.
    
    Args:
        config: Agent configuration
        scenario: Interview scenario
    """
    agent = InterviewAgent(config, scenario)
    
    # Create worker
    worker = agents.Worker(
        entrypoint_fnc=agent.entrypoint,
        request_fnc=None,  # No custom request handling
        opts=WorkerOptions(
            api_key=config.livekit_api_key,
            api_secret=config.livekit_api_secret,
            ws_url=config.livekit_url,
        ),
    )
    
    # Run worker (blocks until stopped)
    cli.run_app(worker)
