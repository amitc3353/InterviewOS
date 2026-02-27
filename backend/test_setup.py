"""Test script to verify environment setup."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from backend.config import AgentConfig


def test_env_setup():
    """Test that environment variables are properly configured."""
    print("Testing InterviewOS environment setup...\n")
    
    # Load .env file
    load_dotenv()
    
    # Load config
    config = AgentConfig.from_env()
    
    # Check each required field
    checks = {
        "LiveKit URL": config.livekit_url,
        "LiveKit API Key": config.livekit_api_key,
        "LiveKit API Secret": config.livekit_api_secret,
        "Deepgram API Key": config.deepgram_api_key,
        "Anthropic API Key": config.anthropic_api_key,
        "Cartesia API Key": config.cartesia_api_key,
    }
    
    all_good = True
    for name, value in checks.items():
        if value:
            print(f"✓ {name}: {value[:20]}...")
        else:
            print(f"✗ {name}: MISSING")
            all_good = False
    
    print(f"\nConfiguration:")
    print(f"  STT Provider: {config.stt_provider}")
    print(f"  LLM Provider: {config.llm_provider}")
    print(f"  LLM Model: {config.llm_model}")
    print(f"  TTS Provider: {config.tts_provider}")
    print(f"  Cartesia Voice ID: {config.cartesia_voice_id}")
    print(f"  Cartesia Speed: {config.cartesia_speed}")
    print(f"  VAD Sensitivity: {config.vad_sensitivity}")
    print(f"  Silence Threshold: {config.silence_threshold_ms}ms")
    print(f"  Semantic Turn Detection: {config.use_semantic_turn_detection}")
    
    if all_good:
        print("\n✅ All environment variables are set!")
        print("\nNext steps:")
        print("  1. Run the agent: python backend/run_interview.py")
        print("  2. Connect via LiveKit client")
        print("  3. Start speaking!")
        return 0
    else:
        print("\n❌ Some environment variables are missing.")
        print("\nPlease check your .env file and ensure all required keys are set.")
        return 1


if __name__ == "__main__":
    sys.exit(test_env_setup())
