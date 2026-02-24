"""Interview agent using LiveKit Agents 1.0 API with custom nodes."""

import asyncio
import logging
import time
import uuid
from typing import AsyncIterable, Optional

from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, AgentServer, JobContext, WorkerOptions, llm, cli
from livekit.plugins import deepgram, openai, silero, anthropic

from ..config import AgentConfig
from ..models.session import InterviewSession, SessionState, InterviewPhase
from ..models.scorecard import InterviewScorecard
from ..interview.phase_manager import PhaseManager
from ..interview.response_parser import StreamingResponseParser
from ..interview.scoring_engine import ScoringEngine

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

        # Scoring
        self._scoring_triggered = False
        self._scoring_engine = ScoringEngine()

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
        Custom LLM node — streams spoken text to TTS as tags complete.

        Spoken tags ([ACK], [Q], [SUMMARY]) are yielded immediately.
        State updates (phase, constraints) happen after stream ends.
        Latency is logged every turn.
        """
        turn_start = time.monotonic()
        first_spoken_time: Optional[float] = None

        # --- Record user message (unchanged logic) ---
        messages_list = chat_ctx.messages()
        if messages_list:
            latest_msg = messages_list[-1]
            if latest_msg.role == "user":
                user_text = ""
                for content in latest_msg.content:
                    if isinstance(content, str):
                        user_text += content
                    elif isinstance(content, llm.ChatText):
                        user_text += content.text
                if user_text:
                    self.interview_session.state.add_message("user", user_text)
                    logger.debug(f"Recorded user message: {user_text[:100]}...")

        # --- Inject phase-aware system prompt (unchanged logic) ---
        system_prompt = self.phase_manager.get_system_prompt(self.interview_session.state)
        if chat_ctx.items and len(chat_ctx.items) > 0:
            chat_ctx.items[0] = llm.ChatMessage(role="system", content=[system_prompt])
        else:
            chat_ctx.add_message(role="system", content=system_prompt)

        logger.debug(
            f"LLM node — Phase: {self.interview_session.state.phase.value}, "
            f"Turn: {self.interview_session.state.phase_turn_count}"
        )

        # --- Streaming parse ---
        parser = StreamingResponseParser()
        last_chunk_id = "parsed_response"

        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            if chunk.id:
                last_chunk_id = chunk.id

            if chunk.delta and chunk.delta.content:
                spoken_fragment = parser.feed(chunk.delta.content)

                if spoken_fragment:
                    if first_spoken_time is None:
                        first_spoken_time = time.monotonic()
                        elapsed_ms = (first_spoken_time - turn_start) * 1000
                        logger.info(f"⚡ First spoken text in {elapsed_ms:.0f}ms: {spoken_fragment!r}")

                    yield llm.ChatChunk(
                        id=last_chunk_id,
                        delta=llm.ChoiceDelta(role="assistant", content=spoken_fragment),
                    )
                continue  # don't yield the raw chunk

            yield chunk  # pass through non-text chunks (tool calls, control frames)

        # --- Flush buffer after stream ends ---
        final_fragment = parser.flush()
        if final_fragment:
            if first_spoken_time is None:
                first_spoken_time = time.monotonic()
            yield llm.ChatChunk(
                id=last_chunk_id,
                delta=llm.ChoiceDelta(role="assistant", content=final_fragment),
            )

        total_ms = (time.monotonic() - turn_start) * 1000
        first_ms = ((first_spoken_time or turn_start) - turn_start) * 1000
        logger.info(f"⚡ Turn complete in {total_ms:.0f}ms (first speech: {first_ms:.0f}ms)")

        # --- Update state after stream (safe — doesn't affect current turn's audio) ---
        new_phase, updated_constraints = parser.get_state_updates()

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

                        # Safe without a lock: asyncio is cooperative and the check+set below has no
                        # await between them, so no other coroutine can interleave here.
                        if requested_phase == InterviewPhase.WRAP and not self._scoring_triggered:
                            self._scoring_triggered = True
                            asyncio.create_task(self._generate_scorecard())
                    else:
                        logger.warning(f"Phase transition blocked (monotonic): {new_phase}")
                else:
                    logger.debug(f"Phase transition not ready: {self.interview_session.state.phase.value} -> {new_phase}")
            except ValueError:
                logger.warning(f"Invalid phase in response: {new_phase}")

        # --- Record full turn in history ---
        full_spoken = parser.get_spoken_text()
        if full_spoken:
            self.interview_session.state.add_message("assistant", full_spoken)
            logger.debug(f"Recorded assistant turn: {full_spoken[:100]}...")
        else:
            logger.warning("Parser returned empty spoken text — skipping history record")
    
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

    async def _generate_scorecard(self):
        """Generate post-interview scorecard. Runs as background task or on session_end."""
        try:
            logger.info("Generating interview scorecard...")
            scorecard = await self._scoring_engine.score_interview(
                self.interview_session, self.config
            )
            self.interview_session.scorecard = scorecard.to_dict()
            saved_path = await self._scoring_engine.save_scorecard(scorecard)
            logger.info(f"Scorecard saved: {saved_path}")
            self._log_scorecard(scorecard)
        except Exception as e:
            logger.error(f"Scorecard generation failed: {e}", exc_info=True)

    def _log_scorecard(self, scorecard: InterviewScorecard):
        """Log human-readable scorecard for immediate visibility during testing."""
        logger.info("=" * 60)
        logger.info(f"INTERVIEW SCORECARD — {scorecard.hire_signal} ({scorecard.overall_score:.1f}/5)")
        logger.info(f"Scenario: {scorecard.scenario}")
        for dim_key, dim in scorecard.dimensions.items():
            logger.info(f"  {dim_key}: {dim.score}/5 ({dim.label})")
            logger.info(f"    {dim.rationale}")
        logger.info(f"Narrative: {scorecard.narrative}")
        logger.info("=" * 60)


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
            model=config.tts_model,
            speed=config.tts_speed,
        ),
        vad=silero.VAD.load(
            min_silence_duration=config.silence_threshold_ms / 1000.0,
        ),
        min_endpointing_delay=config.min_endpointing_delay,
        max_endpointing_delay=config.max_endpointing_delay,
    )

    # Start session with our custom agent
    await session.start(
        room=ctx.room,
        agent=interview_agent,
    )

    @session.on("agent_speech_interrupted")
    def on_interrupted():
        logger.info("Interviewer interrupted by candidate — listening")

    @session.on("session_end")
    async def on_session_end():
        """Fallback: score partial interviews if WRAP was never reached."""
        if not interview_agent._scoring_triggered:
            interview_agent._scoring_triggered = True
            await interview_agent._generate_scorecard()
    
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
