"""Command-line interface for InterviewOS."""

import sys
from app.config import Config

def main():
    """Main CLI entry point."""
    try:
        # Validate environment
        Config.validate()
        Config.ensure_dirs()
        
        print("✅ InterviewOS CLI - Ready")
        print(f"📁 Project root: {Config.PROJECT_ROOT}")
        print(f"📝 Transcripts: {Config.TRANSCRIPTS_DIR}")
        print(f"🔊 Audio: {Config.AUDIO_DIR}")
        print(f"📊 Scores: {Config.SCORES_DIR}")
        
        return 0
        
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
