"""Interview agent using LiveKit Agents 1.0 API with custom nodes."""

import asyncio
import logging
import time
import uuid
from typing import AsyncIterable, Optional

from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, AgentServer, JobContext, WorkerOptions, llm, cli
from livekit.plugins import deepgram, openai, silero, anthropic, cartesia, turn_detector

from ..config import AgentConfig
from ..models.session import InterviewSession, SessionState, InterviewPhase
from ..models.scorecard import InterviewScorecard
from ..interview.phase_manager import PhaseManager
from ..interview.response_parser import StreamingResponseParser
from ..interview.scoring_engine import ScoringEngine
from ..interview.tts_pronunciations import normalize_for_tts as _normalize_for_tts

logger = logging.getLogger(__name__)


class InterviewAgent(Agent):
    """
    Custom Agent that conducts system design interviews.
    
    Uses LiveKit Agents 1.0 API with llm_node and tts_node overrides.
    """
    
    def __init__(self, config: AgentConfig, scenario: str, scenario_metadata=None):
        """
        Initialize interview agent.

        Args:
            config: Agent configuration
            scenario: Interview scenario (e.g., "Design a payment gateway")
            scenario_metadata: Optional ScenarioMetadata object with rich scenario information
        """
        # Minimal placeholder instructions - real instructions come from phase_manager.get_system_prompt()
        # injected in llm_node to prevent competing system prompts
        instructions = "You are a technical interviewer. Follow the system prompt provided in context."

        # Initialize parent Agent class
        super().__init__(instructions=instructions)

        self.config = config
        self.scenario = scenario
        self.scenario_metadata = scenario_metadata

        # Create interview session (renamed to avoid collision with Agent.session property)
        session_id = str(uuid.uuid4())
        self.interview_session = InterviewSession(session_id=session_id, scenario=scenario)

        # Initialize interview engine components
        self.phase_manager = PhaseManager(scenario, scenario_metadata)

        # Scoring
        self._scoring_triggered = False
        self._scoring_engine = ScoringEngine()

        # Track if INTRO/FAILURE was interrupted before critical content was presented
        self._intro_interrupted: bool = False
        self._failure_setup_interrupted: bool = False

        # Set after 2 WRAP turns — no further LLM responses after this point
        self._session_completed: bool = False

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

        # Session has terminated after WRAP — no further LLM responses
        if self._session_completed:
            logger.info("Session completed — not generating further LLM responses")
            return  # yields nothing; LiveKit session continues silently until participant leaves

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

        # --- KV-cache split prompts: static (cached) + dynamic (per-turn) ---
        # First turn: Set static system prompt (gets KV-cached by LLM)
        if not chat_ctx.items or len(chat_ctx.items) == 0:
            static_prompt = self.phase_manager.get_static_system_prompt()
            chat_ctx.add_message(role="system", content=static_prompt)

        # Every turn: Build dynamic context
        dynamic_context = self.phase_manager.get_dynamic_context(self.interview_session.state)

        # Add interruption recovery context if needed
        current_phase = self.interview_session.state.phase
        if self._intro_interrupted:
            if current_phase == InterviewPhase.INTRO:
                dynamic_context += (
                    "\n\n**RECOVERY CONTEXT**: Your previous turn was interrupted — "
                    "the candidate has NOT heard the full scenario. "
                    f'The scenario is: "{self.scenario}". '
                    "Re-state it naturally before asking for clarifying questions. "
                    "Do NOT ask the candidate what system they are designing."
                )
            self._intro_interrupted = False
        if self._failure_setup_interrupted:
            if current_phase == InterviewPhase.FAILURE:
                dynamic_context += (
                    "\n\n**RECOVERY CONTEXT**: Your previous failure scenario setup was "
                    "interrupted — the candidate may not have heard the full premise. "
                    "Re-state the failure scenario before asking about its impact."
                )
            self._failure_setup_interrupted = False

        # CRITICAL: Remove previous dynamic context to prevent accumulation
        # chat_ctx.items[0] = static system (never changes, KV-cached)
        # chat_ctx.items[1] = previous dynamic context (remove before adding new one)
        # LiveKit 1.4.3: items can include non-message objects, check if it's a message first
        if len(chat_ctx.items) > 1 and hasattr(chat_ctx.items[1], 'role') and chat_ctx.items[1].role == "system":
            chat_ctx.items.pop(1)

        # Add fresh dynamic context as separate system message
        chat_ctx.add_message(role="system", content=dynamic_context)

        # --- Fix 3: Cap chat_ctx at 14 non-system messages (~7 turns) ---
        # Prevents unbounded growth past the 30K input-token/min rate limit.
        # System messages (static prompt + dynamic context) are always kept.
        MAX_HISTORY_MESSAGES = 14
        system_items = [
            item for item in chat_ctx.items
            if hasattr(item, 'role') and item.role == "system"
        ]
        non_system_items = [
            item for item in chat_ctx.items
            if not (hasattr(item, 'role') and item.role == "system")
        ]
        if len(non_system_items) > MAX_HISTORY_MESSAGES:
            non_system_items = non_system_items[-MAX_HISTORY_MESSAGES:]
            chat_ctx.items = system_items + non_system_items

        logger.debug(
            f"LLM node — Phase: {self.interview_session.state.phase.value}, "
            f"Turn: {self.interview_session.state.phase_turn_count}"
        )

        # --- Fix 5: Streaming-safe retry with graceful degradation ---
        # Python 3.11+: yield inside try/except is legal.
        # On attempt 0 we stream chunks directly (no buffering, no latency penalty).
        # On retry we buffer the new response and replay it after success.
        # TODO: If a 429 interrupts mid-stream on attempt 0, chunks already yielded to TTS
        # are not replayable — the retry will produce a fresh complete sentence from the new
        # response rather than continuing the partial one. This is acceptable given mid-stream
        # 429s are rare (rate limits apply at request start, not during streaming).

        parser = StreamingResponseParser()
        last_chunk_id = "parsed_response"
        filler_chunk: Optional[llm.ChatChunk] = None

        for attempt in range(3):
            try:
                buffered_chunks: list[llm.ChatChunk] = []

                async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
                    if chunk.id:
                        last_chunk_id = chunk.id

                    if chunk.delta and chunk.delta.content:
                        spoken_fragment = parser.feed(chunk.delta.content)
                        if spoken_fragment:
                            spoken_fragment = _normalize_for_tts(spoken_fragment)

                        if spoken_fragment:
                            if first_spoken_time is None:
                                first_spoken_time = time.monotonic()
                                elapsed_ms = (first_spoken_time - turn_start) * 1000
                                logger.info(f"⚡ First spoken text in {elapsed_ms:.0f}ms: {spoken_fragment!r}")

                            spoken_chunk = llm.ChatChunk(
                                id=last_chunk_id,
                                delta=llm.ChoiceDelta(role="assistant", content=spoken_fragment),
                            )
                            if attempt == 0:
                                yield spoken_chunk   # stream immediately on first attempt
                            else:
                                buffered_chunks.append(spoken_chunk)  # collect for replay on retry
                        continue  # don't yield the raw chunk

                    if attempt == 0:
                        yield chunk   # pass through non-text chunks on first attempt
                    else:
                        buffered_chunks.append(chunk)

                # Flush parser buffer after stream ends
                final_fragment = parser.flush()
                if final_fragment:
                    if first_spoken_time is None:
                        first_spoken_time = time.monotonic()
                    flushed = llm.ChatChunk(
                        id=last_chunk_id,
                        delta=llm.ChoiceDelta(role="assistant", content=final_fragment),
                    )
                    if attempt == 0:
                        yield flushed
                    else:
                        buffered_chunks.append(flushed)

                # Replay buffered chunks for retry attempts
                if attempt > 0:
                    for buffered in buffered_chunks:
                        yield buffered

                break  # success — exit retry loop

            except Exception as e:
                status = getattr(e, 'status_code', None)
                if status == 429 and attempt < 2:
                    wait = 2 ** attempt  # 1s, then 2s
                    logger.warning(
                        "Rate limit hit (attempt %d/3), retrying in %ds", attempt + 1, wait
                    )
                    await asyncio.sleep(wait)
                    # Reset parser for the fresh retry response
                    parser = StreamingResponseParser()
                    first_spoken_time = None
                else:
                    logger.error("LLM request failed after %d attempt(s): %s", attempt + 1, e)
                    # Graceful degradation: emit a filler phrase so TTS says something
                    # natural instead of the session dying silently.
                    filler_text = "Give me just a moment."
                    filler_chunk = llm.ChatChunk(
                        id=last_chunk_id,
                        delta=llm.ChoiceDelta(role="assistant", content=filler_text),
                    )
                    break

        if filler_chunk is not None:
            yield filler_chunk
            return  # skip state update — no real LLM response to parse

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

        # --- Terminate session after 2 WRAP turns (closing question + closing ACK) ---
        if (self.interview_session.state.phase == InterviewPhase.WRAP
                and self.interview_session.state.phase_turn_count >= 2
                and not self._session_completed):
            self._session_completed = True
            logger.info("WRAP phase complete (%d turns) — session terminated",
                        self.interview_session.state.phase_turn_count)
    
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
        try:
            async for audio_frame in Agent.default.tts_node(self, text, model_settings):
                yield audio_frame
        except Exception as e:
            status = getattr(e, "status_code", "N/A")
            logger.error("TTS failed — status_code=%s  type=%s  msg=%s", status, type(e).__name__, e)
            raise

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


