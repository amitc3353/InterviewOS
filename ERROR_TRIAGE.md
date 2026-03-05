# Error Triage Workflow

## Overview

This document defines the error triage process for InterviewOS. It covers how to classify, prioritize, and resolve errors detected by GlitchTip, from initial alert to resolution.

## Alert Severity Levels

| Severity | Response Time | Example | Action |
|----------|--------------|---------|--------|
| **Critical** | < 15 min | 10+ errors in 2 min, fatal errors, service crash | Investigate immediately, escalate if not resolved in 30 min |
| **High** | < 1 hour | STT/TTS/LLM pipeline failures, 5+ errors in 5 min | Investigate during work hours, apply hotfix if needed |
| **Medium** | < 4 hours | Sustained error pattern (10+ in 30 min) | Investigate during current work session |
| **Low** | Next business day | 50+ errors in 24 hours, non-blocking issues | Review in daily triage, batch with similar issues |
| **Info** | Backlog | Warnings, deprecation notices | Track in backlog, address during maintenance |

## Triage Process

### Step 1: Acknowledge the Alert

When you receive a Discord or email alert:

1. **Check GlitchTip** — Open the linked issue in GlitchTip dashboard
2. **Read the context** — Note the session ID, phase, turn number, and error message
3. **Check frequency** — Is this a one-off or recurring pattern?
4. **Acknowledge** — React to the Discord alert or reply to confirm you are looking at it

### Step 2: Classify the Error

Determine the error category:

| Category | Description | Common Causes |
|----------|-------------|---------------|
| **STT Failure** | Speech-to-text pipeline errors | Deepgram API timeout, invalid audio, network issue |
| **LLM Failure** | Claude API errors | Rate limit, timeout, malformed prompt, API outage |
| **TTS Failure** | Text-to-speech errors | Cartesia/OpenAI API failure, invalid text input |
| **Session State** | Interview state corruption | Phase transition bug, missing constraints, race condition |
| **Infrastructure** | System-level failures | LiveKit disconnection, memory exhaustion, network partition |
| **Configuration** | Misconfigured settings | Missing API keys, invalid environment variables |

### Step 3: Assess Impact

Answer these questions:

1. **How many sessions are affected?** — Check session_id tags in GlitchTip
2. **Is the error blocking?** — Can the interview continue despite the error?
3. **Is the error spreading?** — Is the error rate increasing or stable?
4. **Is there a workaround?** — Can affected users retry or use an alternative?

### Step 4: Investigate Root Cause

Use these tools to investigate:

```bash
# Check structured logs for the session
grep "session_id" backend/logs/ | grep "ERROR"

# Check GlitchTip for the specific issue
# Navigate to: GlitchTip → Issues → [Issue ID]
# Review: Stack trace, tags, context, frequency

# Check recent deployments
git log --oneline -10

# Run the test suite to check for regressions
pytest backend/tests/ -v
```

**Key context to gather from GlitchTip:**

- **Stack trace** — Where exactly did the error occur?
- **Tags** — session_id, phase, turn_number, event_type
- **Context** — interview_session data (elapsed time, constraints count)
- **Frequency** — First seen, last seen, total occurrences
- **Affected environments** — Production only? Staging too?

### Step 5: Resolve

Based on the severity and category:

#### Quick Fix (Critical/High)
1. Identify the failing code path
2. Write a targeted fix
3. Add a regression test
4. Deploy to staging, verify, then production
5. Monitor GlitchTip for 30 minutes after deploy

#### Standard Fix (Medium/Low)
1. Create a GitHub issue with the GlitchTip link
2. Reproduce locally using the session context
3. Write fix with tests
4. Submit PR for review
5. Deploy in next release cycle

### Step 6: Post-Incident

After resolving critical or high-severity issues:

1. **Update the GlitchTip issue** — Mark as resolved
2. **Verify resolution** — Confirm no new occurrences for 24 hours
3. **Document learnings** — Add notes to the issue about root cause and fix
4. **Adjust alerts if needed** — Tune thresholds if the alert was too noisy or too quiet

## Dashboard Panels Reference

The InterviewOS monitoring dashboard (`backend/monitoring/dashboard.py`) provides these panels:

