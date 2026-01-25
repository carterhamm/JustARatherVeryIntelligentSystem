#!/usr/bin/env python3
"""
🎙️ J.A.R.V.I.S. Voice Synthesis - CLEAN HIGH QUALITY
Uses original reference audio + noise reduction for clean output

Usage: python synthesize_jarvis_clean.py "Your text here"
"""

import sys
import json
import os
from pathlib import Path
import numpy as np
from scipy import signal
import soundfile as sf
import noisereduce as nr

os.environ['COQUI_TOS_AGREED'] = '1'
from TTS.api import TTS

# Paths
VOICE_PROFILE = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model_hq") / "voice_profile_hq.json"
OUTPUT_DIR = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model_hq")

# Load voice profile
with open(VOICE_PROFILE) as f:
    profile = json.load(f)

print("🤖 J.A.R.V.I.S. Voice Synthesis - Clean HQ")
print("="*60)
print("✨ Using original reference audio for maximum quality")
print("="*60)

# Initialize TTS
print("\n🔧 Loading model...")
tts = TTS(profile["model"], progress_bar=False)

# Get reference audio
reference_audio = profile["reference_audio"][0]
print(f"🎵 Using reference: {Path(reference_audio).name}")

# Get text
if len(sys.argv) > 1:
    text = " ".join(sys.argv[1:])
else:
    text = input("\n📝 Enter text to synthesize: ")

print(f"\n💬 Text: '{text}'")
print("🔊 Synthesizing...")

# Generate base audio
temp_file = OUTPUT_DIR / "temp_synthesis.wav"
tts.tts_to_file(
    text=text,
    speaker_wav=str(reference_audio),
    language="en",
    file_path=str(temp_file)
)

# Load audio
audio, sample_rate = sf.read(temp_file)

print("🎨 Applying noise reduction...")

# Apply gentle noise reduction to remove static
# This uses spectral gating to remove background noise
audio_clean = nr.reduce_noise(
    y=audio,
    sr=sample_rate,
    stationary=True,
    prop_decrease=0.8,  # Reduce noise by 80%
)

# Save
output_file = OUTPUT_DIR / f"jarvis_clean_{int(__import__('time').time())}.wav"
sf.write(output_file, audio_clean, sample_rate)

# Clean up
temp_file.unlink()

print(f"\n✅ Audio saved to: {output_file}")
print("\n🎉 Done! Voice should be clean, clear, and true to original.\n")
