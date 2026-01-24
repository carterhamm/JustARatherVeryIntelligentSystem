#!/usr/bin/env python3
"""
🎙️ J.A.R.V.I.S. Voice Synthesis - SUBTLE NASAL REDUCTION ONLY
Just removes nasality, keeps everything else pristine

Usage: python synthesize_jarvis_subtle.py "Your text here"
"""

import sys
import json
import os
from pathlib import Path
import numpy as np
from scipy import signal
import soundfile as sf

os.environ['COQUI_TOS_AGREED'] = '1'
from TTS.api import TTS

# Paths
VOICE_PROFILE = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model") / "voice_profile.json"
OUTPUT_DIR = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model")

def reduce_nasality_gentle(audio, sample_rate):
    """
    Very gentle nasal reduction - surgical approach.
    Only targets the exact nasal frequency range without affecting anything else.
    """
    # Use a narrow notch filter centered on the nasal resonance frequency
    # Nasality is typically around 1.5-2.5kHz
    # We'll use a very gentle reduction to avoid artifacts

    # Create a gentle parametric EQ cut at nasal frequencies
    # Much narrower Q and less reduction than before
    nasal_freq = 2200  # Hz - peak nasal resonance
    q_factor = 2.5     # Narrow filter (only affects nearby frequencies)
    gain_db = -3       # Gentle 3dB reduction (not -8dB like before!)

    # Design the filter
    w0 = nasal_freq / (sample_rate / 2)

    # Peaking EQ filter
    A = 10 ** (gain_db / 40)
    alpha = np.sin(2 * np.pi * w0 / sample_rate) / (2 * q_factor)

    b0 = 1 + alpha * A
    b1 = -2 * np.cos(2 * np.pi * w0 / sample_rate)
    b2 = 1 - alpha * A
    a0 = 1 + alpha / A
    a1 = -2 * np.cos(2 * np.pi * w0 / sample_rate)
    a2 = 1 - alpha / A

    b = np.array([b0, b1, b2]) / a0
    a = np.array([a0, a1, a2]) / a0

    # Apply filter
    filtered = signal.filtfilt(b, a, audio)

    return filtered

# Load voice profile
with open(VOICE_PROFILE) as f:
    profile = json.load(f)

print("🤖 J.A.R.V.I.S. Voice Synthesis - Subtle Nasal Reduction")
print("="*60)
print("✨ Gentle processing: Only removes nasality, keeps quality")
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

print("🎨 Applying gentle nasal reduction...")
print("   ⚙️  -3dB at 2.2kHz (narrow filter)")

# Apply ONLY gentle nasal reduction - nothing else!
audio_processed = reduce_nasality_gentle(audio, sample_rate)

# Save
output_file = OUTPUT_DIR / f"jarvis_subtle_{int(__import__('time').time())}.wav"
sf.write(output_file, audio_processed, sample_rate)

# Clean up
temp_file.unlink()

print(f"\n✅ Audio saved to: {output_file}")
print("\n🎉 Done! Voice should sound the same but less nasally.\n")
