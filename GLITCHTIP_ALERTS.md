# GlitchTip Alert Configuration Guide

## Overview

This guide explains how to configure GlitchTip alert rules to send notifications to Discord via webhook when error rate spikes are detected. The alerting system monitors for error patterns like ">5 errors in 5 minutes" and sends formatted notifications to your Discord alerts channel.

## Prerequisites

- GlitchTip instance running with InterviewOS configured (see SENTRY_INTEGRATION.md)
- Discord server with a channel for alerts (e.g., `#interview-alerts`)
- Admin access to both GlitchTip and Discord

## Setup Steps

### 1. Create Discord Webhook

1. **Navigate to Discord Channel Settings**:
   - Open Discord and go to your alerts channel (e.g., `#interview-alerts`)
   - Click the gear icon (Edit Channel) → Integrations → Webhooks
   - Click "New Webhook" or "Create Webhook"

2. **Configure Webhook**:
   - Name: `GlitchTip Alerts` (or `InterviewOS Alerts`)
   - Avatar: Optional (upload a custom icon)
   - Channel: Confirm it's pointing to your alerts channel
   - Copy the Webhook URL (you'll need this for GlitchTip)

3. **Save the Webhook URL**:
   - Format: `https://discord.com/api/webhooks/{webhook.id}/{webhook.token}`
   - Keep this URL secure - anyone with it can post to your channel

### 2. Configure GlitchTip Alert Rule

1. **Navigate to Alert Rules**:
   - Log into your GlitchTip instance
   - Go to **Settings** → **Alerts** → **Rules**
   - Click **Create Alert Rule**

2. **Configure Alert Conditions**:
   - **Name**: `High Error Rate - InterviewOS`
   - **Environment**: `production` (or match your SENTRY_ENVIRONMENT)
   - **Alert Trigger**: `An event is captured`
   - **Conditions**:
     - `The issue has happened at least 5 times in 5 minutes`
     - Or: `The issue is seen by more than 5 users in 5 minutes`

3. **Add Discord Webhook Action**:
   - **Action**: Click **Add Action** → **Send a notification via webhook**
   - **Webhook URL**: Paste your Discord webhook URL from Step 1
   - **Method**: `POST`
   - **Payload Template**: Use the Discord-compatible JSON format below

### 3. Discord Webhook Payload Template

GlitchTip sends webhook data, but Discord requires a specific format. You have two options:

#### Option A: Use Webhook Proxy (Recommended)

Run the InterviewOS webhook proxy that formats GlitchTip alerts for Discord:

```bash
# Add Discord webhook URL to .env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_TOKEN

# Run the webhook proxy (stays running)
python backend/webhook_proxy.py
```

Then configure GlitchTip to send webhooks to: `http://your-server:8080/webhook`

#### Option B: Direct Discord Webhook (Manual Format)

If using direct Discord webhook in GlitchTip, configure the payload as:

```json
{
  "content": null,
  "embeds": [
    {
      "title": "🚨 InterviewOS Alert",
      "description": "**{issue.title}**\n\n{issue.culprit}",
      "color": 16711680,
      "fields": [
        {
          "name": "Error Count",
          "value": "{event.count} errors in 5 minutes",
          "inline": true
        },
        {
          "name": "Environment",
          "value": "{event.environment}",
          "inline": true
        },
        {
          "name": "Session ID",
          "value": "{event.tags.session_id}",
          "inline": true
        },
        {
          "name": "Phase",
          "value": "{event.tags.phase}",
          "inline": true
        }
      ],
      "footer": {
        "text": "GlitchTip Alert"
      },
      "timestamp": "{event.datetime}"
    }
  ]
}
```

**Note**: GlitchTip variable syntax may vary by version. Check your GlitchTip documentation for exact template variables.

### 4. Configure Alert Frequency

To avoid alert spam:

1. **Rate Limiting**:
   - In GlitchTip Alert Rule settings
   - Set **Rate Limit**: `Once every 10 minutes` (or appropriate interval)

2. **Quiet Hours** (Optional):
   - Configure in Alert Rule settings
   - Mute alerts during off-hours if needed

### 5. Additional Alert Rules

Consider creating additional rules for different severity levels:

#### Critical Errors (Immediate Notification)
- Trigger: `>10 errors in 2 minutes`
- Action: Discord webhook + email
- Rate limit: Once every 5 minutes

#### Medium Priority (Batched)
- Trigger: `>5 errors in 10 minutes`
- Action: Discord webhook only
- Rate limit: Once every 30 minutes

#### Low Priority (Daily Summary)
- Trigger: `>20 errors in 24 hours`
- Action: Email summary
- Rate limit: Once daily

## Testing the Webhook

### Automated Test Script

Run the test script to verify webhook delivery:

```bash
python backend/test_glitchtip_webhook.py
```

This will:
1. Load your Discord webhook URL from `.env`
2. Send a test alert with mock GlitchTip data
3. Verify delivery and response
4. Display the result

**Expected Output**:
```
Testing GlitchTip webhook delivery to Discord...
✓ Webhook test successful! Check your Discord channel for the test alert.
```

**In Discord**, you should see:
```
🚨 InterviewOS Alert [TEST]

ValueError: Test exception from webhook integration test

Error Count: 5 errors in 5 minutes
Environment: production
Session ID: test-session-12345
Phase: architecture

GlitchTip Alert • Just now
```

### Manual Test via GlitchTip

1. **Trigger Test Alert**:
   - Go to GlitchTip → Settings → Alerts → Rules
   - Find your rule, click **"..."** → **Send Test Alert**
   - Or: Run `python backend/test_sentry.py` to create a real error

2. **Verify in Discord**:
   - Check your alerts channel
   - Verify formatting is correct
   - Confirm all fields are populated

3. **Check GlitchTip Logs**:
   - GlitchTip → Settings → Alerts → Activity
   - Look for webhook delivery logs
   - Check for any errors or failures

## Monitoring and Maintenance

### Alert Health Checks

Monitor webhook health:

```bash
# Check recent webhook deliveries in GlitchTip
# Settings → Alerts → Activity
```

Look for:
- ✓ Successful deliveries (HTTP 200/204)
- ✗ Failed deliveries (HTTP 4xx/5xx)
- ⏱ Delivery latency (should be <1s)

### Common Issues

#### Webhook Not Delivering

**Symptoms**: No Discord messages appear after errors

**Troubleshooting**:
1. Verify Discord webhook URL in `.env` or GlitchTip is correct
2. Check GlitchTip logs for webhook errors
3. Test webhook URL directly: `curl -X POST "YOUR_WEBHOOK_URL" -H "Content-Type: application/json" -d '{"content":"Test"}'`
4. Ensure GlitchTip server can reach Discord (check firewall/network)

#### Too Many Alerts

**Symptoms**: Constant Discord notifications

**Solutions**:
1. Increase rate limit in alert rule (e.g., once every 15 minutes)
2. Adjust threshold (e.g., >10 errors instead of >5)
3. Add filters to alert rule (e.g., only specific error types)
4. Check for error loops in code that need fixing

#### Missing Context Data

**Symptoms**: Discord alert shows "null" or empty fields

**Solutions**:
1. Verify Sentry context is set (see SENTRY_INTEGRATION.md)
2. Check GlitchTip template variables are correct
3. Update payload template to match your GlitchTip version
4. Test with `python backend/test_sentry.py` to send full context

## Environment Configuration

Add to your `.env` file:

```bash
# Discord Webhook for Alerts (optional - only if using webhook proxy)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_TOKEN

# Alert Configuration (optional)
ALERT_RATE_LIMIT_MINUTES=10      # Minimum time between alerts for same issue
ALERT_ERROR_THRESHOLD=5          # Number of errors to trigger alert
ALERT_TIME_WINDOW_MINUTES=5      # Time window for counting errors
```

## Security Considerations

1. **Webhook URL Protection**:
   - Never commit webhook URLs to git
   - Use environment variables or secrets manager
   - Rotate webhook URLs if exposed

2. **Sensitive Data**:
   - Avoid including PII in error messages
   - Configure GlitchTip data scrubbing for sensitive fields
   - Review alert payload before enabling

3. **Discord Permissions**:
   - Limit webhook to alerts channel only
   - Use read-only permissions for non-admin users
   - Set up role-based access for @mentions

## Next Steps

- Set up additional alert rules for different error types
- Configure email notifications as backup
- Set up PagerDuty/Opsgenie for critical alerts
- Create runbooks for common alert scenarios
- Monitor alert fatigue and adjust thresholds

## References

- [GlitchTip Alerts Documentation](https://glitchtip.com/documentation/alerts)
- [Discord Webhooks Guide](https://discord.com/developers/docs/resources/webhook)
- [Sentry Integration Guide](./SENTRY_INTEGRATION.md)
- [InterviewOS Architecture](./ARCHITECTURE.md)
