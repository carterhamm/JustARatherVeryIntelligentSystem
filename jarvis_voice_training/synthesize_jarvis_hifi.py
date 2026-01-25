#!/usr/bin/env python3
"""
🎙️ J.A.R.V.I.S. Voice Synthesis - Hi-Fi Quality
CD-quality output (16-bit/44.1kHz) with advanced noise removal

Usage: python synthesize_jarvis_hifi.py "Your text here"
"""

import sys
import json
import os
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.signal import butter, filtfilt
import soundfile as sf
import noisereduce as nr

os.environ['COQUI_TOS_AGREED'] = '1'
from TTS.api import TTS

# Paths
VOICE_PROFILE = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model_hq") / "voice_profile_hq.json"
OUTPUT_DIR = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model_hq/hifi_output")
OUTPUT_DIR.mkdir(exist_ok=True)

TARGET_SAMPLE_RATE = 44100  # CD quality

def advanced_noise_removal(audio, sr):
    """
    Advanced multi-stage noise removal to eliminate static/white noise.
    """
    print("   🎨 Stage 1: Spectral noise reduction...")
    # Stage 1: Aggressive spectral noise reduction
    # Use first 0.5 seconds as noise profile if available
    audio_clean = nr.reduce_noise(
        y=audio,
        sr=sr,
        stationary=True,
        prop_decrease=1.0,  # Maximum reduction
        freq_mask_smooth_hz=500,  # Smooth frequency masking
        time_mask_smooth_ms=50,   # Smooth time masking
    )

    print("   🎨 Stage 2: High-frequency noise filtering...")
    # Stage 2: Remove high-frequency hiss/static (above 8kHz)
    # Design a gentle low-pass filter
    nyquist = sr / 2
    cutoff = 8000  # Hz - human voice rarely goes above this
    normal_cutoff = cutoff / nyquist
    b, a = butter(4, normal_cutoff, btype='low', analog=False)
    audio_clean = filtfilt(b, a, audio_clean)

    print("   🎨 Stage 3: RF interference removal...")
    # Stage 3: Remove very low frequency rumble and DC offset
    highpass_cutoff = 80  # Hz
    normal_highpass = highpass_cutoff / nyquist
    b_hp, a_hp = butter(2, normal_highpass, btype='high', analog=False)
    audio_clean = filtfilt(b_hp, a_hp, audio_clean)

    print("   🎨 Stage 4: Spectral gate for residual noise...")
    # Stage 4: Second pass with different settings to catch residual noise
    audio_clean = nr.reduce_noise(
        y=audio_clean,
        sr=sr,
        stationary=True,
        prop_decrease=0.9,
        n_fft=2048,  # Higher FFT for better frequency resolution
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

print("🎙️  J.A.R.V.I.S. Hi-Fi Voice Synthesis")
print("="*70)
print("✨ CD-Quality Output: 16-bit / 44.1 kHz")
print("🔇 Advanced noise removal: 4-stage processing")
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
    from scipy.signal import resample_poly
    # Calculate rational fraction for resampling
    gcd = np.gcd(TARGET_SAMPLE_RATE, sr_original)
    up = TARGET_SAMPLE_RATE // gcd
    down = sr_original // gcd
    audio = resample_poly(audio, up, down)
    sr = TARGET_SAMPLE_RATE
else:
    sr = sr_original

print("\n🎨 Applying advanced noise removal pipeline...")
print("   (This removes static, white noise, RF interference)")

# Apply advanced noise removal
audio_clean = advanced_noise_removal(audio, sr)

# Normalize
print("   🎚️  Normalizing to -1dB peak...")
audio_clean = normalize_audio(audio_clean)

# Save as high-quality WAV
output_file = OUTPUT_DIR / f"jarvis_hifi_{int(__import__('time').time())}.wav"
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

print(f"\n✅ Hi-Fi audio saved!")
print(f"   📁 File: {output_file.name}")
print(f"   📊 Quality: 16-bit / {sr}Hz (CD quality)")
print(f"   ⏱️  Duration: {duration:.2f}s")
print(f"   💽 Size: {file_size_mb:.2f} MB")
print("\n🎉 Done! Voice should be crystal clear with no static.\n")
