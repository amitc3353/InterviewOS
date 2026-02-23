# Next Steps: Real-Time Voice Feature (LiveKit Agents)

**Goal:** Natural conversation flow with automatic turn-taking  
**Approach:** LiveKit Agents + Silero VAD + Deepgram + Claude + OpenAI TTS  
**Timeline:** 3-5 days to working prototype  
**Principle:** Keep everything modular (swappable STT/LLM/TTS)

---

## Division of Labor

### 🤖 Atlas Tasks (Autonomous)
Things I can do without you:

1. **Research & Documentation**
   - Deep-dive LiveKit Agents docs
   - Research Deepgram Nova-3 best practices
   - Document VAD tuning parameters
   - Create architecture diagrams

2. **Code Scaffolding**
   - Set up project structure (modular)
   - Create adapter interfaces for STT/LLM/TTS
   - Write configuration management (swap providers easily)
   - Create mock implementations for testing
   - Write session state management
   - Create interview phase logic integration

3. **Interview Engine Integration**
   - Port existing interviewer behavior spec to LiveKit
   - Implement phase transitions (intro → exploration → constraints → depth → closing)
   - Wire scoring rubric logic
   - Create transcript + session recording structure

4. **Documentation & Planning**
   - Write setup guide
   - Document API key requirements
   - Create testing checklist
   - Document cost tracking approach

### 👨‍💻 Amit Tasks (Manual/Interactive)
Things only you can do:

1. **Account Setup**
   - Sign up for LiveKit Cloud (free tier)
   - Get LiveKit API credentials
   - Sign up for Deepgram (or use existing)
   - Get Deepgram API key

2. **Environment Setup**
   - Install dependencies (`pip install livekit livekit-agents`)
   - Configure `.env` with API keys
   - Set up local development environment
   - Test microphone/audio permissions

3. **Testing & Validation**
   - Run first end-to-end test (mic → speaker)
   - Test actual interview conversation
   - Validate turn-taking feels natural
   - Check interruption handling
   - Assess audio quality
   - Provide feedback on interviewer behavior

4. **Tuning & Iteration**
   - Adjust VAD sensitivity (based on your mic/environment)
   - Tune silence threshold (how long before AI responds)
   - Test different TTS voices
   - Validate scoring accuracy

---

## Step-by-Step Plan

### Phase 1: Setup & Scaffolding (Day 1)

#### Atlas:
- [x] Research LiveKit Agents architecture
- [ ] Create modular project structure:
  ```
  InterviewOS/
  ├── backend/
  │   ├── agents/           # LiveKit agent logic
  │   │   ├── __init__.py
  │   │   ├── interview_agent.py
  │   │   └── config.py
  │   ├── adapters/         # Modular adapters (STT/LLM/TTS)
  │   │   ├── __init__.py
  │   │   ├── stt_adapter.py
  │   │   ├── llm_adapter.py
  │   │   └── tts_adapter.py
  │   ├── interview/        # Interview logic (provider-agnostic)
  │   │   ├── __init__.py
  │   │   ├── phases.py
  │   │   ├── prompts.py
  │   │   └── scoring.py
  │   ├── models/           # Data models
  │   │   ├── __init__.py
  │   │   ├── session.py
  │   │   └── transcript.py
  │   └── utils/
  │       ├── __init__.py
  │       └── logger.py
  ├── frontend/             # (later)
  ├── .env.example
  ├── requirements.txt
  └── README.md
  ```
- [ ] Write adapter interfaces (swappable components)
- [ ] Document API key requirements
- [ ] Create setup guide

#### Amit:
- [ ] Sign up for LiveKit Cloud → get API keys
- [ ] Sign up for Deepgram → get API key
- [ ] Create `.env` file with credentials:
  ```
  LIVEKIT_URL=wss://your-project.livekit.cloud
  LIVEKIT_API_KEY=your_api_key
  LIVEKIT_API_SECRET=your_api_secret
  DEEPGRAM_API_KEY=your_deepgram_key
  ANTHROPIC_API_KEY=your_claude_key
  OPENAI_API_KEY=your_openai_key
  ```

**Handoff:** Atlas creates scaffolding → Amit sets up accounts & env

---

### Phase 2: Core Agent Implementation (Day 2)

#### Atlas:
- [ ] Implement `STTAdapter` (Deepgram integration)
  - Streaming transcription
  - Interim results handling
  - End-of-utterance detection
- [ ] Implement `LLMAdapter` (Claude integration)
  - Maintain conversation history
  - Interview phase awareness
  - Streaming response handling
- [ ] Implement `TTSAdapter` (OpenAI TTS integration)
  - Stream audio back to user
  - Handle interruptions
- [ ] Implement `InterviewAgent` (LiveKit agent)
  - Wire VAD (Silero)
  - Connect adapters
  - Basic turn-taking logic
- [ ] Create minimal test scenario ("Design a URL shortener")

#### Amit:
- [ ] Install dependencies:
  ```bash
  cd InterviewOS
  pip install -r requirements.txt
  ```
- [ ] Run basic connection test:
  ```bash
  python backend/agents/test_connection.py
  ```
- [ ] Verify all API keys work

**Handoff:** Atlas writes code → Amit verifies setup works

---

### Phase 3: Interview Logic Integration (Day 3)

#### Atlas:
- [ ] Port interviewer behavior spec to agent:
  - System prompt with phase instructions
  - Locked constraints enforcement
  - Probing questions logic
  - Time tracking
