# InterviewOS

AI-powered system design interview practice platform.

## Setup

1. Copy `.env.example` to `.env` and add your API keys
2. Install dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```

## Usage

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

- `app/stt.py` - Deepgram speech-to-text
- `app/tts.py` - Deepgram text-to-speech  
- `app/interviewer.py` - Claude-powered AI interviewer
- `app/scorer.py` - Claude-powered rubric scoring
- `app/config.py` - Environment + path management
- `INTERVIEW_PLATFORM_CONTEXT.md` - Rubric, format, interviewer behavior

## Requirements

- Python 3.8+
- API keys: Anthropic (Claude), Deepgram, Daily.co (optional)
