# InterviewOS Architecture

## Design Principles

1. **Strict separation**: Interview Engine vs Transport
2. **Modular adapters**: Swap transport without changing interview logic
3. **Interface-first**: Define contracts before implementation

## Core Modules (Phase-independent)

### InterviewEngine
- **Responsibility**: Session state machine, turn management, scenario logic
- **Interface**: `start()`, `process_turn(transcript)`, `get_state()`
- **Does NOT know about**: Audio, microphone, WebRTC, networking

### STTAdapter
- **Responsibility**: Streaming transcript events
- **Interface**: `start_listening()`, `stop_listening()`, `on_transcript(callback)`
- **Implementation**: Deepgram streaming API

### LLMAdapter
- **Responsibility**: Generate interviewer responses
- **Interface**: `get_next_question(context, transcript)` → structured response
- **Implementation**: Claude (Anthropic API)

### TTSAdapter
- **Responsibility**: Text → audio
- **Interface**: `synthesize(text)` → audio buffer
- **Implementation**: OpenAI TTS

### AudioOutAdapter
- **Responsibility**: Play audio
- **Interface**: `play(audio_buffer)`, `stop()`
- **Implementation**: sounddevice / pyaudio

## Transport Adapters (Swappable)

### LocalMicTransport (Phase 1)
- Push-to-talk (spacebar)
- Local microphone capture
- Half-duplex (mute mic during TTS playback)
- CLI-based

### DailyTransport (Phase 2)
- WebRTC via Daily.co
- Full-duplex with VAD
- Web-accessible
- Handles echo cancellation

## Phase 1 Loop (Half-Duplex)

```
1. User presses SPACEBAR → start recording
2. Streaming STT → partial transcripts
3. User releases SPACEBAR → finalize transcript
4. InterviewEngine.process_turn(transcript) → next question
5. LLMAdapter.get_next_question() → structured response
6. TTSAdapter.synthesize(question) → audio
7. AudioOutAdapter.play(audio)
8. (mic muted during playback)
9. Repeat from step 1
```

## Folder Structure

```
app/
  engine/
    __init__.py
    interview_engine.py      # Core state machine
    session.py               # Session state
  
  adapters/
    __init__.py
    stt_adapter.py           # Interface + Deepgram impl
    llm_adapter.py           # Interface + Claude impl
    tts_adapter.py           # Interface + OpenAI TTS impl
    audio_out_adapter.py     # Interface + sounddevice impl
  
  transport/
    __init__.py
    base.py                  # Transport interface
    local_mic.py             # Phase 1: LocalMicTransport
    daily.py                 # Phase 2: DailyTransport (future)
  
  cli.py                     # Existing CLI commands
  realtime.py                # NEW: Real-time voice mode entry point
```

## Contracts

### InterviewEngine API
```python
class InterviewEngine:
    def start(scenario: str) -> dict
    def process_turn(transcript: str) -> dict
    def get_state() -> dict
```

### STTAdapter API
```python
class STTAdapter:
    def start_listening() -> None
    def stop_listening() -> str  # Returns finalized transcript
    def on_partial(callback: Callable[[str], None]) -> None
```

### LLMAdapter API
```python
class LLMAdapter:
    def get_next_question(session_state: dict, transcript: str) -> dict
```

### TTSAdapter API
```python
class TTSAdapter:
    def synthesize(text: str) -> bytes
```

### AudioOutAdapter API
```python
class AudioOutAdapter:
    def play(audio_buffer: bytes) -> None
    def stop() -> None
```

### Transport API
```python
class Transport:
    def run(engine: InterviewEngine) -> None
```

## Phase 2 Migration

To switch to Daily.co:
1. Implement `DailyTransport` following Transport interface
2. Swap in `realtime.py`: `transport = DailyTransport()`
3. No changes to engine/, adapters/ — just transport layer

**Goal**: 95% of code unchanged between Phase 1 and Phase 2.
