"""Test script for GlitchTip webhook delivery to Discord.

This script sends a test alert to Discord using the configured webhook URL,
simulating a GlitchTip alert for error rate spike detection.

Usage:
    python backend/test_glitchtip_webhook.py

Requires:
    DISCORD_WEBHOOK_URL in .env file
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Optional

import requests
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_discord_webhook_url() -> Optional[str]:
    """Load Discord webhook URL from environment."""
    load_dotenv()
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        logger.error("DISCORD_WEBHOOK_URL not configured in .env file")
        return None

    if not webhook_url.startswith("https://discord.com/api/webhooks/"):
        logger.error("Invalid Discord webhook URL format")
        return None

    return webhook_url


def create_test_alert_payload() -> Dict:
    """
    Create a Discord-formatted webhook payload simulating a GlitchTip alert.

    Returns:
        Discord webhook payload with embedded alert information
    """
    return {
        "content": None,
        "embeds": [
            {
                "title": "🚨 InterviewOS Alert [TEST]",
                "description": "**ValueError: Test exception from webhook integration test**\n\n`backend/agents/interview_agent.py:line 142`",
                "color": 16711680,  # Red color for alerts
                "fields": [
                    {
                        "name": "Error Count",
                        "value": "5 errors in 5 minutes",
                        "inline": True
                    },
                    {
                        "name": "Environment",
                        "value": "production",
                        "inline": True
                    },
                    {
                        "name": "Session ID",
                        "value": "test-session-12345",
                        "inline": True
                    },
                    {
                        "name": "Phase",
                        "value": "architecture",
                        "inline": True
                    },
                    {
                        "name": "Turn Number",
                        "value": "8",
                        "inline": True
                    },
                    {
                        "name": "Issue URL",
                        "value": "[View in GlitchTip](https://glitchtip.example.com/issues/12345)",
                        "inline": True
                    }
                ],
                "footer": {
                    "text": "GlitchTip Alert"
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        ]
    }


def send_discord_webhook(webhook_url: str, payload: Dict) -> bool:
    """
    Send webhook payload to Discord.

    Args:
        webhook_url: Discord webhook URL
        payload: JSON payload to send

    Returns:
        True if successful, False otherwise
    """
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        # Discord returns 204 No Content on success
        if response.status_code in (200, 204):
            logger.info(f"✓ Webhook delivered successfully (HTTP {response.status_code})")
            return True
        else:
            logger.error(f"✗ Webhook delivery failed (HTTP {response.status_code})")
            logger.error(f"Response: {response.text}")
            return False

    except requests.exceptions.Timeout:
        logger.error("✗ Webhook delivery timed out (>10s)")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Webhook delivery failed: {e}")
        return False


def test_webhook_delivery() -> bool:
    """
    Test GlitchTip webhook delivery to Discord.

    Returns:
        True if test passed, False otherwise
    """
    print("\n" + "="*60)
    print("Testing GlitchTip Webhook Delivery to Discord")
    print("="*60 + "\n")

    # Step 1: Load webhook URL
    logger.info("Loading Discord webhook URL from .env...")
    webhook_url = load_discord_webhook_url()
    if not webhook_url:
        print("\n❌ Test failed: DISCORD_WEBHOOK_URL not configured")
        print("\nTo fix:")
        print("1. Add DISCORD_WEBHOOK_URL to your .env file")
        print("2. Get webhook URL from Discord: Channel Settings → Integrations → Webhooks")
        print("3. Format: https://discord.com/api/webhooks/{id}/{token}\n")
        return False

    logger.info(f"✓ Webhook URL loaded (ending in ...{webhook_url[-20:]})")

    # Step 2: Create test payload
    logger.info("Creating test alert payload...")
    payload = create_test_alert_payload()
    logger.info(f"✓ Payload created ({len(json.dumps(payload))} bytes)")

    # Step 3: Send webhook
    logger.info("Sending webhook to Discord...")
    success = send_discord_webhook(webhook_url, payload)

    # Step 4: Report results
    print("\n" + "="*60)
    if success:
        print("✅ Webhook test PASSED!")
        print("\nCheck your Discord alerts channel for the test message.")
        print("It should show:")
        print("  - Title: 🚨 InterviewOS Alert [TEST]")
        print("  - Error: ValueError: Test exception...")
        print("  - Fields: Error Count, Environment, Session ID, Phase, etc.")
        print("\nIf you don't see the message:")
        print("  - Verify webhook URL is correct")
        print("  - Check Discord channel permissions")
        print("  - Review webhook settings in Discord")
    else:
        print("❌ Webhook test FAILED!")
        print("\nCheck the error logs above for details.")
    print("="*60 + "\n")

    return success


def main():
    """Main entry point."""
    try:
        success = test_webhook_delivery()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()
