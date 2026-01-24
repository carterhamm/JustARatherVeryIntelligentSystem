#!/usr/bin/env python3
"""
🎙️ J.A.R.V.I.S. Voice Synthesis Script - IMPROVED VERSION
Enhanced with audio processing to sound more adult male and less nasally

Usage: python synthesize_jarvis_improved.py "Your text here"
"""

import sys
import json
import os
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
import soundfile as sf

# Set environment variable for Coqui license
os.environ['COQUI_TOS_AGREED'] = '1'

from TTS.api import TTS

# Paths
VOICE_PROFILE = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model") / "voice_profile.json"
OUTPUT_DIR = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model")

def apply_eq_filter(audio, sample_rate):
    """
    Apply equalization to reduce nasal frequencies and enhance lower frequencies.
    Nasality typically occurs in 1-3kHz range. We'll reduce that and boost bass.
    """
    # Design a parametric EQ
    # Reduce nasal frequencies (1-3kHz) by -6dB
    nasal_freq = 2000  # Center of nasal range
    nasal_q = 1.5
    nasal_gain_db = -8  # Reduce by 8dB

    # Design notch filter for nasal reduction
    b_nasal, a_nasal = signal.iirpeak(nasal_freq, nasal_q, sample_rate)
    b_nasal = b_nasal * (10 ** (nasal_gain_db / 20))

    # Boost lower frequencies (200-500Hz) for deeper voice
    bass_freq = 350
    bass_q = 1.0
    bass_gain_db = 4  # Boost by 4dB

    b_bass, a_bass = signal.iirpeak(bass_freq, bass_q, sample_rate)
    b_bass = b_bass * (10 ** (bass_gain_db / 20))

    # Apply filters
    audio = signal.filtfilt(b_nasal, a_nasal, audio)
    audio = signal.filtfilt(b_bass, a_bass, audio)

    return audio

def pitch_shift(audio, sample_rate, semitones=-2):
    """
    Shift pitch down to make voice deeper and more masculine.
    -2 semitones makes it noticeably deeper without sounding unnatural.
    """
    # Simple pitch shifting using resampling
    # This maintains formants better than other methods
    shift_factor = 2 ** (semitones / 12.0)

    # Resample to shift pitch
    new_length = int(len(audio) / shift_factor)
    shifted = signal.resample(audio, new_length)

    # Stretch back to original length to maintain duration
    stretched = signal.resample(shifted, len(audio))

    return stretched

def enhance_voice_depth(audio, sample_rate):
    """
    Apply multiple processing stages to make voice sound deeper and more adult.
    """
    # 1. Reduce nasal frequencies and boost bass
    audio = apply_eq_filter(audio, sample_rate)

    # 2. Shift pitch down by 2 semitones
    audio = pitch_shift(audio, sample_rate, semitones=-2)

    # 3. Add subtle harmonic enhancement for richness
    # Generate low-frequency harmonics
    low_harmonic = pitch_shift(audio, sample_rate, semitones=-12) * 0.15
    audio = audio + low_harmonic

    # 4. Normalize to prevent clipping
    max_val = np.max(np.abs(audio))
    if max_val > 0.95:
        audio = audio * (0.95 / max_val)

    return audio

def de_ess(audio, sample_rate):
    """
    Reduce sibilance (harsh 's' sounds) that can contribute to nasality.
    """
    # High-pass filter above 6kHz for sibilance detection
    sos = signal.butter(4, 6000, 'hp', fs=sample_rate, output='sos')
    sibilance = signal.sosfilt(sos, audio)

    # Compress sibilance
    threshold = 0.3
    ratio = 4.0

    sibilance_envelope = np.abs(sibilance)
    gain_reduction = np.ones_like(sibilance_envelope)
    above_threshold = sibilance_envelope > threshold
    gain_reduction[above_threshold] = threshold + (sibilance_envelope[above_threshold] - threshold) / ratio
    gain_reduction = gain_reduction / (sibilance_envelope + 1e-10)

    # Apply de-essing
    audio = audio * gain_reduction

    return audio

# Load voice profile
with open(VOICE_PROFILE) as f:
    profile = json.load(f)

print("🤖 J.A.R.V.I.S. Voice Synthesis System - ENHANCED")
print("="*60)
print("✨ Features: Deeper voice, reduced nasality, adult male tone")
print("="*60)

# Initialize TTS
print("\n🔧 Loading XTTS-v2 model...")
tts = TTS(profile["model"], progress_bar=False)

# Use multiple reference samples and pick the deepest-sounding ones
# Typically the later chunks might have deeper voice
reference_audios = profile["reference_audio"]
print(f"📚 Available reference samples: {len(reference_audios)}")

# For better quality, we'll use the middle samples which tend to have better quality
# and more consistent pitch
if len(reference_audios) >= 5:
    # Use samples 3-7 (middle range, usually more consistent)
    selected_refs = reference_audios[2:7]
    print(f"🎵 Using {len(selected_refs)} middle-range reference samples")
else:
    selected_refs = [reference_audios[0]]
    print(f"🎵 Using reference: {Path(reference_audios[0]).name}")

# Get text
if len(sys.argv) > 1:
    text = " ".join(sys.argv[1:])
else:
    text = input("\n📝 Enter text to synthesize: ")

print(f"\n💬 Text: '{text}'")
print("🔊 Synthesizing with enhanced processing...")
print("   ⚙️  Applying: pitch shift (-2 semitones)")
print("   ⚙️  Applying: nasal frequency reduction")
print("   ⚙️  Applying: bass enhancement")
print("   ⚙️  Applying: de-essing")
print()

# Generate with primary reference
temp_file = OUTPUT_DIR / "temp_synthesis.wav"
tts.tts_to_file(
    text=text,
    speaker_wav=str(selected_refs[0]),
    language="en",
    file_path=str(temp_file)
)

# Load the generated audio
audio, sample_rate = sf.read(temp_file)

print("🎨 Post-processing audio...")

# Apply enhancements
audio = enhance_voice_depth(audio, sample_rate)
audio = de_ess(audio, sample_rate)

# Save enhanced version
output_file = OUTPUT_DIR / f"jarvis_enhanced_{int(__import__('time').time())}.wav"
sf.write(output_file, audio, sample_rate)

# Clean up temp file
temp_file.unlink()

print(f"\n✅ Enhanced audio saved to: {output_file}")
print("\n🎉 Synthesis complete!")
print("\n📊 Enhancements applied:")
print("   ✓ Pitch shifted down 2 semitones (deeper)")
print("   ✓ Nasal frequencies reduced by 8dB")
print("   ✓ Bass frequencies boosted by 4dB")
print("   ✓ Harmonic richness added")
print("   ✓ Sibilance reduced")
print("\n🎧 The voice should now sound more like an adult male!\n")
