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
from ..logging import get_logger, set_global_context
from ..models.session import InterviewSession, SessionState, InterviewPhase
from ..models.scorecard import InterviewScorecard
from ..interview.phase_manager import PhaseManager
from ..interview.response_parser import StreamingResponseParser
from ..interview.scoring_engine import ScoringEngine
from ..interview.sentry_context import set_interview_context, update_turn_context
from ..interview.stt_wrapper import TimeoutSTT
from ..interview.tts_pronunciations import normalize_for_tts as _normalize_for_tts

logger = get_logger(__name__)

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

        # Set global logging context for this session
        set_global_context(session_id=session_id)

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

        logger.info(
            "Interview agent initialized",
            event_type="agent_initialized",
            scenario=scenario,
            scenario_id=scenario_metadata.id if scenario_metadata else None,
        )
    
    async def on_enter(self):
        """Called when agent becomes active in session."""
        await logger.info_async(
            "Agent entering session",
            event_type="session_start",
            scenario=self.scenario,
            phase=self.interview_session.state.phase.value,
        )

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
            await logger.info_async(
                "Session completed — not generating further LLM responses",
                event_type="session_completed",
                turn_number=self.interview_session.state.total_turn_count,
            )
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
                    await logger.info_async(
                        "STT transcription received",
                        event_type="stt_complete",
                        turn_number=self.interview_session.state.total_turn_count,
                        phase=self.interview_session.state.phase.value,
                        text_length=len(user_text),
                    )

        # --- Consecutive silence tracking and recovery ---
        # Track empty/silent user turns and inject recovery question after 3 consecutive silences
        if not user_text or not user_text.strip():
            self.interview_session.state.consecutive_silence_count += 1
            await logger.warning_async(
                "Empty STT response detected",
                event_type="stt_silence",
                turn_number=self.interview_session.state.total_turn_count,
                phase=self.interview_session.state.phase.value,
                consecutive_silence_count=self.interview_session.state.consecutive_silence_count,
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
                await logger.info_async(
                    "STT recovery message sent",
                    event_type="stt_recovery",
                    turn_number=self.interview_session.state.total_turn_count,
                )
                return  # Skip LLM processing for this turn

            # If >= 3 consecutive silences, continue to LLM with recovery injection
            # The recovery context will be added to dynamic_context below
            await logger.info_async(
                "Consecutive silence limit reached — injecting recovery question",
                event_type="stt_recovery_inject",
                turn_number=self.interview_session.state.total_turn_count,
                consecutive_silence_count=self.interview_session.state.consecutive_silence_count,
            )
        else:
            # User provided substantive input — reset silence counter
            if self.interview_session.state.consecutive_silence_count > 0:
                await logger.info_async(
                    "Resetting consecutive silence counter after substantive input",
                    event_type="stt_silence_reset",
                    turn_number=self.interview_session.state.total_turn_count,
                    previous_count=self.interview_session.state.consecutive_silence_count,
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
            await logger.info_async(
                f"Context trimmed: removed {trimmed_count} oldest messages, kept last {MAX_HISTORY_MESSAGES}",
                event_type="context_trimmed",
                turn_number=self.interview_session.state.total_turn_count,
                trimmed_count=trimmed_count,
                kept_count=MAX_HISTORY_MESSAGES,
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

                # Log LLM request start
                if attempt == 0:
                    await logger.info_async(
                        "LLM request started",
                        event_type="llm_request",
                        turn_number=self.interview_session.state.total_turn_count,
                        phase=self.interview_session.state.phase.value,
                    )

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
                                await logger.info_async(
                                    f"First spoken text in {elapsed_ms:.0f}ms",
                                    event_type="llm_ttft",
                                    turn_number=self.interview_session.state.total_turn_count,
                                    phase=self.interview_session.state.phase.value,
                                    ttft_ms=int(elapsed_ms),
                                )

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
                    await logger.warning_async(
                        f"LLM timeout ({LLM_TIMEOUT_SECONDS}s), retrying in {wait}s",
                        event_type="llm_timeout",
                        turn_number=self.interview_session.state.total_turn_count,
                        phase=self.interview_session.state.phase.value,
                        attempt=attempt + 1,
                        max_attempts=MAX_LLM_RETRIES,
                        retry_delay_s=wait,
                        timeout_seconds=LLM_TIMEOUT_SECONDS,
                    )
                    await asyncio.sleep(wait)
                    # Reset parser for fresh retry
                    parser = StreamingResponseParser()
                    first_spoken_time = None
                else:
                    # Final timeout - deliver filler per task requirements
                    await logger.error_async(
                        f"LLM timeout after {MAX_LLM_RETRIES} attempts, delivering filler",
                        event_type="llm_timeout_fatal",
                        turn_number=self.interview_session.state.total_turn_count,
                        phase=self.interview_session.state.phase.value,
                        max_attempts=MAX_LLM_RETRIES,
                        timeout_seconds=LLM_TIMEOUT_SECONDS,
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

                    await logger.warning_async(
                        f"Rate limit (429), retrying in {wait}s",
                        event_type="llm_rate_limit",
                        turn_number=self.interview_session.state.total_turn_count,
                        phase=self.interview_session.state.phase.value,
                        attempt=attempt + 1,
                        max_attempts=MAX_LLM_RETRIES,
                        retry_delay_s=wait,
                        retry_after_header=retry_after,
                    )
                    await asyncio.sleep(wait)
                    # Reset parser for the fresh retry response
                    parser = StreamingResponseParser()
                    first_spoken_time = None
                else:
                    # Non-retryable error or final attempt failed
                    await logger.error_async(
                        f"LLM request failed: {e}",
                        event_type="llm_error",
                        turn_number=self.interview_session.state.total_turn_count,
                        phase=self.interview_session.state.phase.value,
                        attempt=attempt + 1,
                        status_code=status or "N/A",
                        error_type=type(e).__name__,
                        exc_info=True,
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
        await logger.info_async(
            f"⚡ Turn complete in {total_ms:.0f}ms (first speech: {first_ms:.0f}ms)",
            event_type="llm_response",
            turn_number=self.interview_session.state.total_turn_count,
            phase=self.interview_session.state.phase.value,
            total_latency_ms=int(total_ms),
            first_speech_ms=int(first_ms),
        )

        # --- Check for empty spoken text and retry if needed ---
        full_spoken = parser.get_spoken_text()
        retry_occurred = False
        retry_parser = None

        if not full_spoken or not full_spoken.strip():
            await logger.warning_async(
                "Empty LLM response detected (no spoken text) — retrying with fallback prompt",
                event_type="llm_empty_response",
                turn_number=self.interview_session.state.total_turn_count,
                phase=self.interview_session.state.phase.value,
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
                    await logger.info_async(
                        f"Retry successful — received spoken text: {retry_spoken[:60]}",
                        event_type="llm_retry_success",
                        turn_number=self.interview_session.state.total_turn_count,
                    )
                else:
                    # Retry still empty — use hardcoded fallback
                    await logger.error_async(
                        "Retry failed (still empty) — using hardcoded fallback",
                        event_type="llm_retry_failed",
                        turn_number=self.interview_session.state.total_turn_count,
                        phase=self.interview_session.state.phase.value,
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
                await logger.error_async(
                    f"Retry failed with error ({e}) — using hardcoded fallback",
                    event_type="llm_retry_error",
                    turn_number=self.interview_session.state.total_turn_count,
                    phase=self.interview_session.state.phase.value,
                    error_type=type(e).__name__,
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
                await logger.info_async(
                    f"Locked constraint: {key} = {value}",
                    event_type="constraint_added",
                    turn_number=self.interview_session.state.total_turn_count,
                    constraint_key=key,
                    constraint_value=value,
                )

        if new_phase:
            try:
                requested_phase = InterviewPhase(new_phase)
                if self.phase_manager.should_transition_phase(self.interview_session.state, requested_phase):
                    if self.interview_session.state.advance_phase(requested_phase):
                        await logger.info_async(
                            f"Phase transitioned: {self.interview_session.state.phase.value}",
                            event_type="phase_transition",
                            turn_number=self.interview_session.state.total_turn_count,
                            from_phase=self.interview_session.state.phase.value,
                            to_phase=requested_phase.value,
                        )

                        # Safe without a lock: asyncio is cooperative and the check+set below has no
                        # await between them, so no other coroutine can interleave here.
                        if requested_phase == InterviewPhase.WRAP and not self._scoring_triggered:
                            self._scoring_triggered = True
                            asyncio.create_task(self._generate_scorecard())
                    else:
                        await logger.warning_async(
                            f"Phase transition blocked (monotonic): {new_phase}",
                            event_type="phase_transition_blocked",
                            turn_number=self.interview_session.state.total_turn_count,
                            requested_phase=new_phase,
                        )
                else:
                    await logger.debug_async(
                        f"Phase transition not ready: {self.interview_session.state.phase.value} -> {new_phase}",
                        event_type="phase_transition_not_ready",
                        turn_number=self.interview_session.state.total_turn_count,
                        current_phase=self.interview_session.state.phase.value,
                        requested_phase=new_phase,
                    )
            except ValueError:
                await logger.warning_async(
                    f"Invalid phase in response: {new_phase}",
                    event_type="phase_invalid",
                    turn_number=self.interview_session.state.total_turn_count,
                    invalid_phase=new_phase,
                )

        # --- Record full turn in history ---
        if full_spoken:
            self.interview_session.state.add_message("assistant", full_spoken)
            await logger.debug_async(
                f"Recorded assistant turn: {full_spoken[:100]}...",
                event_type="turn_recorded",
                turn_number=self.interview_session.state.total_turn_count,
                text_length=len(full_spoken),
            )
        else:
            await logger.warning_async(
                "Parser returned empty spoken text — skipping history record",
                event_type="turn_recording_skipped",
                turn_number=self.interview_session.state.total_turn_count,
            )

        # --- Reset consecutive silence counter after recovery question is delivered ---
        # If we injected a recovery question and LLM generated a response, reset the counter
        # so the next turn starts fresh without recovery injection
        if self.interview_session.state.consecutive_silence_count >= 3:
            await logger.info_async(
                f"Recovery question delivered — resetting consecutive_silence_count from {self.interview_session.state.consecutive_silence_count} to 0",
                event_type="stt_recovery_reset",
                turn_number=self.interview_session.state.total_turn_count,
                previous_silence_count=self.interview_session.state.consecutive_silence_count,
            )
            self.interview_session.state.consecutive_silence_count = 0

        # --- Terminate session after 2 WRAP turns (closing question + closing ACK) ---
        if (self.interview_session.state.phase == InterviewPhase.WRAP
                and self.interview_session.state.phase_turn_count >= 2
                and not self._session_completed):
            self._session_completed = True
            await logger.info_async(
                f"WRAP phase complete ({self.interview_session.state.phase_turn_count} turns) — session terminated",
                event_type="session_terminated",
                turn_number=self.interview_session.state.total_turn_count,
                wrap_turns=self.interview_session.state.phase_turn_count,
            )
    
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
            await logger.debug_async(
                "TTS node received empty text, skipping synthesis",
                event_type="tts_empty_input",
                turn_number=self.interview_session.state.total_turn_count,
            )
            return

        full_text = "".join(text_chunks)
        await logger.debug_async(
            f"TTS synthesizing {len(full_text)} characters: {full_text[:100]}...",
            event_type="tts_synthesizing",
            turn_number=self.interview_session.state.total_turn_count,
            text_length=len(full_text),
        )

        # TTS resilience configuration
        TTS_TIMEOUT_SECONDS = 5.0  # Timeout for first audio frame only
        MAX_TTS_RETRIES = 2  # Total attempts including initial try

        for attempt in range(MAX_TTS_RETRIES):
            try:
                # Log TTS synthesis start
                if attempt == 0:
                    await logger.info_async(
                        f"TTS synthesis started",
                        event_type="tts_start",
                        turn_number=self.interview_session.state.total_turn_count,
                        text_length=len(full_text),
                    )

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

                    await logger.info_async(
                        f"TTS synthesis complete — {frame_count} frames",
                        event_type="tts_complete",
                        turn_number=self.interview_session.state.total_turn_count,
                        frame_count=frame_count,
                        attempt=attempt + 1,
                    )
                    return

                except StopAsyncIteration:
                    # TTS stream ended immediately (no frames)
                    await logger.debug_async(
                        f"TTS returned no frames, attempt {attempt + 1}",
                        event_type="tts_no_frames",
                        turn_number=self.interview_session.state.total_turn_count,
                        attempt=attempt + 1,
                    )
                    return

            except asyncio.TimeoutError:
                if attempt < MAX_TTS_RETRIES - 1:
                    await logger.warning_async(
                        f"TTS timeout ({TTS_TIMEOUT_SECONDS}s) on attempt {attempt + 1}/{MAX_TTS_RETRIES}, retrying",
                        event_type="tts_timeout",
                        turn_number=self.interview_session.state.total_turn_count,
                        timeout_seconds=TTS_TIMEOUT_SECONDS,
                        attempt=attempt + 1,
                        max_attempts=MAX_TTS_RETRIES,
                        text_length=len(full_text),
                    )
                    await asyncio.sleep(0.5)  # Brief pause before retry
                else:
                    await logger.error_async(
                        f"🔴 TTS TIMEOUT after {MAX_TTS_RETRIES} attempts — LLM response will be SILENT",
                        event_type="tts_timeout_fatal",
                        turn_number=self.interview_session.state.total_turn_count,
                        max_attempts=MAX_TTS_RETRIES,
                        text_length=len(full_text),
                        text_preview=full_text[:200],
                    )
                    # Fallback to silence (don't crash the session)
                    return

            except Exception as e:
                status = getattr(e, "status_code", "N/A")
                if attempt < MAX_TTS_RETRIES - 1:
                    await logger.warning_async(
                        f"TTS error on attempt {attempt + 1}/{MAX_TTS_RETRIES}, retrying",
                        event_type="tts_error",
                        turn_number=self.interview_session.state.total_turn_count,
                        attempt=attempt + 1,
                        max_attempts=MAX_TTS_RETRIES,
                        status_code=str(status),
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
                    await asyncio.sleep(0.5)  # Brief pause before retry
                else:
                    await logger.error_async(
                        f"🔴 TTS FAILED after {MAX_TTS_RETRIES} attempts — LLM response will be SILENT",
                        event_type="tts_error_fatal",
                        turn_number=self.interview_session.state.total_turn_count,
                        max_attempts=MAX_TTS_RETRIES,
                        status_code=str(status),
                        error_type=type(e).__name__,
                        error_message=str(e),
                        text_preview=full_text[:200],
                    )
                    # Fallback to silence (don't crash the session)
                    return

    async def _generate_scorecard(self):
        """Generate post-interview scorecard. Runs as background task or on session_end."""
        try:
            await logger.info_async(
                "Generating interview scorecard",
                event_type="scorecard_generation_start",
                turn_number=self.interview_session.state.total_turn_count,
                phase=self.interview_session.state.phase.value,
            )
            scorecard = await self._scoring_engine.score_interview(
                self.interview_session, self.config
            )
            self.interview_session.scorecard = scorecard.to_dict()
            saved_path = await self._scoring_engine.save_scorecard(scorecard)
            await logger.info_async(
                f"Scorecard saved: {saved_path}",
                event_type="scorecard_saved",
                turn_number=self.interview_session.state.total_turn_count,
                phase=self.interview_session.state.phase.value,
                file_path=saved_path,
                hire_signal=scorecard.hire_signal,
                overall_score=scorecard.overall_score,
            )
            await self._log_scorecard(scorecard)
        except Exception as e:
            await logger.error_async(
                f"Scorecard generation failed: {e}",
                event_type="scorecard_generation_error",
                turn_number=self.interview_session.state.total_turn_count,
                phase=self.interview_session.state.phase.value,
                exc_info=True,
            )

    async def _log_scorecard(self, scorecard: InterviewScorecard):
        """Log human-readable scorecard for immediate visibility during testing."""
        await logger.info_async(
            "=" * 60,
            event_type="scorecard_display",
        )
        await logger.info_async(
            f"INTERVIEW SCORECARD — {scorecard.hire_signal} ({scorecard.overall_score:.1f}/5)",
            event_type="scorecard_summary",
            hire_signal=scorecard.hire_signal,
            overall_score=scorecard.overall_score,
        )
        await logger.info_async(
            f"Scenario: {scorecard.scenario}",
            event_type="scorecard_scenario",
            scenario=scorecard.scenario,
        )
        for dim_key, dim in scorecard.dimensions.items():
            await logger.info_async(
                f"  {dim_key}: {dim.score}/5 ({dim.label})",
                event_type="scorecard_dimension",
                dimension=dim_key,
                score=dim.score,
                label=dim.label,
            )
            await logger.info_async(
                f"    {dim.rationale}",
                event_type="scorecard_dimension_rationale",
                dimension=dim_key,
                rationale=dim.rationale,
            )
        await logger.info_async(
            f"Narrative: {scorecard.narrative}",
            event_type="scorecard_narrative",
            narrative=scorecard.narrative,
        )
        await logger.info_async(
            "=" * 60,
            event_type="scorecard_display",
        )


def prewarm(proc: agents.JobProcess) -> None:
    """Pre-load heavy models once per worker process before any job arrives."""
    from ..config import AgentConfig
    config = AgentConfig.from_env()

    proc.userdata["turn_detector"] = None  # default: Silero VAD fallback

    if config.use_semantic_turn_detection:
        try:
            logger.info(
                "Loading semantic turn detector model",
                event_type="turn_detector_loading"
            )
            eou = turn_detector.english.EnglishModel()
            proc.userdata["turn_detector"] = eou
            logger.info(
                "Semantic turn detector loaded",
                event_type="turn_detector_loaded"
            )
        except Exception as e:
            logger.warning(
                f"Turn detector failed to load ({e}); sessions will use Silero VAD only",
                event_type="turn_detector_load_failed",
                error_type=type(e).__name__,
                error_message=str(e)
            )


async def entrypoint(ctx: JobContext):
    """
    Entrypoint for LiveKit agent.

    Called when a participant joins the room.
    """
    await logger.info_async(
        f"Agent starting for room: {ctx.room.name}",
        event_type="room_join",
        room_name=ctx.room.name,
    )

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
        await logger.info_async(
            "Cartesia API key loaded",
            event_type="config_loaded",
            key_preview=f"{_key[:4]}...{_key[-4:]}",
        )
    else:
        await logger.error_async(
            "Cartesia API key is EMPTY — check CARTESIA_API_KEY in .env",
            event_type="config_error",
        )

    # Get scenario from job metadata or use default
    from ..interview.scenario_loader import ScenarioLoader
    import json

    # Initialize scenario loader
    scenario_loader = ScenarioLoader()
    await logger.info_async(
        f"Loaded {len(scenario_loader._scenarios)} scenarios",
        event_type="scenarios_loaded",
        scenario_count=len(scenario_loader._scenarios),
    )

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
            await logger.info_async(
                f"Selected scenario: {scenario_metadata.id} (archetype: {scenario_metadata.archetype})",
                event_type="scenario_selected",
                scenario_id=scenario_metadata.id,
                archetype=scenario_metadata.archetype,
            )

        except (json.JSONDecodeError, Exception) as e:
            # Fallback: treat as literal scenario text for backward compatibility
            await logger.warning_async(
                f"Failed to parse job metadata as JSON, using as literal text: {e}",
                event_type="metadata_parse_error",
                error_type=type(e).__name__,
            )
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
    await logger.info_async(
        "STT configured with 5s timeout and error recovery",
        event_type="stt_configured",
        timeout_seconds=5.0,
    )

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
        await logger.info_async(
            "Semantic turn detection active for this session",
            event_type="turn_detection_configured",
            detector_type="semantic",
        )
    else:
        await logger.info_async(
            "Silero VAD turn detection active for this session",
            event_type="turn_detection_configured",
            detector_type="silero_vad",
        )
    session = AgentSession(**session_kwargs)

    # Start session with our custom agent
    await session.start(
        room=ctx.room,
        agent=interview_agent,
    )

    async def handle_graceful_shutdown():
        """Gracefully shut down the session after prolonged disconnect."""
        try:
            await logger.info_async(
                "30s disconnect timeout reached — shutting down session gracefully",
                event_type="session_shutdown",
                reason="disconnect_timeout",
            )
            # Trigger scoring if not already done
            if not interview_agent._scoring_triggered:
                interview_agent._scoring_triggered = True
                await interview_agent._generate_scorecard()
            # Close the room connection
            await ctx.room.disconnect()
        except Exception as e:
            await logger.error_async(
                f"Error during graceful shutdown: {e}",
                event_type="shutdown_error",
                exc_info=True,
            )

    @ctx.room.on("disconnected")
    def on_room_disconnected():
        """Handle room disconnect event."""
        asyncio.create_task(logger.info_async(
            "Agent disconnected from room",
            event_type="room_disconnect",
            room_name=ctx.room.name,
        ))

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        """Handle participant disconnect — don't crash, wait for reconnection."""
        # Only track candidate disconnections (not our agent)
        if participant.kind == rtc.ParticipantKind.STANDARD:
            asyncio.create_task(logger.warning_async(
                f"Participant disconnected: {participant.identity} — waiting for reconnection",
                event_type="participant_disconnected",
                participant_id=participant.identity,
            ))
            disconnect_state["is_disconnected"] = True
            disconnect_state["disconnect_time"] = time.monotonic()

            # Schedule graceful shutdown after 30s if no reconnection
            async def delayed_shutdown():
                try:
                    await asyncio.sleep(30.0)
                    if disconnect_state["is_disconnected"]:
                        await handle_graceful_shutdown()
                except asyncio.CancelledError:
                    await logger.info_async(
                        "Shutdown task cancelled — participant reconnected",
                        event_type="shutdown_cancelled",
                    )
                except Exception as e:
                    await logger.error_async(
                        f"Error in delayed shutdown: {e}",
                        event_type="shutdown_error",
                        exc_info=True,
                    )

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
                asyncio.create_task(logger.info_async(
                    f"Participant reconnected after {disconnect_duration:.1f}s — resuming session",
                    event_type="participant_reconnected",
                    participant_id=participant.identity,
                    disconnect_duration_seconds=round(disconnect_duration, 1),
                ))

                # Cancel shutdown task
                if disconnect_state["shutdown_task"]:
                    disconnect_state["shutdown_task"].cancel()
                    disconnect_state["shutdown_task"] = None

                # Clear disconnect state
                disconnect_state["is_disconnected"] = False
                disconnect_state["disconnect_time"] = None

                # Session state is preserved server-side, so resume works automatically
                asyncio.create_task(logger.info_async(
                    "Session state preserved — participant can continue interview",
                    event_type="session_resumed",
                ))
            else:
                asyncio.create_task(logger.info_async(
                    f"New participant connected: {participant.identity}",
                    event_type="participant_connected",
                    participant_id=participant.identity,
                ))

    @session.on("agent_speech_interrupted")
    def on_interrupted():
        phase = interview_agent.interview_session.state.phase
        asyncio.create_task(logger.info_async(
            "Interviewer interrupted by candidate — listening",
            event_type="agent_interrupted",
            turn_number=interview_agent.interview_session.state.total_turn_count,
            phase=phase.value,
        ))
        if phase == InterviewPhase.INTRO:
            interview_agent._intro_interrupted = True
            asyncio.create_task(logger.info_async(
                "Interrupted during INTRO — will recover scenario on next turn",
                event_type="intro_interrupted",
                turn_number=interview_agent.interview_session.state.total_turn_count,
            ))
        elif phase == InterviewPhase.FAILURE:
            interview_agent._failure_setup_interrupted = True
            asyncio.create_task(logger.info_async(
                "Interrupted during FAILURE — will recover scenario setup on next turn",
                event_type="failure_interrupted",
                turn_number=interview_agent.interview_session.state.total_turn_count,
            ))

    @session.on("session_end")
    def on_session_end():
        """Fallback: score partial interviews if WRAP was never reached."""
        asyncio.create_task(logger.info_async(
            "Session ended",
            event_type="session_end",
            turn_number=interview_agent.interview_session.state.total_turn_count,
            phase=interview_agent.interview_session.state.phase.value,
            scoring_triggered=interview_agent._scoring_triggered,
        ))
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
            asyncio.create_task(logger.info_async(
                f"⚡ TURN {turn_number}: STT={stt_ms:.0f}ms LLM_TTFT={llm_ttft_ms:.0f}ms "
                f"TTS_TTFB={tts_ttfb_ms:.0f}ms TOTAL={total_ms:.0f}ms",
                event_type="turn_metrics",
                turn_number=turn_number,
                stt_ms=int(stt_ms),
                llm_ttft_ms=int(llm_ttft_ms),
                tts_ttfb_ms=int(tts_ttfb_ms),
                total_ms=int(total_ms),
            ))

        # Log additional metrics for debugging
        if hasattr(event, "llm_total_duration") and event.llm_total_duration:
            llm_total_ms = event.llm_total_duration * 1000
            asyncio.create_task(logger.debug_async(
                f"⚡ TURN {turn_number}: LLM_Total={llm_total_ms:.0f}ms",
                event_type="llm_total_duration",
                turn_number=turn_number,
                llm_total_ms=int(llm_total_ms),
            ))

        # Log LLM token usage to validate theoretical token budget
        input_tokens = getattr(event, 'input_tokens', None) or getattr(event, 'llm_input_tokens', None)
        output_tokens = getattr(event, 'output_tokens', None) or getattr(event, 'llm_output_tokens', None)
        cache_read = getattr(event, 'cache_read_input_tokens', None) or getattr(event, 'llm_cache_read_input_tokens', None)
        if input_tokens is not None:
            asyncio.create_task(logger.info_async(
                f"📊 LLM tokens — input: {input_tokens}, output: {output_tokens or 0}, cache_read: {cache_read or 0}",
                event_type="llm_tokens",
                turn_number=turn_number,
                input_tokens=input_tokens,
                output_tokens=output_tokens or 0,
                cache_read_tokens=cache_read or 0,
            ))

    # Send initial greeting using session.say() - skips LLM entirely for faster start
    # Strip leading "Design " from scenario name to avoid "We're designing Design a URL Shortener"
    display_name = scenario_text.removeprefix("Design ").removeprefix("design ")
    intro_text = f"Hey there. We're designing {display_name}. What questions do you have?"
    await session.say(intro_text, allow_interruptions=True)

    await logger.info_async(
        "Interview session started",
        event_type="interview_started",
        scenario=scenario_text,
        room_name=ctx.room.name,
    )


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
