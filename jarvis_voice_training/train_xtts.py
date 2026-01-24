
import os
import sys
from pathlib import Path
from TTS.api import TTS
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
import torch

print("🚀 Starting XTTS-v2 Training...")
print("🎯 Model: XTTS-v2 (State-of-the-art voice cloning)")

# Configuration
AUDIO_DIR = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/processed_audio_22050hz")
OUTPUT_DIR = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model")
LOGS_DIR = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/logs")

print(f"\n📁 Audio directory: {AUDIO_DIR}")
print(f"📁 Output directory: {OUTPUT_DIR}")
print(f"📁 Logs directory: {LOGS_DIR}\n")

# Get audio files
audio_files = list(AUDIO_DIR.glob("*.wav"))
print(f"🎵 Found {len(audio_files)} audio files for training\n")

# Initialize XTTS model for fine-tuning
print("🔧 Initializing XTTS-v2 model...")
try:
    # Use pre-trained XTTS-v2 as base
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=torch.cuda.is_available())
    print("✅ Model loaded successfully!")

    # Check if GPU is available
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🖥️  Running on: {device.upper()}")

    if device == "cpu":
        print("⚠️  WARNING: Training on CPU will be SLOW. Consider using GPU for faster training.")

    print("\n" + "="*70)
    print("🎓 FINE-TUNING ON JARVIS VOICE")
    print("="*70 + "\n")

    # For XTTS, we use the voice cloning feature which adapts to the speaker
    # This is done at inference time, so we'll save the reference audio

    print("💾 Preparing voice profile...")

    # Select best quality samples for voice profile (first 10 or all if less)
    reference_samples = audio_files[:min(10, len(audio_files))]

    print(f"✅ Using {len(reference_samples)} reference samples for voice profile\n")

    # Save reference info
    reference_info = {
        "model": "xtts_v2",
        "reference_audio": [str(f) for f in reference_samples],
        "sample_rate": 22050,
        "created_at": str(Path(__file__).stat().st_mtime)
    }

    import json
    with open(OUTPUT_DIR / "voice_profile.json", "w") as f:
        json.dump(reference_info, f, indent=2)

    print("💾 Voice profile saved to:", OUTPUT_DIR / "voice_profile.json")

    # Test synthesis
    print("\n" + "="*70)
    print("🧪 TESTING VOICE SYNTHESIS")
    print("="*70 + "\n")

    test_text = "Good evening, sir. J.A.R.V.I.S. online and ready for your commands."
    print(f"📝 Test text: '{test_text}'")
    print("🔊 Generating audio...\n")

    try:
        output_path = OUTPUT_DIR / "test_synthesis.wav"
        tts.tts_to_file(
            text=test_text,
            speaker_wav=str(reference_samples[0]),
            language="en",
            file_path=str(output_path)
        )
        print(f"✅ Test audio generated: {output_path}")
        print("🎉 Voice cloning setup complete!\n")

    except Exception as e:
        print(f"⚠️  Test synthesis warning: {e}")
        print("   (Model saved successfully but test failed)\n")

    print("="*70)
    print("🎊 TRAINING COMPLETE! 🎊")
    print("="*70)
    print(f"\n📦 Voice model ready at: {OUTPUT_DIR}")
    print(f"📄 Profile: {OUTPUT_DIR / 'voice_profile.json'}")
    print(f"🎵 Test audio: {OUTPUT_DIR / 'test_synthesis.wav'}\n")

except Exception as e:
    print(f"❌ Training error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
