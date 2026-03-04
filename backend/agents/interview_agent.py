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
from ..interview.stt_wrapper import TimeoutSTT
from ..interview.tts_pronunciations import normalize_for_tts as _normalize_for_tts

logger = logging.getLogger(__name__)

# LLM resilience configuration
LLM_TIMEOUT_SECONDS = 12.0  # Timeout for Claude API first-token response
MAX_LLM_RETRIES = 3  # Total attempts including initial try


async def _stream_with_first_chunk_timeout(async_gen, timeout: float):
    """
    Wrap async generator with timeout only on first item (TTFT).

    Once first chunk arrives, continue streaming without timeout.
    This prevents stalled LLM requests while allowing normal streaming.

    Args:
        async_gen: Async generator to wrap
        timeout: Timeout in seconds for first chunk

    Raises:
        asyncio.TimeoutError: If first chunk doesn't arrive within timeout
    """
    try:
        # First chunk with timeout
        first_item = await asyncio.wait_for(async_gen.__anext__(), timeout=timeout)
        yield first_item

        # Rest without timeout (normal streaming can be slow)
        async for item in async_gen:
            yield item
    except StopAsyncIteration:
        pass


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

        # --- Record user message and detect STT failures ---
        messages_list = chat_ctx.messages()
        user_text = ""
        if messages_list:
            latest_msg = messages_list[-1]
            if latest_msg.role == "user":
                for content in latest_msg.content:
                    if isinstance(content, str):
                        user_text += content
                    elif isinstance(content, llm.ChatText):
                        user_text += content.text
                if user_text:
                    self.interview_session.state.add_message("user", user_text)
                    logger.debug(f"Recorded user message: {user_text[:100]}...")

        # --- Consecutive silence tracking and recovery ---
        # Track empty/silent user turns and inject recovery question after 3 consecutive silences
        if not user_text or not user_text.strip():
            self.interview_session.state.consecutive_silence_count += 1
            logger.warning(
                "Empty STT response detected — consecutive_silence=%d turn=%d phase=%s",
                self.interview_session.state.consecutive_silence_count,
                self.interview_session.state.total_turn_count,
                self.interview_session.state.phase.value,
            )

            # If < 3 consecutive silences, send simple recovery and skip LLM
            if self.interview_session.state.consecutive_silence_count < 3:
                recovery_text = "Sorry, I didn't catch that. Can you repeat?"
                recovery_chunk = llm.ChatChunk(
                    id="stt_recovery",
                    delta=llm.ChoiceDelta(role="assistant", content=recovery_text),
                )
                yield recovery_chunk
                # Record recovery message in history
                self.interview_session.state.add_message("assistant", recovery_text)
                logger.info("STT recovery message sent: %s", recovery_text)
                return  # Skip LLM processing for this turn

            # If >= 3 consecutive silences, continue to LLM with recovery injection
            # The recovery context will be added to dynamic_context below
            logger.info(
                "Consecutive silence limit reached (%d) — injecting recovery question",
                self.interview_session.state.consecutive_silence_count,
            )
        else:
            # User provided substantive input — reset silence counter
            if self.interview_session.state.consecutive_silence_count > 0:
                logger.info(
                    "Resetting consecutive_silence_count from %d to 0 after substantive input",
                    self.interview_session.state.consecutive_silence_count,
                )
                self.interview_session.state.consecutive_silence_count = 0

        # --- KV-cache split prompts: static (cached) + dynamic (per-turn) ---
        # First turn: Set static system prompt (gets KV-cached by LLM)
        if not chat_ctx.items or len(chat_ctx.items) == 0:
            static_prompt = self.phase_manager.get_static_system_prompt()
            chat_ctx.add_message(role="system", content=static_prompt)

        # Every turn: Build dynamic context
        dynamic_context = self.phase_manager.get_dynamic_context(self.interview_session.state)

        # Add consecutive silence recovery context if needed
        if self.interview_session.state.consecutive_silence_count >= 3:
            dynamic_context += (
                "\n\n**RECOVERY**: The candidate seems stuck or silent. "
                "Ask a clarifying question to help them continue. "
                "Provide a gentle prompt or ask if they need more context about the problem."
            )

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

        # --- Context overflow prevention: Cap chat_ctx at 16-20 non-system messages (8-10 turns) ---
        # Proactively trims conversation history BEFORE each Claude call to prevent token overflow.
        # System messages (static prompt + dynamic context + locked_constraints) are always kept.
        # This prevents hitting the token limit mid-session.
        MAX_HISTORY_MESSAGES = 18  # 9 turns (user + assistant pairs)
        system_items = [
            item for item in chat_ctx.items
            if hasattr(item, 'role') and item.role == "system"
        ]
        non_system_items = [
            item for item in chat_ctx.items
            if not (hasattr(item, 'role') and item.role == "system")
        ]
        if len(non_system_items) > MAX_HISTORY_MESSAGES:
            trimmed_count = len(non_system_items) - MAX_HISTORY_MESSAGES
            non_system_items = non_system_items[-MAX_HISTORY_MESSAGES:]
            chat_ctx.items = system_items + non_system_items
            logger.info(
                "Context trimmed: removed %d oldest messages, kept last %d — turn=%d",
                trimmed_count,
                MAX_HISTORY_MESSAGES,
                self.interview_session.state.total_turn_count,
            )

        logger.debug(
            f"LLM node — Phase: {self.interview_session.state.phase.value}, "
            f"Turn: {self.interview_session.state.phase_turn_count}"
        )

        # --- Streaming-safe retry with timeout, rate limit, and graceful degradation ---
        # On attempt 0 we stream chunks directly (no buffering, no latency penalty).
        # On retry we buffer the new response and replay it after success.
        # Timeout applies only to first chunk (TTFT), not entire stream.
        # Rate limits (429) are retried with exponential backoff or retry-after header.

        parser = StreamingResponseParser()
        last_chunk_id = "parsed_response"
        filler_chunk: Optional[llm.ChatChunk] = None

        for attempt in range(MAX_LLM_RETRIES):
            try:
                buffered_chunks: list[llm.ChatChunk] = []

                # Wrap LLM stream with timeout on first chunk
                llm_stream = Agent.default.llm_node(self, chat_ctx, tools, model_settings)
                llm_stream_with_timeout = _stream_with_first_chunk_timeout(
                    llm_stream, LLM_TIMEOUT_SECONDS
                )

                async for chunk in llm_stream_with_timeout:
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

            except asyncio.TimeoutError:
                # LLM timeout - retry with exponential backoff
                if attempt < MAX_LLM_RETRIES - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s...
                    logger.warning(
                        "LLM timeout (%ds) on attempt %d/%d, retrying in %ds — turn=%d phase=%s",
                        LLM_TIMEOUT_SECONDS,
                        attempt + 1,
                        MAX_LLM_RETRIES,
                        wait,
                        self.interview_session.state.total_turn_count,
                        self.interview_session.state.phase.value,
                    )
                    await asyncio.sleep(wait)
                    # Reset parser for fresh retry
                    parser = StreamingResponseParser()
                    first_spoken_time = None
                else:
                    # Final timeout - deliver filler per task requirements
                    logger.error(
                        "LLM timeout after %d attempts, delivering filler — turn=%d phase=%s",
                        MAX_LLM_RETRIES,
                        self.interview_session.state.total_turn_count,
                        self.interview_session.state.phase.value,
                    )
                    filler_text = "Hmm."
                    filler_chunk = llm.ChatChunk(
                        id=last_chunk_id,
                        delta=llm.ChoiceDelta(role="assistant", content=filler_text),
                    )
                    break

            except Exception as e:
                # Rate limit (429) or other API errors
                status = getattr(e, 'status_code', None)

                if status == 429 and attempt < MAX_LLM_RETRIES - 1:
                    # Extract retry-after header if present
                    retry_after = None
                    if hasattr(e, 'response') and hasattr(e.response, 'headers'):
                        retry_after = e.response.headers.get('retry-after') or e.response.headers.get('Retry-After')

                    # Use retry-after if present, otherwise exponential backoff
                    if retry_after:
                        try:
                            wait = float(retry_after)
                        except (ValueError, TypeError):
                            wait = 2 ** attempt
                    else:
                        wait = 2 ** attempt  # 1s, 2s, 4s...

                    logger.warning(
                        "Rate limit (429) on attempt %d/%d, retrying in %ds — turn=%d phase=%s%s",
                        attempt + 1,
                        MAX_LLM_RETRIES,
                        wait,
                        self.interview_session.state.total_turn_count,
                        self.interview_session.state.phase.value,
                        f" (retry-after: {retry_after}s)" if retry_after else "",
                    )
                    await asyncio.sleep(wait)
                    # Reset parser for the fresh retry response
                    parser = StreamingResponseParser()
                    first_spoken_time = None
                else:
                    # Non-retryable error or final attempt failed
                    logger.error(
                        "LLM request failed after %d attempt(s): %s (status: %s) — turn=%d phase=%s",
                        attempt + 1,
                        e,
                        status or "N/A",
                        self.interview_session.state.total_turn_count,
                        self.interview_session.state.phase.value,
                    )
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

        # --- Check for empty spoken text and retry if needed ---
        full_spoken = parser.get_spoken_text()
        retry_occurred = False
        retry_parser = None

        if not full_spoken or not full_spoken.strip():
            logger.warning(
                "Empty LLM response detected (no spoken text) — retrying with fallback prompt — turn=%d phase=%s",
                self.interview_session.state.total_turn_count,
                self.interview_session.state.phase.value,
            )

            # Retry LLM call ONCE with fallback prompt
            fallback_prompt = "You must provide a spoken response to the candidate. Please respond now."
            chat_ctx.add_message(role="system", content=fallback_prompt)

            retry_parser = StreamingResponseParser()
            retry_chunks: list[llm.ChatChunk] = []

            try:
                # Retry with 5s timeout
                llm_retry_stream = Agent.default.llm_node(self, chat_ctx, tools, model_settings)
                llm_retry_with_timeout = _stream_with_first_chunk_timeout(
                    llm_retry_stream, timeout=5.0
                )

                async for chunk in llm_retry_with_timeout:
                    if chunk.delta and chunk.delta.content:
                        spoken_fragment = retry_parser.feed(chunk.delta.content)
                        if spoken_fragment:
                            spoken_fragment = _normalize_for_tts(spoken_fragment)
                        if spoken_fragment:
                            spoken_chunk = llm.ChatChunk(
                                id=chunk.id or last_chunk_id,
                                delta=llm.ChoiceDelta(role="assistant", content=spoken_fragment),
                            )
                            retry_chunks.append(spoken_chunk)
                    else:
                        retry_chunks.append(chunk)

                # Flush retry parser
                final_retry_fragment = retry_parser.flush()
                if final_retry_fragment:
                    retry_chunks.append(llm.ChatChunk(
                        id=last_chunk_id,
                        delta=llm.ChoiceDelta(role="assistant", content=final_retry_fragment),
                    ))

                # Yield retry chunks to TTS
                for retry_chunk in retry_chunks:
                    yield retry_chunk

                # Get spoken text from retry
                retry_spoken = retry_parser.get_spoken_text()
                if retry_spoken and retry_spoken.strip():
                    full_spoken = retry_spoken
                    retry_occurred = True
                    logger.info("Retry successful — received spoken text: %s", retry_spoken[:60])
                else:
                    # Retry still empty — use hardcoded fallback
                    logger.error(
                        "Retry failed (still empty) — using hardcoded fallback — turn=%d phase=%s",
                        self.interview_session.state.total_turn_count,
                        self.interview_session.state.phase.value,
                    )
                    fallback_text = "Could you elaborate on that?"
                    fallback_chunk = llm.ChatChunk(
                        id=last_chunk_id,
                        delta=llm.ChoiceDelta(role="assistant", content=fallback_text),
                    )
                    yield fallback_chunk
                    full_spoken = fallback_text

            except (asyncio.TimeoutError, Exception) as e:
                # Retry failed — use hardcoded fallback
                logger.error(
                    "Retry failed with error (%s) — using hardcoded fallback — turn=%d phase=%s",
                    e,
                    self.interview_session.state.total_turn_count,
                    self.interview_session.state.phase.value,
                )
                fallback_text = "Could you elaborate on that?"
                fallback_chunk = llm.ChatChunk(
                    id=last_chunk_id,
                    delta=llm.ChoiceDelta(role="assistant", content=fallback_text),
                )
                yield fallback_chunk
                full_spoken = fallback_text

        # --- Update state after stream (safe — doesn't affect current turn's audio) ---
        # Use retry parser's state updates if retry was successful, otherwise use original parser
        active_parser = retry_parser if retry_occurred and retry_parser else parser
        new_phase, updated_constraints = active_parser.get_state_updates()

        if updated_constraints:
            for key, value in updated_constraints.items():
                self.interview_session.state.add_locked_constraint(key, value)
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
        if full_spoken:
            self.interview_session.state.add_message("assistant", full_spoken)
            logger.debug(f"Recorded assistant turn: {full_spoken[:100]}...")
        else:
            logger.warning("Parser returned empty spoken text — skipping history record")

        # --- Reset consecutive silence counter after recovery question is delivered ---
        # If we injected a recovery question and LLM generated a response, reset the counter
        # so the next turn starts fresh without recovery injection
        if self.interview_session.state.consecutive_silence_count >= 3:
            logger.info(
                "Recovery question delivered — resetting consecutive_silence_count from %d to 0",
                self.interview_session.state.consecutive_silence_count,
            )
            self.interview_session.state.consecutive_silence_count = 0

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
    ) -> AsyncIterable[rtc.AudioFrame]:
        """
        Custom TTS node with timeout and retry handling.

        Wraps Cartesia TTS with 5s timeout on first audio frame and one retry on failure.
        Streams audio frames immediately to maintain <2s response latency.
        Never loses LLM responses - logs loudly but allows silence if TTS is completely down.

        Timeout applies only to first frame (TTFB), not entire synthesis.
        This prevents stalled TTS requests while allowing normal streaming for long responses.
        """
        # Buffer text chunks for potential retry
        # Trade-off: Adds latency (can't start TTS until all text received) but enables retry
        text_chunks: list[str] = []
        async for chunk in text:
            text_chunks.append(chunk)

        # Don't attempt TTS if there's no text
        if not text_chunks:
            logger.debug("TTS node received empty text, skipping synthesis")
            return

        full_text = "".join(text_chunks)
        logger.debug(f"TTS synthesizing {len(full_text)} characters: {full_text[:100]}...")

        # TTS resilience configuration
        TTS_TIMEOUT_SECONDS = 5.0  # Timeout for first audio frame only
        MAX_TTS_RETRIES = 2  # Total attempts including initial try

        for attempt in range(MAX_TTS_RETRIES):
            try:
                # Create async generator from buffered text
                async def text_generator() -> AsyncIterable[str]:
                    for chunk in text_chunks:
                        yield chunk

                # Create TTS stream
                tts_stream = Agent.default.tts_node(self, text_generator(), model_settings)

                # Get first audio frame with timeout (detects TTS hangs/failures early)
                try:
                    first_frame = await asyncio.wait_for(
                        tts_stream.__anext__(),
                        timeout=TTS_TIMEOUT_SECONDS,
                    )
                    yield first_frame
                    frame_count = 1

                    # Stream remaining frames without timeout (normal streaming can be slow for long text)
                    async for audio_frame in tts_stream:
                        yield audio_frame
                        frame_count += 1

                    logger.debug(f"TTS synthesis complete — {frame_count} frames, attempt {attempt + 1}")
                    return

                except StopAsyncIteration:
                    # TTS stream ended immediately (no frames)
                    logger.debug(f"TTS returned no frames, attempt {attempt + 1}")
                    return

            except asyncio.TimeoutError:
                if attempt < MAX_TTS_RETRIES - 1:
                    logger.warning(
                        "TTS timeout (%.1fs) on attempt %d/%d, retrying — text_len=%d turn=%d",
                        TTS_TIMEOUT_SECONDS,
                        attempt + 1,
                        MAX_TTS_RETRIES,
                        len(full_text),
                        self.interview_session.state.total_turn_count,
                    )
                    await asyncio.sleep(0.5)  # Brief pause before retry
                else:
                    logger.error(
                        "🔴 TTS TIMEOUT after %d attempts — LLM response will be SILENT — text_len=%d turn=%d text=%s",
                        MAX_TTS_RETRIES,
                        len(full_text),
                        self.interview_session.state.total_turn_count,
                        full_text[:200],
                    )
                    # Fallback to silence (don't crash the session)
                    return

            except Exception as e:
                status = getattr(e, "status_code", "N/A")
                if attempt < MAX_TTS_RETRIES - 1:
                    logger.warning(
                        "TTS error on attempt %d/%d, retrying — status=%s type=%s msg=%s turn=%d",
                        attempt + 1,
                        MAX_TTS_RETRIES,
                        status,
                        type(e).__name__,
                        e,
                        self.interview_session.state.total_turn_count,
                    )
                    await asyncio.sleep(0.5)  # Brief pause before retry
                else:
                    logger.error(
                        "🔴 TTS FAILED after %d attempts — LLM response will be SILENT — status=%s type=%s msg=%s turn=%d text=%s",
                        MAX_TTS_RETRIES,
                        status,
                        type(e).__name__,
                        e,
                        self.interview_session.state.total_turn_count,
                        full_text[:200],
                    )
                    # Fallback to silence (don't crash the session)
                    return

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
    # Wrap Deepgram STT with timeout and error handling
    base_stt = deepgram.STT(
        api_key=config.deepgram_api_key,
        model="nova-2",
    )
    wrapped_stt = TimeoutSTT(
        wrapped_stt=base_stt,
        timeout=5.0,
    )
    logger.info("STT configured with 5s timeout and error recovery")

    session_kwargs = dict(
        stt=wrapped_stt,
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
        """Log per-turn timing instrumentation and token usage."""
        # Extract timing metrics
        stt_ms = (event.stt_duration * 1000) if hasattr(event, "stt_duration") and event.stt_duration else 0
        llm_ttft_ms = (event.llm_ttft * 1000) if hasattr(event, "llm_ttft") and event.llm_ttft else 0
        tts_ttfb_ms = (event.tts_ttfb * 1000) if hasattr(event, "tts_ttfb") and event.tts_ttfb else 0

        # Calculate total latency (STT + LLM TTFT + TTS TTFB)
        total_ms = stt_ms + llm_ttft_ms + tts_ttfb_ms

        # Get current turn number
        turn_number = interview_agent.interview_session.state.total_turn_count

        # Log per-turn timing in required format
        if stt_ms > 0 or llm_ttft_ms > 0 or tts_ttfb_ms > 0:
            logger.info(
                f"⚡ TURN {turn_number}: STT={stt_ms:.0f}ms LLM_TTFT={llm_ttft_ms:.0f}ms "
                f"TTS_TTFB={tts_ttfb_ms:.0f}ms TOTAL={total_ms:.0f}ms"
            )

        # Log additional metrics for debugging
        if hasattr(event, "llm_total_duration") and event.llm_total_duration:
            llm_total_ms = event.llm_total_duration * 1000
            logger.debug(f"⚡ TURN {turn_number}: LLM_Total={llm_total_ms:.0f}ms")

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
