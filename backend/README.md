# InterviewOS Backend

Real-time voice interview simulation using LiveKit Agents.

## Architecture

```
User (mic) → LiveKit → Silero VAD → Deepgram STT → Interview Engine → Claude → Response Parser → OpenAI TTS → User (speaker)
                                                            ↓
                                                    Session State
                                                    (phase, constraints)
```

### Key Components

1. **LiveKit Agent** (`agents/interview_agent.py`)
   - Orchestrates the entire pipeline
   - Manages participant connections
   - Handles hooks for custom logic

2. **Interview Engine** (`interview/`)
   - `PhaseManager`: Manages interview phases and generates system prompts
   - `ResponseParser`: Parses Claude's JSON responses with fallback

3. **Models** (`models/`)
   - `InterviewSession`: Complete session data
   - `SessionState`: Current phase, locked constraints, conversation history
   - `InterviewPhase`: Enum of interview phases

4. **Config** (`config.py`)
   - Environment-based configuration
   - Swappable provider settings

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp ../.env.example ../.env
```

Required keys:
- `LIVEKIT_URL` - Your LiveKit Cloud WebSocket URL
- `LIVEKIT_API_KEY` - LiveKit API key
- `LIVEKIT_API_SECRET` - LiveKit API secret
- `DEEPGRAM_API_KEY` - Deepgram API key
- `ANTHROPIC_API_KEY` - Anthropic API key
- `OPENAI_API_KEY` - OpenAI API key

### 3. Run the Agent

```bash
python backend/run_interview.py
```

Or with a custom scenario:

```bash
python backend/run_interview.py "Design a payment gateway"
```

## Interview Flow

### Phases (45 minutes total)

1. **Intro** (2 min) - Problem statement, clarifying questions
2. **Exploration** (10 min) - High-level architecture, initial design
3. **Constraints** (10 min) - Scale requirements, realistic constraints
4. **Depth** (15 min) - Deep-dive on specific components
5. **Closing** (8 min) - Summary, tradeoffs, operational concerns

### State Management

The `SessionState` tracks:
- Current phase
- Locked constraints (decisions candidate commits to)
- Conversation history
- Phase timing

### LLM Response Format

Claude responds with structured JSON:

```json
{
  "phase": "exploration",
  "interviewer_says": "That's a reasonable approach.",
  "question": "Why did you choose a relational database over NoSQL?",
  "update_locked_constraints": ["Using PostgreSQL for transactions"]
}
```

The `ResponseParser` extracts:
- Spoken text: `interviewer_says + question`
- State updates: `update_locked_constraints`

If JSON parsing fails, it falls back to using raw text (no state updates).

## Modularity

Components are swappable via config:

### Change STT Provider
```python
# In config.py
stt_provider: str = "deepgram"  # or "whisper" (when implemented)
```

### Change LLM Provider
```python
# In config.py
llm_provider: str = "anthropic"  # or "openai" (when implemented)
llm_model: str = "claude-sonnet-4-20250514"
```

### Change TTS Provider
```python
# In config.py
tts_provider: str = "openai"  # or "cartesia" (when implemented)
tts_voice: str = "echo"  # alloy, echo, fable, onyx, nova, shimmer
```

### Tune Turn Detection
```python
# In config.py
vad_sensitivity: float = 0.5  # 0.0-1.0 (higher = more sensitive)
silence_threshold_ms: int = 600  # milliseconds before turn ends
use_semantic_turn_detection: bool = True  # Use both VAD + semantic
```

## Hooks

The agent uses LiveKit's hook system for custom logic:

### `before_llm_cb`
Called before LLM processes user input.

- Injects current phase context
- Updates system prompt dynamically
- Adds locked constraints to context

### `before_tts_cb`
Called before TTS converts text to speech.

- Parses JSON response
- Updates session state (constraints, phase)
- Extracts spoken text only
- Returns clean text for TTS

## Testing

### End-to-End Test

1. Start the agent: `python backend/run_interview.py`
2. Connect via LiveKit client (web or mobile)
3. Speak naturally - no push-to-talk needed
4. Agent should respond within 1-2 seconds
5. Try interrupting the agent mid-response

### What to Validate

- [ ] Natural turn-taking (no awkward pauses)
- [ ] Can interrupt AI mid-response
- [ ] AI waits for you to finish speaking
- [ ] Latency <2s (you stop → AI responds)
- [ ] Phase transitions happen automatically
- [ ] Locked constraints are tracked
- [ ] Transcript is accurate

## Troubleshooting

### "Invalid configuration" error
Check that all environment variables are set in `.env`.

### Agent doesn't respond
- Check microphone permissions
- Verify LiveKit connection (check logs for WebSocket errors)
- Check API keys are valid

### Turn-taking feels unnatural
Tune `vad_sensitivity` and `silence_threshold_ms` in config:
- Too sensitive: False triggers, cuts you off mid-thought
- Not sensitive enough: Long awkward pauses

### JSON parsing errors
Check logs for "JSON parse failed" warnings. The fallback should handle this gracefully, but if it happens frequently, review the system prompt.

## Next Steps

- [ ] Add session recording/storage
- [ ] Build web frontend for client connection
- [ ] Add scoring rubric evaluation
- [ ] Implement multiple scenarios
- [ ] Add session replay feature
- [ ] Build analytics dashboard

## Cost Tracking

Approximate costs per 45-minute session:

| Component | Cost |
|-----------|------|
| LiveKit | Free tier (5K participant-min/month) |
| Deepgram STT | ~$0.35 (45 min × $0.0077/min) |
| Claude Sonnet | ~$0.03 (~8K tokens × $3/1M) |
| OpenAI TTS | ~$0.05 (~3K chars × $15/1M) |
| **Total** | **~$0.43/session** |
