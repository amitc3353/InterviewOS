"""Command-line interface for InterviewOS."""

import sys
import json
import argparse
from pathlib import Path
from app.config import Config
from app.stt import transcribe_and_save
from app.tts import speak
from app.interviewer import InterviewSession
from app.scorer import score_and_save


def cmd_stt(args):
    """STT command: transcribe audio file."""
    try:
        print(f"🎤 Transcribing: {args.file}")
        output_file = transcribe_and_save(args.file)
        
        # Load and display
        with open(output_file) as f:
            result = json.load(f)
        
        print(f"\n📝 Transcript:\n{result['transcript']}\n")
        print(f"✅ Saved to: {output_file}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


def cmd_tts(args):
    """TTS command: convert text to speech."""
    try:
        print(f"🔊 Generating audio...")
        output_file = speak(args.text)
        
        print(f"✅ Audio saved to: {output_file}")
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


def cmd_interview(args):
    """Interview command: get next question from AI interviewer."""
    try:
        session = InterviewSession(scenario=args.scenario)
        
        if args.start:
            # Get opening question
            result = session.start()
        else:
            # Get next question based on input
            if not args.input:
                print("❌ Error: --input required (or use --start for opening)", file=sys.stderr)
                return 1
            
            result = session.next_question(args.input)
        
        print(f"\n💬 Interviewer:\n{result['question']}\n")
        
        if args.verbose:
            print(f"🎯 Intent: {result['intent']}")
            print(f"✨ Good answer covers: {result['what_good_looks_like']}\n")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


def cmd_score(args):
    """Score command: evaluate interview transcript."""
    try:
        print(f"📊 Scoring: {args.transcript}")
        output_file = score_and_save(args.transcript)
        
        # Load and display
        with open(output_file) as f:
            scores = json.load(f)
        
        print(f"\n📈 Scores (out of 10 each):")
        for dim, score in scores['dimensions'].items():
            print(f"  {dim.replace('_', ' ').title()}: {score}")
        
        print(f"\n🎯 Total: {scores['total']}/50\n")
        
        print(f"💪 Strengths:")
        for s in scores['strengths']:
            print(f"  - {s}")
        
        print(f"\n📝 Improvements:")
        for i in scores['improvements']:
            print(f"  - {i}")
        
        print(f"\n🎓 Next Focus:\n  {scores['next_focus']}\n")
        print(f"✅ Saved to: {output_file}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="InterviewOS - AI-powered system design interview practice"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # STT command
    stt_parser = subparsers.add_parser("stt", help="Transcribe audio to text")
    stt_parser.add_argument("--file", required=True, help="Path to audio file")
    
    # TTS command
    tts_parser = subparsers.add_parser("tts", help="Convert text to speech")
    tts_parser.add_argument("--text", required=True, help="Text to speak")
    
    # Interview command
    interview_parser = subparsers.add_parser("interview", help="Get next interview question")
    interview_parser.add_argument("--scenario", default="payments", 
                                   choices=["payments", "social_feed", "e_commerce", "ride_sharing", "video_streaming"],
                                   help="Interview scenario")
    interview_parser.add_argument("--input", help="Candidate's response")
    interview_parser.add_argument("--start", action="store_true", help="Get opening question")
    interview_parser.add_argument("--verbose", "-v", action="store_true", help="Show intent and tips")
    
    # Score command
    score_parser = subparsers.add_parser("score", help="Score interview transcript")
    score_parser.add_argument("--transcript", required=True, help="Path to transcript JSON")
    
    args = parser.parse_args()
    
    # Validate environment
    try:
        Config.validate()
        Config.ensure_dirs()
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    
    # Route to command
    if args.command == "stt":
        return cmd_stt(args)
    elif args.command == "tts":
        return cmd_tts(args)
    elif args.command == "interview":
        return cmd_interview(args)
    elif args.command == "score":
        return cmd_score(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
