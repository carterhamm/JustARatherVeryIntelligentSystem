#!/usr/bin/env python3
"""
🎙️ J.A.R.V.I.S. Voice Synthesis Script
Usage: python synthesize_jarvis.py "Your text here"
"""

import sys
import json
from pathlib import Path
from TTS.api import TTS

# Load voice profile
VOICE_PROFILE = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model") / "voice_profile.json"
OUTPUT_DIR = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model")

with open(VOICE_PROFILE) as f:
    profile = json.load(f)

print("🤖 J.A.R.V.I.S. Voice Synthesis System")
print("="*50)

# Initialize TTS
print("🔧 Loading model...")
tts = TTS(profile["model"])

# Get reference audio
reference_audio = profile["reference_audio"][0]
print(f"🎵 Using reference: {Path(reference_audio).name}")

# Get text
if len(sys.argv) > 1:
    text = " ".join(sys.argv[1:])
else:
    text = input("\n📝 Enter text to synthesize: ")

print(f"\n💬 Text: '{text}'")
print("🔊 Synthesizing...\n")

# Generate
output_file = OUTPUT_DIR / f"jarvis_output_{int(__import__('time').time())}.wav"
tts.tts_to_file(
    text=text,
    speaker_wav=reference_audio,
    language="en",
    file_path=str(output_file)
)

print(f"✅ Audio saved to: {output_file}")
print("\n🎉 Synthesis complete!\n")
