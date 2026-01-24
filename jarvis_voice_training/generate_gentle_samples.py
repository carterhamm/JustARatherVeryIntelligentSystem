#!/usr/bin/env python3
"""
🎙️ Generate GENTLE Nasal Reduction Samples
Much more subtle - preserves voice quality while reducing nasality
"""

import os
import json
from pathlib import Path
import numpy as np
from scipy import signal
import soundfile as sf

os.environ['COQUI_TOS_AGREED'] = '1'
from TTS.api import TTS

# Paths
VOICE_PROFILE = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model") / "voice_profile.json"
OUTPUT_DIR = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model/gentle_samples")
OUTPUT_DIR.mkdir(exist_ok=True)

def apply_gentle_eq(audio, sample_rate, freq, q, gain_db):
    """Apply a single parametric EQ band."""
    w0 = freq / (sample_rate / 2)
    A = 10 ** (gain_db / 40)
    alpha = np.sin(2 * np.pi * w0 / sample_rate) / (2 * q)

    b0 = 1 + alpha * A
    b1 = -2 * np.cos(2 * np.pi * w0 / sample_rate)
    b2 = 1 - alpha * A
    a0 = 1 + alpha / A
    a1 = -2 * np.cos(2 * np.pi * w0 / sample_rate)
    a2 = 1 - alpha / A

    b = np.array([b0, b1, b2]) / a0
    a = np.array([a0, a1, a2]) / a0

    return signal.filtfilt(b, a, audio)

# Load profile
with open(VOICE_PROFILE) as f:
    profile = json.load(f)

print("🎙️  GENTLE NASAL REDUCTION SAMPLE GENERATOR")
print("="*70)
print("Creating subtle variations - no quality loss, just less nasality")
print()

# Initialize TTS
print("🔧 Loading model...")
tts = TTS(profile["model"], progress_bar=False)
reference_audio = profile["reference_audio"][0]

# Test text
test_text = "Good evening, sir. J.A.R.V.I.S. online and ready for your commands."

# Gentle configurations - MUCH more conservative
configs = [
    {
        "name": "original",
        "freq": None,
        "q": None,
        "gain": 0,
        "desc": "No processing - baseline"
    },
    {
        "name": "very_gentle",
        "freq": 2200,
        "q": 3.0,  # Very narrow
        "gain": -2,  # Just -2dB
        "desc": "Barely noticeable reduction"
    },
    {
        "name": "gentle",
        "freq": 2200,
        "q": 2.5,
        "gain": -3,  # -3dB
        "desc": "Subtle nasal reduction"
    },
    {
        "name": "moderate",
        "freq": 2200,
        "q": 2.0,
        "gain": -4,  # -4dB
        "desc": "Noticeable but natural"
    },
    {
        "name": "clear",
        "freq": 2200,
        "q": 1.5,
        "gain": -5,  # -5dB
        "desc": "Clear reduction, still natural"
    },
    {
        "name": "dual_filter",
        "freq": [1800, 2500],  # Two nasal frequencies
        "q": [2.5, 2.5],
        "gain": [-3, -3],
        "desc": "Target two nasal peaks gently"
    },
]

# Generate base audio once
print(f"🔊 Generating base audio...")
temp_file = OUTPUT_DIR / "temp.wav"
tts.tts_to_file(
    text=test_text,
    speaker_wav=str(reference_audio),
    language="en",
    file_path=str(temp_file)
)

base_audio, sample_rate = sf.read(temp_file)
print(f"✅ Base generated ({len(base_audio)/sample_rate:.2f}s)\n")

print("🎨 Creating gentle variations...")
print()

for i, config in enumerate(configs, 1):
    print(f"[{i}/{len(configs)}] {config['name']}: {config['desc']}")

    audio = base_audio.copy()

    # Apply processing
    if config['freq'] is not None:
        if isinstance(config['freq'], list):
            # Multiple filters
            for freq, q, gain in zip(config['freq'], config['q'], config['gain']):
                audio = apply_gentle_eq(audio, sample_rate, freq, q, gain)
                print(f"    ⚙️  {gain}dB @ {freq}Hz (Q={q})")
        else:
            # Single filter
            audio = apply_gentle_eq(audio, sample_rate, config['freq'], config['q'], config['gain'])
            print(f"    ⚙️  {config['gain']}dB @ {config['freq']}Hz (Q={config['q']})")
    else:
        print(f"    ⚙️  No processing")

    # Save
    output_file = OUTPUT_DIR / f"jarvis_{config['name']}.wav"
    sf.write(output_file, audio, sample_rate)
    print(f"    ✓ Saved: {output_file.name}")
    print()

# Clean up
temp_file.unlink()

print("="*70)
print("🎉 GENTLE SAMPLES COMPLETE!")
print("="*70)
print(f"\n📁 Samples saved to: {OUTPUT_DIR}\n")
print("🎧 Listen and compare:\n")

for config in configs:
    filename = f"jarvis_{config['name']}.wav"
    print(f"   • {filename:25s} - {config['desc']}")

print("\n💡 Start with 'jarvis_gentle.wav' (-3dB)")
print("   If still too nasally, try 'jarvis_moderate.wav' (-4dB)")
print("   If you want original, it's 'jarvis_original.wav'\n")
print(f"🔊 Listen: open {OUTPUT_DIR}/jarvis_gentle.wav\n")
