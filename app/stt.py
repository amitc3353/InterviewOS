"""Speech-to-Text using Deepgram API."""

import json
from pathlib import Path
from datetime import datetime
from deepgram import DeepgramClient, PrerecordedOptions, FileSource
from app.config import Config


def transcribe_audio(audio_file_path: str) -> dict:
    """
    Transcribe an audio file to text using Deepgram.

    Args:
        audio_file_path: Path to audio file (wav, m4a, mp3, etc.)

    Returns:
        dict with keys:
            - transcript: raw text
            - timestamps: word-level timing data
            - metadata: duration, confidence, etc.
    """
    audio_path = Path(audio_file_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

    if not Config.DEEPGRAM_API_KEY:
        raise ValueError("DEEPGRAM_API_KEY not set in .env")

    try:
        # Initialize Deepgram client
        deepgram = DeepgramClient(Config.DEEPGRAM_API_KEY)

        # Read audio file
        with open(audio_path, "rb") as audio:
            buffer_data = audio.read()

        payload: FileSource = {
            "buffer": buffer_data,
        }

        # Configure transcription options
        options = PrerecordedOptions(
            model="nova-2",
            smart_format=True,
            utterances=True,
            punctuate=True,
            diarize=False,
        )

        # Transcribe
        response = deepgram.listen.prerecorded.v("1").transcribe_file(payload, options)

        # Extract results
        result = response.results.channels[0].alternatives[0]

        output = {
            "transcript": result.transcript,
            "confidence": result.confidence,
            "words": [
                {
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "confidence": w.confidence,
                }
                for w in result.words
            ],
            "metadata": {
                "duration": response.results.channels[0].detected_language,
                "model": "nova-2",
                "audio_file": str(audio_path),
            },
        }

        return output

    except Exception as e:
        raise RuntimeError(f"Deepgram transcription failed: {e}")


def transcribe_and_save(audio_file_path: str) -> Path:
    """
    Transcribe audio and save to /transcripts folder.

    Returns:
        Path to saved transcript JSON
    """
    result = transcribe_audio(audio_file_path)

    # Generate output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Config.TRANSCRIPTS_DIR / f"{timestamp}.json"

    # Save
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    return output_file
