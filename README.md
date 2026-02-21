# InterviewOS

AI-powered system design interview practice platform.

## Setup

1. Copy `.env.example` to `.env` and add your API keys
2. Install dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```

## Modes

### 🎤 Real-Time Voice Mode (NEW - Phase 1)
Interactive push-to-talk voice interview:
```bash
python3 -m app.realtime --scenario payments
```

**Controls:**
- **SPACEBAR (hold)** - Talk
- **SPACEBAR (release)** - Submit your response
- **ESC** - Exit interview

**Flow:**
1. Interviewer asks opening question (plays audio)
2. Press and hold SPACEBAR while speaking
3. Release SPACEBAR to submit
4. Interviewer responds with follow-up (audio)
5. Repeat

Half-duplex: microphone muted during TTS playback.

---

## CLI Mode (Batch Processing)

### Usage

### STT (Speech-to-Text)
Transcribe audio files to text:
```bash
python3 -m app stt --file path/to/audio.wav
```

Output: saves transcript JSON to `/transcripts`

### Interview Loop
Get AI interviewer questions:
```bash
# Opening question
python3 -m app interview --scenario payments --start

# Follow-up based on your response
python3 -m app interview --scenario payments --input "I would start by..."

# Verbose mode (shows intent + tips)
python3 -m app interview --scenario payments --input "..." --verbose
```

Scenarios: `payments`, `social_feed`, `e_commerce`, `ride_sharing`, `video_streaming`

### TTS (Text-to-Speech)
Generate audio from text:
```bash
python3 -m app tts --text "Can you explain your approach?"
```

Output: saves MP3 to `/audio`

### Scoring
Evaluate interview performance:
```bash
python3 -m app score --transcript transcripts/20260221_095500.json
```

Output: 
- 5 dimensions scored 0-10 each (total out of 50)
- 2 strengths, 2 improvements
- Next focus recommendation
- Saves to `/scores`

## Workflow

1. **Practice session**: Use `interview` to get questions, respond verbally
2. **Record your responses** (audio)
3. **Transcribe**: `stt --file your-response.wav`
4. **Score**: `score --transcript transcripts/xyz.json`
5. **Review feedback** and iterate

## Architecture

**Modular design for easy transport swapping (Phase 1 → Phase 2)**

```
app/
  engine/              # Core business logic (phase-independent)
    interview_engine.py  - Session state machine
    session.py          - Session state management
  
  adapters/            # Service adapters (swappable)
    stt_adapter.py      - Deepgram streaming STT
    llm_adapter.py      - Claude interviewer
    tts_adapter.py      - OpenAI TTS
    audio_out_adapter.py - sounddevice playback
  
  transport/           # Transport layer (swappable)
    local_mic.py        - Phase 1: Push-to-talk local mic
    daily.py            - Phase 2: Daily.co WebRTC (future)
  
  realtime.py          - Voice mode entry point
  cli.py               - Batch CLI commands
```

See `ARCHITECTURE.md` for full design principles and contracts.

**Legacy modules (still functional):**
- `app/stt.py` - Batch Deepgram STT
- `app/tts.py` - Batch Deepgram TTS  
- `app/interviewer.py` - Batch Claude interviewer
- `app/scorer.py` - Claude rubric scoring

## Requirements

- Python 3.8+
- API keys: Anthropic (Claude), OpenAI (TTS), Deepgram (STT), Daily.co (Phase 2)
