# Real-Time Interview Feature — Technical Plan

**Goal:** Natural voice conversation without push-to-talk (spacebar)  
**Current state:** Push-to-talk blocking efficient testing  
**Target:** Conversational flow with automatic turn-taking

---

## Core Problem: Turn-Taking in Voice Conversations

Real-time voice requires solving:
1. **When did the user start speaking?** (Voice Activity Detection)
2. **When did the user stop speaking?** (End-of-speech detection)
3. **When should AI respond?** (Turn-taking logic)
4. **When can user interrupt AI?** (Interruption handling)
5. **How to minimize latency?** (Streaming architecture)

---

## Architecture Options

### Option 1: VAD + Streaming STT + Turn-Taking Logic ⭐ RECOMMENDED
**Stack:**
- Frontend: WebRTC audio capture → VAD (browser-native or Silero VAD)
- STT: Deepgram streaming API
- Turn detection: Silence threshold (500-800ms of silence = end of turn)
- Backend: WebSocket connection for bidirectional streaming
- TTS: OpenAI streaming API

**Pros:**
- Full control over turn-taking logic
- Can tune interruption behavior
- Lower cost (only transcribe when speaking)
- Works with any LLM provider

**Cons:**
- More complex to build
- Need to handle edge cases (false triggers, background noise)
- Requires tuning VAD sensitivity

**Latency:**
- VAD detection: <50ms
- STT streaming: 200-400ms
- LLM response: 800-1500ms
- TTS streaming: 300-500ms
- **Total: ~1.5-2.5s** (acceptable for interviews)

---

### Option 2: OpenAI Realtime API
**Stack:**
- Use OpenAI's Realtime API (GPT-4 Turbo with voice)
- Single WebSocket handles VAD + STT + LLM + TTS
- Automatic turn-taking built-in

**Pros:**
- Fastest to implement (2-3 days)
- Automatic VAD + turn-taking
- Very low latency (~1s end-to-end)
- Handles interruptions natively

**Cons:**
- Locked to OpenAI models (no Claude)
- Higher cost per session
- Less control over interviewer behavior
- API still in beta

**Cost comparison:**
- Realtime API: ~$0.06/min audio + $0.06/min output = **$0.12/min**
- Option 1: Deepgram $0.0043/min + Claude $0.003/1K tokens + OpenAI TTS $0.015/1K chars = **~$0.03-0.05/min**

---

### Option 3: Daily.co + Custom Logic
**Stack:**
- Daily.co handles WebRTC infrastructure
- Custom VAD + STT pipeline
- Similar to Option 1 but with managed WebRTC

**Pros:**
- Production-grade WebRTC infrastructure
- Good for scaling later
- Daily.co has built-in noise cancellation

**Cons:**
- Additional dependency
- More complex setup
- Overkill for MVP

---

## Recommended Approach: Hybrid Phased Plan

### Phase 1: OpenAI Realtime API (2-3 days) 🎯 START HERE
**Why:**
- Unblocks testing immediately
- Validates conversation flow UX
- Proves core interview experience works
- Can always swap backend later

**Build:**
1. Frontend: Capture audio via WebRTC
2. Connect to OpenAI Realtime API WebSocket
3. Implement basic turn-taking (function calling to control flow)
4. Add "interviewer interrupt" logic via function calls
5. Display live transcript
6. Save session recording + transcript

**Trade-off:**
- Accept OpenAI lock-in for now
- Optimize for learning speed over cost
- Can migrate to Option 1 post-validation

---

### Phase 2: Custom VAD + Streaming (Post-MVP)
**When:** After validating interview experience works

**Build:**
1. Implement browser-based VAD (Silero VAD ONNX model)
2. Stream audio chunks to Deepgram
3. Build turn-taking state machine:
   - LISTENING (user speaking)
   - PROCESSING (STT → LLM)
   - SPEAKING (AI responding)
   - IDLE (waiting for next turn)
4. Add configurable silence threshold
5. Migrate to Claude for interviewer logic

**Benefits:**
- Lower cost per session
- Full control over Claude prompting
- Better interviewer personality tuning
- More flexible interruption handling

---

## Technical Implementation — Phase 1 (OpenAI Realtime)

### 1. Frontend Setup
```javascript
// Real-time audio capture
const mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });

// Connect to OpenAI Realtime API
const ws = new WebSocket('wss://api.openai.com/v1/realtime');

// Send audio chunks
const audioContext = new AudioContext();
const source = audioContext.createMediaStreamSource(mediaStream);
const processor = audioContext.createScriptProcessor(4096, 1, 1);

processor.onaudioprocess = (e) => {
  const audioData = e.inputBuffer.getChannelData(0);
  ws.send(JSON.stringify({
    type: 'input_audio_buffer.append',
    audio: arrayBufferToBase64(audioData)
  }));
};
```

