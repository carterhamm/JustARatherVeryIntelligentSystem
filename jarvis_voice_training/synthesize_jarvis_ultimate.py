#!/usr/bin/env python3
"""
🎙️ J.A.R.V.I.S. Voice Synthesis - Ultimate Quality
CD-quality output (16-bit/44.1kHz) with GENTLE noise reduction

Usage: python synthesize_jarvis_ultimate.py "Your text here"
"""

import sys
import json
import os
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
import soundfile as sf
import noisereduce as nr

os.environ['COQUI_TOS_AGREED'] = '1'
from TTS.api import TTS

# Paths
VOICE_PROFILE = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model_hq") / "voice_profile_hq.json"
OUTPUT_DIR = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model_hq/ultimate_output")
OUTPUT_DIR.mkdir(exist_ok=True)

TARGET_SAMPLE_RATE = 44100  # CD quality

def gentle_noise_removal(audio, sr):
    """
    Gentle noise removal - preserves voice quality while reducing static.
    Much lighter than the aggressive 4-stage version.
    """
    print("   🎨 Applying gentle noise reduction...")
    # Single pass with conservative settings
    audio_clean = nr.reduce_noise(
        y=audio,
        sr=sr,
        stationary=True,
        prop_decrease=0.75,  # Gentle reduction (not 1.0!)
    )
    return audio_clean

def normalize_audio(audio):
    """Normalize audio to -1dB peak to prevent clipping."""
    peak = np.abs(audio).max()
    if peak > 0:
        target_peak = 0.891  # -1dB
        audio = audio * (target_peak / peak)
    return audio

# Load voice profile
with open(VOICE_PROFILE) as f:
    profile = json.load(f)

print("🎙️  JARVIS Ultimate Voice Synthesis")
print("="*70)
print("✨ CD-Quality Output: 16-bit / 44.1 kHz")
print("🔇 Gentle noise removal (preserves voice quality)")
print("="*70)

# Initialize TTS
print("\n🔧 Loading XTTS-v2 model...")
tts = TTS(profile["model"], progress_bar=False)

# Get reference audio
reference_audio = profile["reference_audio"][0]
print(f"🎵 Reference: {Path(reference_audio).name} (144kHz original)")

# Get text
if len(sys.argv) > 1:
    text = " ".join(sys.argv[1:])
else:
    text = input("\n📝 Enter text to synthesize: ")

print(f"\n💬 Text: '{text}'")
print("🔊 Synthesizing at maximum quality...")

# Generate base audio
temp_file = OUTPUT_DIR / "temp_synthesis.wav"
tts.tts_to_file(
    text=text,
    speaker_wav=str(reference_audio),
    language="en",
    file_path=str(temp_file)
)

# Load audio
audio, sr_original = sf.read(temp_file)
print(f"✅ Base synthesis complete (original rate: {sr_original}Hz)")

# Resample to 44.1kHz if needed
if sr_original != TARGET_SAMPLE_RATE:
    print(f"🔄 Upsampling {sr_original}Hz → {TARGET_SAMPLE_RATE}Hz (CD quality)...")
    # Calculate rational fraction for resampling
    gcd = np.gcd(TARGET_SAMPLE_RATE, sr_original)
    up = TARGET_SAMPLE_RATE // gcd
    down = sr_original // gcd
    audio = resample_poly(audio, up, down)
    sr = TARGET_SAMPLE_RATE
else:
    sr = sr_original

print("\n🎨 Processing audio...")

# Apply GENTLE noise removal (same approach as test_synthesis_hq.wav)
audio_clean = gentle_noise_removal(audio, sr)

# Normalize
print("   🎚️  Normalizing to -1dB peak...")
audio_clean = normalize_audio(audio_clean)

# Save as high-quality WAV
output_file = OUTPUT_DIR / f"jarvis_ultimate_{int(__import__('time').time())}.wav"
print(f"\n💾 Saving as 16-bit/44.1kHz WAV...")

sf.write(
    output_file,
    audio_clean,
    sr,
    subtype='PCM_16'  # 16-bit PCM (CD quality)
)

# Clean up
temp_file.unlink()

# Show file info
file_size_mb = output_file.stat().st_size / (1024 * 1024)
duration = len(audio_clean) / sr

print(f"\n✅ Ultimate quality audio saved!")
print(f"   📁 File: {output_file.name}")
print(f"   📊 Quality: 16-bit / {sr}Hz (CD quality)")
print(f"   ⏱️  Duration: {duration:.2f}s")
print(f"   💽 Size: {file_size_mb:.2f} MB")
print("\n🎉 Done! Voice quality preserved with gentle noise reduction.\n")
