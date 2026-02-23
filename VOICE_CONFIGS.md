# Voice Configuration Guide

## Available Voice Presets (A/B Testing)

### 1. Nova HD (Warm & Conversational) - **RECOMMENDED**
**Usage:** `python3 -m app.realtime --voice nova_hd`

**Characteristics:**
- Warm, friendly, conversational tone
- Best for natural peer-to-peer feel
- Sounds like a real engineer talking to a colleague
- Slightly slower pace (0.95x) for clarity

**Best for:**
- Casual, collaborative interview style
- Putting candidates at ease
- Natural back-and-forth conversation

**Model:** tts-1-hd (high quality)
**Speed:** 0.95x (slightly slower than default)
**Format:** MP3 (high quality)

---

### 2. Alloy HD (Neutral & Balanced)
**Usage:** `python3 -m app.realtime --voice alloy_hd`

**Characteristics:**
- Neutral, clear, professional
- Well-balanced, not too warm or cold
- Safe default choice
- Slightly slower pace (0.95x)

**Best for:**
- Formal interview settings
- When you want clarity without personality bias
- Conservative/corporate contexts

**Model:** tts-1-hd (high quality)
**Speed:** 0.95x
**Format:** MP3

---

### 3. Onyx HD (Authoritative & Clear)
**Usage:** `python3 -m app.realtime --voice onyx_hd`

**Characteristics:**
- Deep, authoritative voice
- Technical gravitas and confidence
- More deliberate pacing (0.92x)
- Commands attention

**Best for:**
- Senior/Staff+ level interviews
- When you want technical authority
- More serious/formal tone

**Model:** tts-1-hd (high quality)
**Speed:** 0.92x (more deliberate)
**Format:** MP3

---

## A/B Testing Guide

### Test Each Voice
Run a short 5-minute mock interview with each voice:

```bash
# Test 1: Nova (warm)
python3 -m app.realtime --scenario payments --voice nova_hd

# Test 2: Alloy (neutral)
python3 -m app.realtime --scenario payments --voice alloy_hd

# Test 3: Onyx (authoritative)
python3 -m app.realtime --scenario payments --voice onyx_hd
```

### Evaluation Criteria

Rate each voice 1-10 on:
1. **Naturalness** - Does it sound like a real person?
2. **Clarity** - Can you easily understand every word?
3. **Engagement** - Does it keep your attention?
4. **Authority** - Does it feel credible/experienced?
5. **Comfort** - Would you want to talk to this voice for 45 min?

### Recommendation

**Start with Nova HD** - Most natural and conversational for peer-to-peer interviews.

Switch to:
- **Alloy HD** if Nova feels too casual
- **Onyx HD** if you want more gravitas/authority

---

## Technical Details

### Quality Improvements
All presets use:
- **Model:** `tts-1-hd` (high definition audio)
- **Speed:** 0.92-0.95x (slightly slower for naturalness)
- **Format:** MP3 (high quality, ~128kbps)

### Why Slower Speed?
- Default 1.0x can feel rushed for technical content
- 0.92-0.95x gives:
  - Better word clarity
  - More natural pauses
  - Time to absorb complex terms
  - Sounds more like a real conversation

### Why HD Model?
- Better prosody (natural intonation)
- Clearer pronunciation
- More expressive pauses
- Worth the slight latency increase

---

## Prosody Tips

The Interview Protocol already enforces:
- ✅ Short sentences (5-10 words)
- ✅ Punctuation for natural pauses
- ✅ Conversational fillers ("Hmm...", "Got it...")
- ✅ Plain English over jargon

These combine with voice config for natural-sounding speech.

---

## Future Enhancements (Phase 2)

- Add emotion/emphasis control
- Dynamic speed based on question complexity
- Custom SSML for better prosody
- Voice cloning for personalized interviewer