### 2. Session Configuration
```javascript
{
  modalities: ["text", "audio"],
  instructions: INTERVIEWER_SYSTEM_PROMPT,
  voice: "alloy", // or "echo" for deeper voice
  input_audio_format: "pcm16",
  output_audio_format: "pcm16",
  turn_detection: {
    type: "server_vad",
    threshold: 0.5,
    prefix_padding_ms: 300,
    silence_duration_ms: 600
  }
}
```

### 3. Turn-Taking Logic
```javascript
// Listen for conversation events
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch(data.type) {
    case 'conversation.item.created':
      // User or AI started speaking
      break;
    case 'response.audio.delta':
      // Stream AI audio back to user
      playAudioChunk(data.delta);
      break;
    case 'response.done':
      // AI finished speaking
      break;
    case 'input_audio_buffer.speech_started':
      // User started speaking - cancel AI if needed
      if (aiSpeaking) {
        ws.send({ type: 'response.cancel' });
      }
      break;
  }
};
```

### 4. Interruption Handling
- When user starts speaking while AI is responding → cancel AI audio
- When AI needs to interrupt user (for probing) → use function call trigger
- Track conversation state for scoring later

---

## Technical Implementation — Phase 2 (Custom VAD)

### 1. VAD Setup (Browser)
```javascript
// Load Silero VAD model (ONNX)
const vadModel = await ort.InferenceSession.create('silero_vad.onnx');

function detectVoiceActivity(audioChunk) {
  const tensor = new ort.Tensor('float32', audioChunk, [1, audioChunk.length]);
  const output = await vadModel.run({ input: tensor });
  return output.output.data[0] > 0.5; // Voice detected
}
```

### 2. Streaming STT (Deepgram)
```javascript
const deepgram = new Deepgram(API_KEY);
const dgConnection = deepgram.transcription.live({
  model: 'nova-2',
  language: 'en',
  punctuate: true,
  interim_results: true,
  endpointing: 600 // ms silence = end of utterance
});

dgConnection.on('transcriptReceived', (transcript) => {
  if (transcript.is_final) {
    sendToLLM(transcript.channel.alternatives[0].transcript);
  }
});
```

### 3. Turn-Taking State Machine
```javascript
const states = {
  IDLE: 'idle',
  LISTENING: 'listening',
  PROCESSING: 'processing',
  SPEAKING: 'speaking'
};

let currentState = states.IDLE;
let silenceTimer = null;

function onVADResult(voiceDetected) {
  if (voiceDetected) {
    clearTimeout(silenceTimer);
    if (currentState === states.IDLE) {
      currentState = states.LISTENING;
      startSTT();
    }
  } else {
    // Start silence timer
    silenceTimer = setTimeout(() => {
      if (currentState === states.LISTENING) {
        currentState = states.PROCESSING;
        endSTT();
        processUserInput();
      }
    }, 600); // 600ms silence = end of turn
  }
}
```

### 4. LLM Integration (Claude)
```javascript
async function processUserInput(transcript) {
  const response = await anthropic.messages.create({
    model: 'claude-sonnet-4',
    messages: conversationHistory,
    system: INTERVIEWER_PROMPT,
    stream: true
  });

  let fullResponse = '';
  for await (const chunk of response) {
    fullResponse += chunk.delta?.text || '';
  }

  // Convert to speech
  currentState = states.SPEAKING;
  await streamTTS(fullResponse);
  currentState = states.IDLE;
}
```

### 5. Streaming TTS
```javascript
async function streamTTS(text) {
  const response = await fetch('https://api.openai.com/v1/audio/speech', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${OPENAI_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model: 'tts-1',
      voice: 'onyx',
      input: text,
      response_format: 'pcm'
    })
  });

  const audioStream = response.body;
  const reader = audioStream.getReader();
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    playAudioChunk(value);
  }
}
```

---

## Key Implementation Details

### 1. Silence Detection Tuning
- **Too short (200-300ms):** False triggers, cuts off user mid-thought
- **Too long (1000ms+):** Feels unresponsive, awkward pauses
- **Sweet spot: 500-700ms** for interview simulation
- Make configurable per scenario (relaxed vs rapid-fire)

### 2. Interruption Strategy
**User interrupts AI:**
- Cancel TTS immediately
- Reset state to LISTENING
- Save partial AI response for context

