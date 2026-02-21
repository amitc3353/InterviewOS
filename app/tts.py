"""Text-to-Speech using Deepgram API."""

from pathlib import Path
from datetime import datetime
from deepgram import DeepgramClient, SpeakOptions
from app.config import Config

def text_to_speech(text: str, output_path: Path = None) -> Path:
    """
    Convert text to speech using Deepgram TTS.
    
    Args:
        text: Text to convert to speech
        output_path: Optional custom output path
        
    Returns:
        Path to saved audio file
    """
    if not Config.DEEPGRAM_API_KEY:
        raise ValueError("DEEPGRAM_API_KEY not set in .env")
    
    if not text.strip():
        raise ValueError("Text cannot be empty")
    
    try:
        # Initialize Deepgram client
        deepgram = DeepgramClient(Config.DEEPGRAM_API_KEY)
        
        # Configure TTS options
        options = SpeakOptions(
            model="aura-asteria-en",  # Natural, conversational voice
            encoding="mp3",
            container="mp3"
        )
        
        # Generate audio
        response = deepgram.speak.v("1").save(
            output_path or _generate_output_path(),
            {"text": text},
            options
        )
        
        return output_path or _generate_output_path()
        
    except Exception as e:
        raise RuntimeError(f"Deepgram TTS failed: {e}")


def _generate_output_path() -> Path:
    """Generate timestamped output filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Config.AUDIO_DIR / f"{timestamp}.mp3"


def speak(text: str) -> Path:
    """
    Convenience function: convert text to speech and return path.
    
    Args:
        text: Text to speak
        
    Returns:
        Path to generated audio file
    """
    output_path = _generate_output_path()
    
    if not Config.DEEPGRAM_API_KEY:
        raise ValueError("DEEPGRAM_API_KEY not set in .env")
    
    try:
        deepgram = DeepgramClient(Config.DEEPGRAM_API_KEY)
        
        options = SpeakOptions(
            model="aura-asteria-en",
            encoding="mp3",
            container="mp3"
        )
        
        # Save directly to file
        deepgram.speak.v("1").save(
            str(output_path),
            {"text": text},
            options
        )
        
        return output_path
        
    except Exception as e:
        raise RuntimeError(f"Deepgram TTS failed: {e}")
