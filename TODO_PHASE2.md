# Phase 2 TODOs

## Critical Updates

### 1. Upgrade Deepgram SDK to v5 (Option B)
**Current state:** Pinned to v3.x for Phase 1 speed
**Why upgrade:**
- v5 is latest stable
- Better API design
- Improved performance

**What needs changing:**
- `app/adapters/stt_adapter.py` - Rewrite for v5 API
  - `LiveTranscriptionEvents` → `ListenV1VadEvents`
  - Connection model changed
  - Event handlers refactored

**Reference:**
- Deepgram v5 migration guide: https://developers.deepgram.com/docs/migration-guide
- PR discussion: See PR #7 comments (2026-02-21)

**Timing:** Do this BEFORE implementing DailyTransport, so you have clean v5 integration.

---

## Phase 2 Checklist

- [ ] Upgrade deepgram-sdk to v5.x
- [ ] Rewrite `stt_adapter.py` for v5 API
- [ ] Test streaming STT with v5
- [ ] Implement `DailyTransport`
- [ ] Add VAD (Voice Activity Detection)
- [ ] Implement echo cancellation
- [ ] Add web UI
- [ ] Session persistence
- [ ] User accounts (if needed)

---

## Notes

Phase 1 focus = interview quality validation (5+ sessions)
Phase 2 focus = production-ready web platform