**AI interrupts user (for probing):**
- Only during LISTENING state
- Use function call: `interrupt_candidate({ reason: "clarification" })`
- Play AI audio over user (mix, don't mute)

### 3. Audio Quality Requirements
- Sample rate: 16kHz minimum (24kHz ideal)
- Format: PCM16 or Opus
- Noise suppression: Enable browser-native or WebRTC processing
- Echo cancellation: Critical for headphone-free use

### 4. Latency Optimization
**STT latency:**
- Use interim results for faster perceived response
- Buffer last 200ms of audio before silence to avoid cutting words

**LLM latency:**
- Start TTS on first 2-3 tokens (don't wait for full response)
- Use streaming everywhere possible

**Network latency:**
- Use WebSocket (not HTTP polling)
- Deploy backend in user's region

**Target latency budget:**
- User stops speaking → AI starts speaking: <2s
- User interrupts AI → AI stops: <200ms

---

## Testing Strategy

### Phase 1 Testing (OpenAI Realtime)
1. Basic conversation flow (no interruptions)
2. User interrupts AI mid-response
3. AI probes user with clarifying questions
4. Background noise handling
5. Multiple rapid questions from user
6. Long pauses (10s+) - should wait patiently
7. Session recording quality

### Phase 2 Testing (Custom VAD)
1. VAD sensitivity in quiet environments
2. VAD with background noise (music, typing, A/C)
3. False positive rate (breathing, "um", coughs)
4. Different microphone qualities
5. Mobile vs desktop performance
6. Network lag simulation
7. Multi-turn conversation coherence

---

## Cost Analysis

### Per 45-minute interview session:

**Option 1 (Custom VAD + Claude):**
- Deepgram STT: 45 min × $0.0043/min = $0.19
- Claude Sonnet: ~8K tokens × $3/1M = $0.024
- OpenAI TTS: ~3K chars × $15/1M = $0.045
- **Total: ~$0.26/session**

**Option 2 (OpenAI Realtime):**
- Audio I/O: 45 min × $0.12/min = $5.40
- **Total: $5.40/session**

**Cost difference: 20x cheaper with custom pipeline**

**But:** OpenAI Realtime unblocks testing NOW (worth $5 vs weeks of dev time).

---

## Migration Path

### Week 1-2: OpenAI Realtime MVP
- Build end-to-end voice interview
- Test with 5-10 real users
- Validate conversation flow UX
- Gather latency/quality feedback

### Week 3-4: Custom Pipeline (if validated)
- Implement VAD + Deepgram + Claude
- A/B test against OpenAI version
- Migrate if quality is comparable

### Week 5+: Optimization
- Fine-tune VAD thresholds per scenario
- Add interruption personality tuning
- Implement dynamic silence detection
- Add conversation analytics

---

## Edge Cases to Handle

1. **User doesn't speak for 30s:** AI should prompt ("Are you still there?")
2. **Multiple false starts:** User says "um, uh, so..." → don't respond yet
3. **Overlapping speech:** Both speaking simultaneously → AI yields
4. **Network disconnection:** Save state, allow resume
5. **User mutes mid-conversation:** Detect and pause AI
6. **Background conversation:** VAD should ignore non-primary speaker
7. **Long monologues (5min+):** AI should acknowledge periodically

---

## Success Metrics

### Technical metrics:
- User-to-AI latency: <2s (p95)
- AI-stop latency on interrupt: <200ms (p95)
- False VAD triggers: <5% of sessions
- Session completion rate: >90%

### UX metrics:
- Feels natural (user survey)
- No frustration with turn-taking
- Comfortable interrupting AI
- Would prefer over push-to-talk: >80%

---

## Next Actions

### Immediate (Week 1):
1. Set up OpenAI Realtime API access
2. Build minimal frontend (mic → WebSocket → speaker)
3. Implement basic interviewer prompt in session config
4. Add transcript display
5. Test one full interview end-to-end
6. Record session for review

### Week 2:
7. Add interruption handling (user can interrupt)
8. Implement AI probing (interviewer interrupts candidate)
9. Add session recording save
10. Test with 3-5 real practice sessions

### Week 3+ (if validated):
11. Start custom VAD + Deepgram pipeline in parallel
12. Build turn-taking state machine
13. Migrate one scenario to custom pipeline
14. A/B test quality vs OpenAI Realtime

---

## Recommendation

**Start with OpenAI Realtime API.**

Rationale:
- Unblocks testing in 2-3 days vs 2-3 weeks
- Higher cost acceptable during validation
- Can always optimize later
- Learning speed > cost optimization right now
- Real feedback on interview UX is the blocker

Build custom pipeline only after proving the interview experience works.

---

**DECISION NEEDED:**
- Go with OpenAI Realtime MVP?
- Or build custom VAD pipeline from day 1?