- [ ] Implement phase transitions:
  - Intro (2 min)
  - Exploration (10 min)
  - Constraints (10 min)
  - Deep-dive (15 min)
  - Closing (8 min)
- [ ] Add session state management:
  - Track current phase
  - Save conversation history
  - Record phase transitions
- [ ] Wire scoring logic (save for post-interview)

#### Amit:
- [ ] Review phase transition logic
- [ ] Test if prompts feel natural
- [ ] Validate timing feels right

**Handoff:** Atlas implements logic → Amit validates behavior

---

### Phase 4: End-to-End Testing (Day 4)

#### Atlas:
- [ ] Add transcript recording
- [ ] Add session replay save
- [ ] Implement graceful error handling
- [ ] Add connection recovery logic
- [ ] Create debugging logs

#### Amit:
- [ ] Run first full interview (45 min):
  ```bash
  python backend/agents/run_interview.py --scenario url_shortener
  ```
- [ ] Test natural conversation:
  - Can you interrupt AI?
  - Does AI wait for you to finish?
  - Do pauses feel natural?
  - Is latency acceptable (<2s)?
- [ ] Test edge cases:
  - Long silences
  - Background noise
  - Rapid back-and-forth
  - Overlapping speech
- [ ] Review transcript quality
- [ ] Check audio quality

**Handoff:** Atlas builds testing harness → Amit runs real tests

---

### Phase 5: Tuning & Refinement (Day 5)

#### Atlas:
- [ ] Make VAD sensitivity configurable
- [ ] Make silence threshold configurable
- [ ] Add per-scenario tuning (relaxed vs rapid-fire)
- [ ] Implement cost tracking
- [ ] Add session analytics

#### Amit:
- [ ] Tune VAD for your environment:
  - Adjust sensitivity (0.3–0.7 range)
  - Adjust silence threshold (400–800ms)
  - Test with/without headphones
- [ ] Try different TTS voices:
  - OpenAI: alloy, echo, fable, onyx, nova, shimmer
  - Pick most "interviewer-like"
- [ ] Validate interview feels realistic
- [ ] Test 2-3 different scenarios
- [ ] Document what works vs what needs fixing

**Handoff:** Atlas adds tunability → Amit finds optimal settings

---

## Modular Architecture Principles

### 1. Adapter Pattern (Swappable Components)
```python
# adapters/stt_adapter.py
class STTAdapter(ABC):
    @abstractmethod
    async def transcribe_stream(self, audio_stream):
        pass

class DeepgramSTT(STTAdapter):
    # Deepgram implementation

class WhisperSTT(STTAdapter):
    # Whisper implementation (future)

# Easy swap in config:
stt = DeepgramSTT()  # or WhisperSTT()
```

### 2. Configuration-Driven
```python
# config.py
class AgentConfig:
    stt_provider: str = "deepgram"  # or "whisper"
    llm_provider: str = "anthropic"  # or "openai"
    tts_provider: str = "openai"     # or "cartesia"
    
    vad_sensitivity: float = 0.5
    silence_threshold_ms: int = 600
    
# Swap providers without code changes
```

### 3. Interview Logic Decoupled
```python
# interview/phases.py
# This code never changes regardless of STT/LLM/TTS provider
class InterviewPhaseManager:
    def get_system_prompt(self, phase):
        # Phase logic independent of providers
    
    def should_transition(self, elapsed_time, conversation):
        # Transition logic independent of providers
```

---

## Success Criteria (End of Day 5)

- [ ] Full 45-min interview runs without manual intervention
- [ ] Turn-taking feels natural (no awkward pauses)
- [ ] Can interrupt AI mid-response
- [ ] AI waits appropriately after you stop speaking
- [ ] Transcript is accurate (>90%)
- [ ] Audio quality is clear
- [ ] Latency is acceptable (<2s user→AI)
- [ ] Cost per session is <$1.50
- [ ] Can swap STT/LLM/TTS in config file

---

## Risk Mitigation

### If LiveKit free tier limits hit too soon:
- **Fallback:** Self-host LiveKit server (it's open-source)
- **Timeline impact:** +1-2 days setup

### If Deepgram is too expensive:
- **Swap:** Use OpenAI Whisper API (cheaper, slightly slower)
- **Timeline impact:** 2 hours (adapter already built)

### If turn-taking feels unnatural:
- **Fix:** Tune VAD sensitivity + silence threshold
- **Timeline impact:** 1-2 hours iteration

### If Claude is too slow for real-time:
- **Temporary:** Use GPT-4o for conversation, Claude for scoring
- **Long-term:** Cache conversation context, use streaming
- **Timeline impact:** 4 hours implementation

---

## Cost Tracking (Per Session)

| Component | Cost/45min | Notes |
|-----------|-----------|-------|
| LiveKit | Free tier | Up to 5K participant-minutes/month |
| Deepgram STT | ~$0.35 | 45min × $0.0077/min |
| Claude Sonnet | ~$0.03 | ~8K tokens × $3/1M |
| OpenAI TTS | ~$0.05 | ~3K chars × $15/1M |
| **Total** | **~$0.43** | vs $5.40 with OpenAI Realtime |

---

## Immediate Next Action

**Atlas:** Start Phase 1 scaffolding (create project structure + adapters)  
**Amit:** Sign up for LiveKit Cloud + Deepgram, get API keys

Once you have API keys → paste them in `.env` → I'll write the agent code.

---

**Decision Checkpoint:** Approve this plan?
