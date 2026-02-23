# InterviewOS

Voice-based AI interview simulator for Staff-level (L5→L6) system design interviews.

## What is this?

InterviewOS is a real-time voice interview platform that helps senior engineers practice system design interviews with AI-powered interviewers. Unlike generic ChatGPT sessions, InterviewOS provides:

- **Structured phases** - Intro → Exploration → Constraints → Depth → Closing
- **Realistic probing** - AI asks follow-up questions like a real Staff engineer
- **Locked constraints** - Tracks your architectural decisions
- **Natural conversation** - No push-to-talk, just speak naturally
- **Low latency** - <2s response time for realistic flow

## Quick Start

### 1. Clone and Setup

```bash
git clone <repo>
cd InterviewOS
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Fill in your API keys in `.env`:
- **LiveKit**: Sign up at [livekit.io](https://livekit.io) (free tier)
- **Deepgram**: Sign up at [deepgram.com](https://deepgram.com) ($200 free credits)
- **Anthropic**: Your existing Claude API key
- **OpenAI**: Your existing OpenAI API key

### 4. Test Setup

```bash
python backend/test_setup.py
```

Should show all green checkmarks ✓

### 5. Run Interview

```bash
python backend/run_interview.py
```

Or with a custom scenario:

```bash
python backend/run_interview.py "Design a payment gateway"
```

### 6. Connect and Interview

Connect via LiveKit client (web or mobile) and start speaking!

## Project Structure

```
InterviewOS/
├── backend/
│   ├── agents/              # LiveKit agent
│   │   └── interview_agent.py
│   ├── adapters/            # STT/LLM/TTS adapters (modular)
│   ├── interview/           # Interview logic
│   │   ├── phase_manager.py       # Phase transitions & prompts
│   │   └── response_parser.py     # JSON parsing with fallback
│   ├── models/              # Data models
│   │   └── session.py
│   ├── utils/
│   ├── config.py            # Configuration
│   ├── run_interview.py     # Entry point
│   └── test_setup.py        # Setup verification
├── .env.example             # Environment template
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Architecture

```
User (mic)
    ↓
LiveKit WebRTC
    ↓
Silero VAD (voice activity detection)
    ↓
Deepgram STT (speech-to-text)
    ↓
Interview Engine
  - Phase Manager (tracks current phase, builds prompts)
  - Session State (locked constraints, history)
    ↓
Claude Sonnet (interviewer brain)
    ↓
Response Parser (JSON → spoken text + state updates)
    ↓
OpenAI TTS (text-to-speech)
    ↓
LiveKit WebRTC
    ↓
User (speaker)
```

### Modular Design

All components are swappable:
- **STT**: Deepgram (default) → Whisper (future)
- **LLM**: Claude (default) → GPT-4 (future)
- **TTS**: OpenAI (default) → Cartesia (future)

Change providers in `backend/config.py` - no code changes needed.

## How It Works

### Interview Phases

1. **Intro (2 min)** - Problem statement, clarifying questions
2. **Exploration (10 min)** - High-level architecture
3. **Constraints (10 min)** - Scale, latency, failure modes
4. **Depth (15 min)** - Deep-dive on specific components
5. **Closing (8 min)** - Summary, tradeoffs, operational concerns

Phases transition automatically based on elapsed time.

### Locked Constraints

The AI tracks your architectural decisions:
- "We'll use PostgreSQL for transactions"
- "Cache TTL is 5 minutes"
- "We're designing for 100K requests/sec"

Once locked, you must work within these constraints (like a real interview).

### Turn-Taking

Uses **two-layer detection**:
1. **Silero VAD** - Detects when you start/stop speaking
2. **Semantic Turn Detection** - Distinguishes "thinking pause" from "done talking"

Result: Natural conversation without awkward pauses or false triggers.

## Cost

Approximately **$0.43 per 45-minute session**:

| Component | Cost |
|-----------|------|
| LiveKit | Free tier |
| Deepgram STT | $0.35 |
| Claude Sonnet | $0.03 |
| OpenAI TTS | $0.05 |

Compare to human mock interviews: $200-400/session.

## Development

See `backend/README.md` for detailed architecture, hooks, and development guide.

## Roadmap

- [x] Real-time voice pipeline
- [x] Phase management
- [x] Locked constraints tracking
- [ ] Session recording
- [ ] Web frontend
- [ ] Scoring rubric
- [ ] Multiple scenarios (15 total)
- [ ] Session replay
- [ ] Analytics dashboard

## Support

For issues or questions, check `backend/README.md` troubleshooting section.
