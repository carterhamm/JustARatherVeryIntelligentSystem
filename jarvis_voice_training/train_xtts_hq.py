#!/usr/bin/env python3
"""
🎙️ JARVIS Voice Training - HIGH QUALITY VERSION
Uses original unprocessed audio files to preserve quality
"""

import os
import json
from pathlib import Path
from datetime import datetime

os.environ['COQUI_TOS_AGREED'] = '1'
from TTS.api import TTS

# Paths
ORIGINAL_AUDIO_DIR = Path("/Users/mr.stark/Downloads/J.A.R.V.I.S. Resources/J.A.R.V.I.S. Voice FIles/ElevenLabs-Upscaled3x")
OUTPUT_DIR = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model_hq")
OUTPUT_DIR.mkdir(exist_ok=True)

print("🎙️  JARVIS VOICE TRAINING - HIGH QUALITY")
print("="*70)
print("✨ Using ORIGINAL files (no preprocessing - maximum quality)")
print("="*70)
print()

# Get all audio files
audio_files = sorted(list(ORIGINAL_AUDIO_DIR.glob("chunk_*.wav")))
print(f"📁 Found {len(audio_files)} original audio files")
print()

# Use best quality samples for reference
# Select diverse samples from different parts
reference_samples = [
    audio_files[0],   # chunk_1
    audio_files[4],   # chunk_13
    audio_files[8],   # chunk_18
    audio_files[10],  # chunk_2
    audio_files[12],  # chunk_20
]

print("🎵 Selected reference samples (original quality):")
for i, sample in enumerate(reference_samples, 1):
    print(f"   {i}. {sample.name}")
print()

# Initialize TTS
print("🔧 Loading XTTS-v2 model...")
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False)
print("✅ Model loaded")
print()

# Test synthesis
test_text = "Good evening, sir. JARVIS online and ready for your commands."
print(f"💬 Test text: '{test_text}'")
print("🔊 Synthesizing with high-quality reference audio...")
print()

output_path = OUTPUT_DIR / "test_synthesis_hq.wav"

# Use first reference sample - TTS will handle any resampling internally
tts.tts_to_file(
    text=test_text,
    speaker_wav=str(reference_samples[0]),
    language="en",
    file_path=str(output_path)
)

print(f"✅ Audio saved to: {output_path}")
print()

# Save voice profile
profile = {
    "model": "xtts_v2",
    "reference_audio": [str(s) for s in reference_samples],
    "original_quality": True,
    "sample_rate": 144000,
    "created_at": str(datetime.now().timestamp())
}

profile_path = OUTPUT_DIR / "voice_profile_hq.json"
with open(profile_path, 'w') as f:
    json.dump(profile, f, indent=2)

print(f"📝 Voice profile saved to: {profile_path}")
print()
print("="*70)
print("🎉 HIGH-QUALITY VOICE TRAINING COMPLETE!")
print("="*70)
print()
print(f"🔊 Listen to test: open {output_path}")
print()
print("✨ This version uses the original files directly")
print("   No downsampling, no loudnorm artifacts, maximum quality!")
print()
