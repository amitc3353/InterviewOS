"""Local microphone transport - Phase 1 implementation."""

import random
import sounddevice as sd
import numpy as np
from pynput import keyboard
from app.transport.base import Transport
from app.engine import InterviewEngine
from app.adapters import STTAdapter, LLMAdapter, TTSAdapter, AudioOutAdapter


class LocalMicTransport(Transport):
    """
    Local microphone transport with push-to-talk.

    Phase 1: Half-duplex voice loop
    - Press SPACEBAR to talk
    - Release SPACEBAR to submit
    - Mic muted during TTS playback
    """

    def __init__(self, scenario: str = "payments", voice_config: str = "nova_hd"):
        """
        Initialize local mic transport.

        Args:
            scenario: Interview scenario
            voice_config: TTS voice preset (alloy_hd, onyx_hd, nova_hd)
        """
        self.scenario = scenario

        # Adapters
        self.stt = STTAdapter()
        self.llm = LLMAdapter()
        self.tts = TTSAdapter(voice_config=voice_config)
        self.audio_out = AudioOutAdapter()

        # State
        self.is_recording = False
        self.stream = None
        self.current_partial = ""
        self.audio_chunks_sent = 0
        self.engine: InterviewEngine | None = None  # Will be set in run()

        # Keyboard listener
        self.listener = None

    def run(self, engine: InterviewEngine) -> None:
        """
        Run the interview loop.

        Args:
            engine: InterviewEngine instance
        """
        # Store engine reference
        self.engine = engine

        print("\n🎤 InterviewOS - Voice Mode (Phase 1)")
        print("=" * 50)
        print(f"Scenario: {self.scenario}")
        print("\nControls:")
        print("  SPACEBAR (hold) - Talk")
        print("  SPACEBAR (release) - Submit")
        print("  ESC - Exit\n")
        print("=" * 50)

        # Start session
        opening = engine.start(self.scenario)
        self._speak_question(opening)

        # Start keyboard listener
        self.listener = keyboard.Listener(
            on_press=self._on_key_press, on_release=self._on_key_release
        )
        self.listener.start()

        print("\n✅ Ready! Press SPACEBAR to start talking...\n")

        # Keep running until ESC
        try:
            self.listener.join()
        except KeyboardInterrupt:
            print("\n\n👋 Interview ended.")
            self._cleanup()

    def _on_key_press(self, key):
        """Handle key press events."""
        try:
            if key == keyboard.Key.space and not self.is_recording:
                self._start_recording()
            elif key == keyboard.Key.esc:
                print("\n\n👋 Exiting...")
                self._cleanup()
                self.listener.stop()
                return False
        except Exception as e:
            print(f"Error: {e}")

    def _on_key_release(self, key):
        """Handle key release events."""
        try:
            if key == keyboard.Key.space and self.is_recording:
                self._stop_recording()
        except Exception as e:
            print(f"Error: {e}")

    def _start_recording(self):
        """Start recording audio."""
        if self.audio_out.is_playing:
            return  # Don't record while playing

        print("🎤 Recording... (release SPACEBAR to submit)")
        self.is_recording = True
        self.current_partial = ""
        self.audio_chunks_sent = 0  # Reset counter

        # Start STT
        self.stt.on_partial(self._on_partial_transcript)
        try:
            self.stt.start_listening()
        except Exception as e:
            print(f"❌ STT connection failed: {e}")
            self.is_recording = False
            return

        # Start audio stream
        def audio_callback(indata, frames, time, status):
            if status:
                print(f"⚠️  Audio status: {status}")

            # Apply gain boost to compensate for quiet Mac mic signal
            boosted = np.clip(indata * 6.0, -1.0, 1.0)
            audio_bytes = (boosted * 32767).astype(np.int16).tobytes()

            self.audio_chunks_sent += 1

            self.stt.send_audio(audio_bytes)

        self.stream = sd.InputStream(
            samplerate=16000, channels=1, dtype="float32", callback=audio_callback
        )
        self.stream.start()

    def _stop_recording(self):
        """Stop recording and process transcript."""
        if not self.is_recording:
            return

        print("\n⏹️  Processing...")
        self.is_recording = False

        # Stop stream (defensive cleanup)
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        except Exception as e:
            print(f"⚠️  Stream cleanup warning: {e}")
        finally:
            self.stream = None

        # Get final transcript
        self.audio_chunks_sent = 0  # Reset for next recording

        try:
            transcript = self.stt.stop_listening()
        except Exception as e:
            print(f"❌ STT error: {e}")
            return

        if not transcript.strip():
            print("❌ No speech detected. Try again.\n")
            return

        print(f"\n📝 You said: {transcript}\n")

        # Process turn
        self._process_turn(transcript)

    def _on_partial_transcript(self, text: str):
        """Handle partial transcript for live feedback."""
        if text != self.current_partial:
            self.current_partial = text
            # Could print live transcript here if desired
            # print(f"\r{text}", end="", flush=True)

    def _process_turn(self, transcript: str):
        """Process candidate's response and get next question."""
        if not self.engine or not self.engine.session:
            print("❌ Error: Engine not initialized")
            return

        # LATENCY MASKING: Play thinking filler immediately
        thinking_filler = random.choice(self.THINKING_FILLERS)
        print(f"💭 {thinking_filler}")

        # Synthesize and play filler while LLM is thinking
        filler_audio = self.tts.synthesize(thinking_filler)
        self.audio_out.play(filler_audio)

        # Get context from engine (includes history, locked constraints, phase)
        context = self.engine.process_turn(transcript)

        # Debug logging
        print(
            f"[DEBUG] Turn: {context['turn_count']}, Phase: {context['current_phase']}"
        )
        print(f"[DEBUG] History length: {len(context['history'])}")

        # Call LLM with full context
        response = self.llm.get_next_question(context)

        # Record turn in engine (updates history, locked constraints, phase)
        self.engine.record_turn(transcript, response)

        # Speak the question
        self._speak_question(response)

    def _speak_question(self, response: dict):
        """Synthesize and play interviewer's question."""
        # Use interviewer_says for TTS (conversational), question is the actual probe
        interviewer_says = response.get("interviewer_says", "")
        question = response.get("question", "")

        # Combine for natural flow
        full_message = f"{interviewer_says} {question}".strip()

        if not full_message:
            return

        print(f"\n💬 Interviewer: {full_message}\n")

        # Synthesize and play
        audio_buffer = self.tts.synthesize(full_message)
        self.audio_out.play(audio_buffer)

        print("✅ Ready! Press SPACEBAR to respond...\n")

    def _cleanup(self):
        """Clean up resources with defensive shutdown."""
        # Stop audio playback
        try:
            self.audio_out.stop()
        except Exception as e:
            print(f"⚠️  Audio stop warning: {e}")

        # Stop mic stream
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        except Exception as e:
            print(f"⚠️  Stream cleanup warning: {e}")
        finally:
            self.stream = None

        # Stop keyboard listener
        try:
            if self.listener:
                self.listener.stop()
        except Exception as e:
            print(f"⚠️  Listener cleanup warning: {e}")
        finally:
            self.listener = None