| Panel | What It Shows | When to Check |
|-------|--------------|---------------|
| **Total Errors (24h)** | Error count over last 24 hours | Daily triage |
| **Error Rate (per min)** | Real-time error rate trend | During incidents |
| **Errors by Phase** | Which interview phases have most errors | Weekly review |
| **Errors by Component** | STT vs LLM vs TTS error distribution | When pipeline issues occur |
| **Top Unresolved Issues** | Most frequent open errors | Daily triage |
| **Session Health** | % of clean sessions | Weekly review |
| **Critical Errors** | Fatal/critical error count | During incidents |
| **LLM Response Time** | Claude API latency | Performance monitoring |

## Alert Rules Reference

Configured in `backend/monitoring/alert_rules.py`:

| Rule | Trigger | Notification | Rate Limit |
|------|---------|-------------|------------|
| Critical Error Spike | 10+ errors in 2 min | Discord + Email | 5 min |
| High Error Rate | 5+ errors in 5 min | Discord | 10 min |
| Sustained Errors | 10+ errors in 30 min | Discord | 30 min |
| Daily Error Threshold | 50+ errors in 24h | Email | 24h |
| Fatal Error | 1 fatal error | Discord + Email | 5 min |
| STT Pipeline Errors | 3+ STT errors in 5 min | Discord | 15 min |
| TTS Pipeline Errors | 3+ TTS errors in 5 min | Discord | 15 min |
| LLM API Errors | 3+ LLM errors in 5 min | Discord | 10 min |

## Notification Channels

Configured in `backend/monitoring/notification_channels.py`:

| Channel | Type | Receives | Purpose |
|---------|------|----------|---------|
| Discord - Critical | Discord Webhook | Critical+ | Immediate team notification |
| Discord - High Priority | Discord Webhook | High+ | Pipeline failure alerts |
| Email - Daily Summary | Email | Low+ | Daily error digest |
| Email - Critical Backup | Email | Critical+ | Backup for missed Discord alerts |

## Common Error Patterns and Fixes

### Pattern: Deepgram STT Timeout
- **Symptoms**: `stt_error` events, empty transcripts
- **Cause**: Network latency or Deepgram API degradation
- **Fix**: Check Deepgram status page. If systemic, increase STT timeout in config. If transient, the retry logic should handle it.

### Pattern: Claude API Rate Limit
- **Symptoms**: `llm_error` events with 429 status code
- **Cause**: Too many concurrent sessions or burst requests
- **Fix**: Check concurrent session count. Reduce `traces_sample_rate` if performance monitoring is causing excess API calls. Contact Anthropic for rate limit increase if needed.

### Pattern: Cartesia TTS Failure
- **Symptoms**: `tts_error` events, silent interviewer responses
- **Cause**: Invalid SSML, pronunciation dict issues, or API outage
- **Fix**: Check TTS pronunciation configuration. Verify Cartesia API key and voice ID. Check `tts_pronunciations.py` for recent changes.

### Pattern: Phase Transition Error
- **Symptoms**: `session_state` errors during phase changes
- **Cause**: Race condition in phase advancement or invalid state
- **Fix**: Review `phase_manager.py` for monotonic enforcement. Check conversation history for unexpected phase jumps.

### Pattern: LiveKit Connection Drop
- **Symptoms**: Session ends abruptly, reconnection errors
- **Cause**: Network instability, LiveKit server issue, or client disconnect
- **Fix**: Check LiveKit dashboard for room status. Review VAD settings — aggressive endpointing can cause premature disconnects.

## Daily Triage Checklist

Run this checklist each morning:

- [ ] Check GlitchTip dashboard for overnight errors
- [ ] Review "Top Unresolved Issues" panel
- [ ] Check "Session Health" percentage (target: >95%)
- [ ] Scan Discord alerts channel for any unacknowledged alerts
- [ ] Review error trends — is the error rate increasing or decreasing?
- [ ] Check for any new error types not seen before
- [ ] Prioritize and assign issues for the day

## References

- [Sentry Integration Guide](./SENTRY_INTEGRATION.md)
- [GlitchTip Alert Configuration](./GLITCHTIP_ALERTS.md)
- [Structured Logging Guide](./STRUCTURED_LOGGING.md)
- [Dashboard Configuration](./backend/monitoring/dashboard.py)
- [Alert Rules](./backend/monitoring/alert_rules.py)
- [Notification Channels](./backend/monitoring/notification_channels.py)
