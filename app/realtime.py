"""Real-time voice mode entry point."""

import sys
import argparse
from app.config import Config
from app.engine import InterviewEngine
from app.transport import LocalMicTransport


def main():
    """Real-time voice interview mode."""
    parser = argparse.ArgumentParser(description="InterviewOS - Real-time Voice Mode")

    parser.add_argument(
        "--scenario",
        default="payments",
        choices=[
            "payments",
            "social_feed",
            "e_commerce",
            "ride_sharing",
            "video_streaming",
        ],
        help="Interview scenario",
    )

    args = parser.parse_args()

    # Validate environment
    try:
        Config.validate()
        Config.ensure_dirs()
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    # Create engine and transport
    engine = InterviewEngine()
    transport = LocalMicTransport(scenario=args.scenario)

    # Run
    try:
        transport.run(engine)
        return 0
    except KeyboardInterrupt:
        print("\n\n👋 Interview ended.")
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