def prewarm(proc: agents.JobProcess) -> None:
    """Pre-load heavy models once per worker process before any job arrives."""
    from ..config import AgentConfig
    config = AgentConfig.from_env()

    proc.userdata["turn_detector"] = None  # default: Silero VAD fallback

    if config.use_semantic_turn_detection:
        try:
            logger.info("Loading semantic turn detector model...")
            eou = turn_detector.english.EnglishModel()
            proc.userdata["turn_detector"] = eou
            logger.info("Semantic turn detector loaded")
        except Exception as e:
            logger.warning(
                "Turn detector failed to load (%s); sessions will use Silero VAD only", e
            )


async def entrypoint(ctx: JobContext):
    """
    Entrypoint for LiveKit agent.

    Called when a participant joins the room.
    """
    logger.info(f"Agent starting for room: {ctx.room.name}")

    # Track disconnect state for graceful handling
    disconnect_state = {
        "is_disconnected": False,
        "disconnect_time": None,
        "shutdown_task": None,
    }

    # Load config
    from ..config import AgentConfig
    config = AgentConfig.from_env()

    # Validate Cartesia key loaded
    _key = config.cartesia_api_key
    if _key:
        logger.info("Cartesia API key loaded: %s...%s", _key[:4], _key[-4:])
    else:
        logger.error("Cartesia API key is EMPTY — check CARTESIA_API_KEY in .env")

    # Get scenario from job metadata or use default
    from ..interview.scenario_loader import ScenarioLoader
    import json

    # Initialize scenario loader
    scenario_loader = ScenarioLoader()
    logger.info(f"Loaded {len(scenario_loader._scenarios)} scenarios")

    # Parse job metadata — frontend sends JSON with scenario ID
    scenario_text = "Design a URL Shortener"
    scenario_metadata = None

    if hasattr(ctx.job, 'metadata') and ctx.job.metadata:
        try:
            # Try parsing as JSON: {"scenario": "url-shortener"}
            metadata_dict = json.loads(ctx.job.metadata)
            scenario_id = metadata_dict.get("scenario", "url-shortener")

            # Load scenario
            scenario_metadata = scenario_loader.get_scenario(scenario_id)
            scenario_text = scenario_metadata.name
            logger.info(f"Selected scenario: {scenario_metadata.id} (archetype: {scenario_metadata.archetype})")

        except (json.JSONDecodeError, Exception) as e:
            # Fallback: treat as literal scenario text for backward compatibility
            logger.warning(f"Failed to parse job metadata as JSON, using as literal text: {e}")
            if isinstance(ctx.job.metadata, str) and len(ctx.job.metadata) > 5:
                scenario_text = ctx.job.metadata

    # Create interview agent
    interview_agent = InterviewAgent(config, scenario_text, scenario_metadata)
    
    # Create agent session
    session_kwargs = dict(
        stt=deepgram.STT(
            api_key=config.deepgram_api_key,
            model="nova-2",
        ),
        llm=anthropic.LLM(
            model=config.llm_model,
            api_key=config.anthropic_api_key,
            caching="ephemeral",
        ),
        tts=cartesia.TTS(
            model="sonic-3",  # Latest Cartesia model
            voice=config.cartesia_voice_id,
            api_key=config.cartesia_api_key,
            speed=config.cartesia_speed,
            **({"pronunciation_dict_id": config.cartesia_pronunciation_dict_id}
               if config.cartesia_pronunciation_dict_id else {}),
        ),
        vad=silero.VAD.load(
            min_silence_duration=config.silence_threshold_ms / 1000.0,
        ),
        min_endpointing_delay=config.min_endpointing_delay,
        max_endpointing_delay=config.max_endpointing_delay,
    )
    eou = ctx.proc.userdata.get("turn_detector")
    if eou is not None:
        session_kwargs["turn_detection"] = eou
        logger.info("Semantic turn detection active for this session")
    else:
        logger.info("Silero VAD turn detection active for this session")
    session = AgentSession(**session_kwargs)

    # Start session with our custom agent
    await session.start(
        room=ctx.room,
        agent=interview_agent,
    )

    async def handle_graceful_shutdown():
        """Gracefully shut down the session after prolonged disconnect."""
        try:
            logger.info("30s disconnect timeout reached — shutting down session gracefully")
            # Trigger scoring if not already done
            if not interview_agent._scoring_triggered:
                interview_agent._scoring_triggered = True
                await interview_agent._generate_scorecard()
            # Close the room connection
            await ctx.room.disconnect()
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}", exc_info=True)

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        """Handle participant disconnect — don't crash, wait for reconnection."""
        # Only track candidate disconnections (not our agent)
        if participant.kind == rtc.ParticipantKind.STANDARD:
            logger.warning(
                f"Participant disconnected: {participant.identity} — waiting for reconnection"
            )
            disconnect_state["is_disconnected"] = True
            disconnect_state["disconnect_time"] = time.monotonic()

            # Schedule graceful shutdown after 30s if no reconnection
            async def delayed_shutdown():
                try:
                    await asyncio.sleep(30.0)
                    if disconnect_state["is_disconnected"]:
                        await handle_graceful_shutdown()
                except asyncio.CancelledError:
                    logger.info("Shutdown task cancelled — participant reconnected")
                except Exception as e:
                    logger.error(f"Error in delayed shutdown: {e}", exc_info=True)

            # Cancel previous shutdown task if exists
            if disconnect_state["shutdown_task"]:
                disconnect_state["shutdown_task"].cancel()

            # Start new shutdown task
            disconnect_state["shutdown_task"] = asyncio.create_task(delayed_shutdown())

    @ctx.room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        """Handle participant reconnection — resume seamlessly if <30s."""
        if participant.kind == rtc.ParticipantKind.STANDARD:
            if disconnect_state["is_disconnected"]:
                disconnect_duration = time.monotonic() - disconnect_state["disconnect_time"]
                logger.info(
                    f"Participant reconnected after {disconnect_duration:.1f}s — resuming session"
                )

                # Cancel shutdown task
                if disconnect_state["shutdown_task"]:
                    disconnect_state["shutdown_task"].cancel()
                    disconnect_state["shutdown_task"] = None

                # Clear disconnect state
                disconnect_state["is_disconnected"] = False
                disconnect_state["disconnect_time"] = None

                # Session state is preserved server-side, so resume works automatically
                logger.info("Session state preserved — participant can continue interview")
            else:
                logger.info(f"New participant connected: {participant.identity}")

    @session.on("agent_speech_interrupted")
    def on_interrupted():
        logger.info("Interviewer interrupted by candidate — listening")
        phase = interview_agent.interview_session.state.phase
        if phase == InterviewPhase.INTRO:
            interview_agent._intro_interrupted = True
            logger.info("Interrupted during INTRO — will recover scenario on next turn")
        elif phase == InterviewPhase.FAILURE:
            interview_agent._failure_setup_interrupted = True
            logger.info("Interrupted during FAILURE — will recover scenario setup on next turn")

    @session.on("session_end")
    def on_session_end():
        """Fallback: score partial interviews if WRAP was never reached."""
        if not interview_agent._scoring_triggered:
            interview_agent._scoring_triggered = True
            asyncio.create_task(interview_agent._generate_scorecard())

    @session.on("metrics_collected")
    def on_metrics(event):
        """Log actual per-component latencies from LiveKit metrics."""
        metrics_data = []

        # STT duration
        if hasattr(event, "stt_duration") and event.stt_duration:
            stt_ms = event.stt_duration * 1000
            metrics_data.append(f"STT={stt_ms:.0f}ms")

        # LLM time to first token (TTFT)
        if hasattr(event, "llm_ttft") and event.llm_ttft:
            ttft_ms = event.llm_ttft * 1000
            metrics_data.append(f"LLM-TTFT={ttft_ms:.0f}ms")

        # LLM total duration
        if hasattr(event, "llm_total_duration") and event.llm_total_duration:
            llm_total_ms = event.llm_total_duration * 1000
            metrics_data.append(f"LLM-Total={llm_total_ms:.0f}ms")

        # TTS time to first byte (TTFB)
        if hasattr(event, "tts_ttfb") and event.tts_ttfb:
            tts_ttfb_ms = event.tts_ttfb * 1000
            metrics_data.append(f"TTS-TTFB={tts_ttfb_ms:.0f}ms")

        # Log combined metrics
        if metrics_data:
            logger.info(f"⚡ Component metrics: {', '.join(metrics_data)}")

        # Log LLM token usage to validate theoretical token budget
        input_tokens = getattr(event, 'input_tokens', None) or getattr(event, 'llm_input_tokens', None)
        output_tokens = getattr(event, 'output_tokens', None) or getattr(event, 'llm_output_tokens', None)
        cache_read = getattr(event, 'cache_read_input_tokens', None) or getattr(event, 'llm_cache_read_input_tokens', None)
        if input_tokens is not None:
            logger.info(
                "📊 LLM tokens — input: %d, output: %d, cache_read: %d",
                input_tokens,
                output_tokens or 0,
                cache_read or 0,
            )

    # Send initial greeting using session.say() - skips LLM entirely for faster start
    # Strip leading "Design " from scenario name to avoid "We're designing Design a URL Shortener"
    display_name = scenario_text.removeprefix("Design ").removeprefix("design ")
    intro_text = f"Hey there. We're designing {display_name}. What questions do you have?"
    await session.say(intro_text, allow_interruptions=True)
    
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
