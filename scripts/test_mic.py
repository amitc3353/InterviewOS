#!/usr/bin/env python3
"""Test microphone access and list available devices."""

import sounddevice as sd
import numpy as np
import sys

print("=" * 60)
print("Microphone Test")
print("=" * 60)

# List all audio devices
print("\n📋 Available audio devices:\n")
devices = sd.query_devices()
for i, device in enumerate(devices):
    if device['max_input_channels'] > 0:
        marker = " ← DEFAULT" if i == sd.default.device[0] else ""
        print(f"  [{i}] {device['name']}")
        print(f"      Inputs: {device['max_input_channels']}, Sample rate: {device['default_samplerate']}{marker}")

# Get default input device
default_input = sd.default.device[0]
print(f"\n🎤 Default input device: [{default_input}] {sd.query_devices(default_input)['name']}")

# Test recording
print("\n🎙️  Testing microphone for 3 seconds...")
print("Say something NOW!")

try:
    duration = 3  # seconds
    recording = sd.rec(int(duration * 16000), samplerate=16000, channels=1, dtype='float32')
    sd.wait()
    
    # Analyze recording
    audio_level = np.abs(recording).mean()
    max_level = np.abs(recording).max()
    
    print(f"\n📊 Results:")
    print(f"  Average level: {audio_level:.4f}")
    print(f"  Peak level: {max_level:.4f}")
    
    if audio_level < 0.001:
        print("\n❌ PROBLEM: No audio detected!")
        print("\n💡 Troubleshooting:")
        print("  1. Grant microphone permission:")
        print("     System Settings → Privacy & Security → Microphone")
        print("     → Enable for Terminal/Python")
        print("  2. Check correct mic is selected in System Settings → Sound → Input")
        print("  3. Test mic with Voice Memos app to confirm it works")
    elif audio_level < 0.01:
        print("\n⚠️  WARNING: Audio level very low")
        print("  Mic is working but very quiet. Speak louder or adjust input volume.")
    else:
        print("\n✅ SUCCESS: Microphone is working!")
        print("  Audio is being captured correctly.")
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("\n💡 This usually means mic permissions are not granted.")
    print("  System Settings → Privacy & Security → Microphone → Enable for Terminal")
    sys.exit(1)

print("\n" + "=" * 60)
