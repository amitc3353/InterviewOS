"""Webhook proxy for forwarding GlitchTip alerts to Discord.

This proxy receives webhooks from GlitchTip and reformats them for Discord's
webhook API, providing rich embedded alerts with proper formatting.

Usage:
    python backend/webhook_proxy.py

Configuration:
    DISCORD_WEBHOOK_URL: Discord webhook URL (from .env)
    WEBHOOK_PROXY_PORT: Port to listen on (default: 8080)
    WEBHOOK_PROXY_HOST: Host to bind to (default: 0.0.0.0)

The proxy listens on http://localhost:8080/webhook by default.
Configure GlitchTip to send webhooks to this endpoint.
"""

import json
import logging
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
WEBHOOK_PROXY_PORT = int(os.getenv("WEBHOOK_PROXY_PORT", "8080"))
WEBHOOK_PROXY_HOST = os.getenv("WEBHOOK_PROXY_HOST", "0.0.0.0")


class GlitchTipWebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler for GlitchTip webhooks."""

    def log_message(self, format: str, *args: Any) -> None:
        """Override to use Python logging instead of stderr."""
        logger.info(f"{self.address_string()} - {format % args}")

    def do_POST(self) -> None:
        """Handle POST request from GlitchTip."""
        if self.path != "/webhook":
            self.send_error(404, "Endpoint not found. Use /webhook")
            return

        try:
            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            glitchtip_data = json.loads(body.decode("utf-8"))

            logger.info("Received webhook from GlitchTip")
            logger.debug(f"Payload: {json.dumps(glitchtip_data, indent=2)}")

            # Transform to Discord format
            discord_payload = self._transform_to_discord(glitchtip_data)

            # Send to Discord
            success = self._send_to_discord(discord_payload)

            if success:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode())
                logger.info("✓ Alert forwarded to Discord successfully")
            else:
                self.send_error(502, "Failed to forward to Discord")

        except json.JSONDecodeError:
            logger.error("Invalid JSON in request body")
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            logger.error(f"Error processing webhook: {e}", exc_info=True)
            self.send_error(500, f"Internal error: {str(e)}")

    def do_GET(self) -> None:
        """Handle GET request (health check)."""
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "healthy",
                "service": "glitchtip-webhook-proxy",
                "discord_configured": bool(DISCORD_WEBHOOK_URL)
            }).encode())
        else:
            self.send_error(404, "Not found. Use POST /webhook or GET /health")

    def _transform_to_discord(self, glitchtip_data: Dict) -> Dict:
        """
        Transform GlitchTip webhook data to Discord embed format.

        Args:
            glitchtip_data: Raw webhook data from GlitchTip

        Returns:
            Discord webhook payload with embedded alert
        """
        # Extract data from GlitchTip payload
        # Note: GlitchTip/Sentry webhook format varies by version
        # This handles common fields
        data = glitchtip_data.get("data", {})
        issue = data.get("issue", {})
        event = data.get("event", {})

        # Extract key fields with fallbacks
        title = issue.get("title") or event.get("title") or "Unknown Error"
        culprit = issue.get("culprit") or event.get("culprit") or "Unknown location"
        level = event.get("level", "error")
        environment = event.get("environment", "production")
        issue_url = issue.get("web_url") or ""

        # Extract tags
        tags = event.get("tags", {})
        session_id = tags.get("session_id", "N/A")
        phase = tags.get("phase", "N/A")
        turn_number = tags.get("turn_number", "N/A")

        # Determine color based on severity
        color_map = {
            "error": 16711680,    # Red
            "warning": 16753920,  # Orange
            "info": 65535,        # Blue
            "fatal": 8388736,     # Dark red
        }
        color = color_map.get(level, 16711680)

        # Build Discord embed
        fields = [
            {
                "name": "Environment",
                "value": environment,
                "inline": True
            },
            {
                "name": "Level",
                "value": level.upper(),
                "inline": True
            }
        ]

        # Add session context if available
        if session_id != "N/A":
            fields.append({
                "name": "Session ID",
                "value": session_id,
                "inline": True
            })

        if phase != "N/A":
            fields.append({
                "name": "Phase",
                "value": phase,
                "inline": True
            })

        if turn_number != "N/A":
            fields.append({
                "name": "Turn Number",
                "value": str(turn_number),
                "inline": True
            })

        # Add issue URL if available
        if issue_url:
            fields.append({
                "name": "Issue URL",
                "value": f"[View in GlitchTip]({issue_url})",
                "inline": False
            })

        return {
            "content": None,
            "embeds": [
                {
                    "title": f"🚨 InterviewOS Alert: {level.upper()}",
                    "description": f"**{title}**\n\n`{culprit}`",
                    "color": color,
                    "fields": fields,
                    "footer": {
                        "text": "GlitchTip Alert"
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
            ]
        }

    def _send_to_discord(self, payload: Dict) -> bool:
        """
        Send formatted payload to Discord webhook.

        Args:
            payload: Discord webhook payload

        Returns:
            True if successful, False otherwise
        """
        if not DISCORD_WEBHOOK_URL:
            logger.error("DISCORD_WEBHOOK_URL not configured")
            return False

        try:
            response = requests.post(
                DISCORD_WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            if response.status_code in (200, 204):
                return True
            else:
                logger.error(f"Discord webhook failed: HTTP {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send to Discord: {e}")
            return False


def validate_configuration() -> bool:
    """
    Validate webhook proxy configuration.

    Returns:
        True if configuration is valid, False otherwise
    """
    if not DISCORD_WEBHOOK_URL:
        logger.error("DISCORD_WEBHOOK_URL not configured in .env")
        logger.error("Add your Discord webhook URL to .env file")
        return False

    if not DISCORD_WEBHOOK_URL.startswith("https://discord.com/api/webhooks/"):
        logger.error("Invalid DISCORD_WEBHOOK_URL format")
        return False

    logger.info(f"✓ Discord webhook configured (ending in ...{DISCORD_WEBHOOK_URL[-20:]})")
    return True


def run_server() -> None:
    """Start the webhook proxy server."""
    print("\n" + "="*60)
    print("GlitchTip Webhook Proxy for Discord")
    print("="*60 + "\n")

    # Validate configuration
    if not validate_configuration():
        print("\n❌ Configuration validation failed")
        print("\nTo fix:")
        print("1. Add DISCORD_WEBHOOK_URL to your .env file")
        print("2. Get webhook URL from Discord: Channel Settings → Integrations → Webhooks")
        print("3. Format: https://discord.com/api/webhooks/{id}/{token}\n")
        exit(1)

    # Start server
    server_address = (WEBHOOK_PROXY_HOST, WEBHOOK_PROXY_PORT)
    httpd = HTTPServer(server_address, GlitchTipWebhookHandler)

    logger.info(f"✓ Webhook proxy listening on {WEBHOOK_PROXY_HOST}:{WEBHOOK_PROXY_PORT}")
    logger.info(f"✓ Webhook endpoint: http://localhost:{WEBHOOK_PROXY_PORT}/webhook")
    logger.info(f"✓ Health check: http://localhost:{WEBHOOK_PROXY_PORT}/health")
    print("\nProxy is running. Press Ctrl+C to stop.\n")
    print("Configure GlitchTip to send webhooks to:")
    print(f"  → http://YOUR_SERVER:{WEBHOOK_PROXY_PORT}/webhook\n")
    print("="*60 + "\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down webhook proxy...")
        httpd.shutdown()
        logger.info("Webhook proxy stopped")


def main():
    """Main entry point."""
    try:
        run_server()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()
