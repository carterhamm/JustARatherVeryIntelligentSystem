#!/usr/bin/env python3
"""
🎙️ Generate Multiple JARVIS Voice Samples with Different Settings
Creates several versions so you can pick the best one
"""

import os
import sys
import json
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
import soundfile as sf

os.environ['COQUI_TOS_AGREED'] = '1'
from TTS.api import TTS

# Paths
VOICE_PROFILE = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model") / "voice_profile.json"
OUTPUT_DIR = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model/samples")
OUTPUT_DIR.mkdir(exist_ok=True)

def apply_eq_filter(audio, sample_rate, nasal_reduction_db=-8, bass_boost_db=4):
    """Apply EQ to reduce nasality and boost bass."""
    # Reduce nasal frequencies (1-3kHz)
    nasal_freq = 2000
    nasal_q = 1.5
    b_nasal, a_nasal = signal.iirpeak(nasal_freq, nasal_q, sample_rate)
    b_nasal = b_nasal * (10 ** (nasal_reduction_db / 20))

    # Boost bass (200-500Hz)
    bass_freq = 350
    bass_q = 1.0
    b_bass, a_bass = signal.iirpeak(bass_freq, bass_q, sample_rate)
    b_bass = b_bass * (10 ** (bass_boost_db / 20))

    audio = signal.filtfilt(b_nasal, a_nasal, audio)
    audio = signal.filtfilt(b_bass, a_bass, audio)
    return audio

def pitch_shift(audio, sample_rate, semitones):
    """Shift pitch by semitones."""
    shift_factor = 2 ** (semitones / 12.0)
    new_length = int(len(audio) / shift_factor)
    shifted = signal.resample(audio, new_length)
    stretched = signal.resample(shifted, len(audio))
    return stretched

def process_audio(audio, sample_rate, pitch_semitones, nasal_db, bass_db, add_harmonics=True):
    """Process audio with specified parameters."""
    # Apply EQ
    audio = apply_eq_filter(audio, sample_rate, nasal_db, bass_db)

    # Pitch shift
    if pitch_semitones != 0:
        audio = pitch_shift(audio, sample_rate, pitch_semitones)

    # Add harmonics for richness
    if add_harmonics and pitch_semitones < 0:
        harmonic = pitch_shift(audio, sample_rate, pitch_semitones * 2) * 0.12
        audio = audio + harmonic

    # Normalize
    max_val = np.max(np.abs(audio))
    if max_val > 0.95:
        audio = audio * (0.95 / max_val)

    return audio

# Load profile
with open(VOICE_PROFILE) as f:
    profile = json.load(f)

print("🎙️  J.A.R.V.I.S. VOICE SAMPLE GENERATOR")
print("="*70)
print("Generating multiple versions with different voice settings...")
print()

# Initialize TTS
tts = TTS(profile["model"], progress_bar=False)
reference_audio = profile["reference_audio"][2]  # Use middle sample

# Test text
test_text = "Good evening, sir. J.A.R.V.I.S. online and ready for your commands."

# Different voice configurations to try
configs = [
    {
        "name": "original",
        "pitch": 0,
        "nasal_db": 0,
        "bass_db": 0,
        "harmonics": False,
        "desc": "No processing (baseline)"
    },
    {
        "name": "slightly_deeper",
        "pitch": -1,
        "nasal_db": -4,
        "bass_db": 2,
        "harmonics": False,
        "desc": "Subtle improvements"
    },
    {
        "name": "deeper",
        "pitch": -2,
        "nasal_db": -8,
        "bass_db": 4,
        "harmonics": True,
        "desc": "Moderate depth, less nasality"
    },
    {
        "name": "very_deep",
        "pitch": -3,
        "nasal_db": -10,
        "bass_db": 6,
        "harmonics": True,
        "desc": "Maximum depth and richness"
    },
    {
        "name": "deep_smooth",
        "pitch": -2.5,
        "nasal_db": -12,
        "bass_db": 5,
        "harmonics": True,
        "desc": "Deep with strong nasal reduction"
    },
]

# Generate base audio once
print("🔊 Generating base audio...")
temp_file = OUTPUT_DIR / "temp.wav"
tts.tts_to_file(
    text=test_text,
    speaker_wav=str(reference_audio),
    language="en",
    file_path=str(temp_file)
)

base_audio, sample_rate = sf.read(temp_file)
print(f"✅ Base audio generated ({len(base_audio)/sample_rate:.2f}s)\n")

# Process with each configuration
print("🎨 Creating variations...")
print()

for i, config in enumerate(configs, 1):
    print(f"[{i}/{len(configs)}] {config['name']}: {config['desc']}")

    # Process audio
    processed = process_audio(
        base_audio.copy(),
        sample_rate,
        pitch_semitones=config['pitch'],
        nasal_db=config['nasal_db'],
        bass_db=config['bass_db'],
        add_harmonics=config['harmonics']
    )

    # Save
    output_file = OUTPUT_DIR / f"jarvis_{config['name']}.wav"
    sf.write(output_file, processed, sample_rate)
    print(f"    ✓ Saved: {output_file.name}")
    print()

# Clean up
temp_file.unlink()

print("="*70)
print("🎉 SAMPLE GENERATION COMPLETE!")
print("="*70)
print(f"\n📁 All samples saved to: {OUTPUT_DIR}\n")
print("🎧 Listen to each version and pick your favorite:\n")

for config in configs:
    filename = f"jarvis_{config['name']}.wav"
    print(f"   • {filename:25s} - {config['desc']}")

print("\n💡 Recommended: Start with 'jarvis_deeper.wav'")
print("   (Good balance of depth and naturalness)\n")
print(f"🔊 To play: open {OUTPUT_DIR}/jarvis_deeper.wav\n")
