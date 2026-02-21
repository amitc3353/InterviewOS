"""Local microphone transport - Phase 1 implementation."""

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

    def __init__(self, scenario: str = "payments"):
        """
        Initialize local mic transport.

        Args:
            scenario: Interview scenario
        """
        self.scenario = scenario

        # Adapters
        self.stt = STTAdapter()
        self.llm = LLMAdapter()
        self.tts = TTSAdapter()
        self.audio_out = AudioOutAdapter()

        # State
        self.is_recording = False
        self.stream = None
        self.current_partial = ""
        self.audio_chunks_sent = 0

        # Keyboard listener
        self.listener = None

    def run(self, engine: InterviewEngine) -> None:
        """
        Run the interview loop.

        Args:
            engine: InterviewEngine instance
        """
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

        # Start STT
        self.stt.on_partial(self._on_partial_transcript)
        self.stt.start_listening()

        # Audio chunk counter for debugging
        self.audio_chunks_sent = 0

        # Start audio stream
        def audio_callback(indata, frames, time, status):
            if status:
                print(f"⚠️  Audio status: {status}")

            # Send to STT
            audio_bytes = (indata * 32767).astype(np.int16).tobytes()

            # Debug: Log audio level
            audio_level = np.abs(indata).mean()
            if audio_level > 0.01:  # Only log if there's actual sound
                self.audio_chunks_sent += 1
                if self.audio_chunks_sent % 10 == 0:  # Log every 10 chunks
                    print(
                        f"🎵 Audio level: {audio_level:.3f} (chunk #{self.audio_chunks_sent})"
                    )

            self.stt.send_audio(audio_bytes)

        self.stream = sd.InputStream(
            samplerate=16000, channels=1, dtype="float32", callback=audio_callback
        )
        self.stream.start()
        print("🎙️  Microphone active - speak now!")

    def _stop_recording(self):
        """Stop recording and process transcript."""
        if not self.is_recording:
            return

        print("\n⏹️  Processing...")
        self.is_recording = False

        # Stop stream
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        # Get final transcript
        print(f"🎵 Total audio chunks sent: {self.audio_chunks_sent}")
        self.audio_chunks_sent = 0  # Reset for next recording

        try:
            transcript = self.stt.stop_listening()
            print(f"📋 Raw transcript: '{transcript}'")
        except Exception as e:
            print(f"❌ STT error: {e}")
            return

        if not transcript.strip():
            print("❌ No speech detected. Try again.")
            print("💡 Tip: Speak clearly and loudly. Check mic permissions.\n")
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
        print("🤔 Interviewer is thinking...")

        # Mock engine call for now - will refactor to pass engine properly
        # This is a quick implementation for Phase 1
        context = {
            "scenario": self.scenario,
            "turn_count": 1,
            "current_phase": "requirements_gathering",
            "candidate_transcript": transcript,
            "platform_context": "",
            "history": [],
        }

        response = self.llm.get_next_question(context)
        self._speak_question(response)

    def _speak_question(self, response: dict):
        """Synthesize and play interviewer's question."""
        question = response.get("question", "")

        if not question:
            return

        print(f"\n💬 Interviewer: {question}\n")

        # Synthesize
        print("🔊 Generating audio...")
        audio_buffer = self.tts.synthesize(question)

        # Play
        print("▶️  Playing...\n")
        self.audio_out.play(audio_buffer)

        print("✅ Ready! Press SPACEBAR to respond...\n")

    def _cleanup(self):
        """Clean up resources."""
        if self.stream:
            self.stream.stop()
            self.stream.close()

        if self.listener:
            self.listener.stop()
