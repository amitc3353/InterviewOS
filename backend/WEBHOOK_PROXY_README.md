# GlitchTip Webhook Proxy - Quick Start

## Overview

The webhook proxy reformats GlitchTip alerts for Discord's webhook API, providing rich embedded notifications with proper formatting and interview context.

## Quick Start

### 1. Configure Discord Webhook

```bash
# Add to .env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
```

Get webhook URL from Discord:
- Channel Settings → Integrations → Webhooks → New Webhook

### 2. Test Webhook Delivery

```bash
# Send test alert to Discord
python backend/test_glitchtip_webhook.py
```

Expected output:
```
✅ Webhook test PASSED!
Check your Discord alerts channel for the test message.
```

### 3. Run Webhook Proxy (Optional)

For automatic formatting of GlitchTip alerts:

```bash
# Start proxy server
python backend/webhook_proxy.py

# In another terminal, configure GlitchTip to send to:
# http://YOUR_SERVER:8080/webhook
```

## Files

- `test_glitchtip_webhook.py` - Test script for webhook delivery
- `webhook_proxy.py` - HTTP server for reformatting GlitchTip alerts
- `tests/test_glitchtip_webhook.py` - Unit tests for webhook functionality

## Documentation

See **[GLITCHTIP_ALERTS.md](../GLITCHTIP_ALERTS.md)** for:
- Complete setup guide
- GlitchTip alert rule configuration
- Error rate thresholds
- Troubleshooting

## Testing

```bash
# Run tests
pytest backend/tests/test_glitchtip_webhook.py -v

# Test webhook delivery
python backend/test_glitchtip_webhook.py

# Health check (when proxy is running)
curl http://localhost:8080/health
```

## Configuration

Environment variables (in `.env`):

```bash
# Required
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Optional (webhook proxy)
WEBHOOK_PROXY_PORT=8080
WEBHOOK_PROXY_HOST=0.0.0.0
```
