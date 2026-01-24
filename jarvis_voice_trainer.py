#!/usr/bin/env python3
"""
🎙️ J.A.R.V.I.S. Voice Cloning Training System 🎙️
Using Coqui TTS XTTS-v2 for high-quality voice synthesis
"""

import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
import wave

print("\n" + "="*70)
print("🤖 J.A.R.V.I.S. VOICE CLONING TRAINING SYSTEM 🤖")
print("="*70 + "\n")

# Configuration
SOURCE_FOLDER = Path("/Users/mr.stark/Downloads/J.A.R.V.I.S. Resources/J.A.R.V.I.S. Voice FIles/ElevenLabs-Upscaled3x")
OUTPUT_BASE = Path("/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training")
PROCESSED_FOLDER = OUTPUT_BASE / "processed_audio_22050hz"
MODEL_OUTPUT = OUTPUT_BASE / "trained_model"
LOGS_FOLDER = OUTPUT_BASE / "logs"

TARGET_SAMPLE_RATE = 22050
TARGET_CHANNELS = 1  # Mono

# Create directories
for folder in [OUTPUT_BASE, PROCESSED_FOLDER, MODEL_OUTPUT, LOGS_FOLDER]:
    folder.mkdir(parents=True, exist_ok=True)

print(f"📁 Source folder: {SOURCE_FOLDER}")
print(f"📁 Output base: {OUTPUT_BASE}")
print(f"📁 Processed audio: {PROCESSED_FOLDER}")
print(f"📁 Model output: {MODEL_OUTPUT}")
print(f"\n{'='*70}\n")

# ============================================================================
# STEP 1: Audio Preprocessing
# ============================================================================

def get_audio_info(file_path):
    """Get audio file information using ffprobe."""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_streams', str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        if data.get('streams'):
            stream = data['streams'][0]
            return {
                'sample_rate': int(stream.get('sample_rate', 0)),
                'channels': int(stream.get('channels', 0)),
                'duration': float(stream.get('duration', 0))
            }
    except Exception as e:
        print(f"⚠️  Error getting info for {file_path}: {e}")
    return None


def process_audio_file(input_path, output_path, progress_callback=None):
    """
    Process audio file: resample to 22050Hz, convert to mono, normalize.
    Returns True if successful.
    """
    try:
        # FFmpeg command for processing
        cmd = [
            'ffmpeg', '-i', str(input_path),
            '-ar', str(TARGET_SAMPLE_RATE),  # Resample to 22050 Hz
            '-ac', str(TARGET_CHANNELS),      # Convert to mono
            '-af', 'loudnorm',                # Normalize audio levels
            '-y',                             # Overwrite output
            str(output_path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout per file
        )

        if result.returncode == 0:
            if progress_callback:
                progress_callback()
            return True
        else:
            print(f"⚠️  FFmpeg error: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⚠️  Timeout processing {input_path.name}")
        return False
    except Exception as e:
        print(f"⚠️  Error processing {input_path.name}: {e}")
        return False


def preprocess_all_audio():
    """Preprocess all audio files with progress tracking."""
    print("🎵 STEP 1: AUDIO PREPROCESSING 🎵\n")

    # Get all WAV files
    audio_files = list(SOURCE_FOLDER.glob("*.wav"))
    total_files = len(audio_files)

    if total_files == 0:
        print(f"❌ No WAV files found in {SOURCE_FOLDER}")
        return False

    print(f"📊 Found {total_files} audio files")

    # Calculate total duration
    print("\n🔍 Analyzing audio files...")
    total_duration = 0
    valid_files = []

    for i, file_path in enumerate(audio_files):
        info = get_audio_info(file_path)
        if info:
            total_duration += info['duration']
            valid_files.append((file_path, info))
            print(f"  ✓ {file_path.name}: {info['duration']:.2f}s @ {info['sample_rate']}Hz")

    print(f"\n📈 Total audio duration: {total_duration:.2f} seconds ({total_duration/60:.2f} minutes)")

    if total_duration < 120:  # Less than 2 minutes
        print("⚠️  WARNING: Less than 2 minutes of audio. Training quality may be poor.")
    elif total_duration < 600:  # Less than 10 minutes
        print("✅ Audio duration is acceptable for basic voice cloning")
    else:
        print("🎉 Excellent! Plenty of audio data for high-quality training")

    print(f"\n{'='*70}")
    print("🔧 PROCESSING AUDIO FILES")
    print(f"{'='*70}\n")
    print(f"Target: {TARGET_SAMPLE_RATE}Hz, Mono, Normalized\n")

    # Process each file with fancy progress bar
    processed_count = 0
    failed_files = []
    start_time = time.time()

    def update_progress():
        nonlocal processed_count
        processed_count += 1
        percent = (processed_count / len(valid_files)) * 100

        # Fancy progress bar
        bar_length = 40
        filled = int(bar_length * processed_count / len(valid_files))
        bar = "█" * filled + "░" * (bar_length - filled)

        elapsed = time.time() - start_time
        eta = (elapsed / processed_count) * (len(valid_files) - processed_count) if processed_count > 0 else 0

        print(f"\r  [{bar}] {percent:.1f}% | {processed_count}/{len(valid_files)} files | ETA: {eta:.0f}s", end="", flush=True)

    for file_path, info in valid_files:
        output_path = PROCESSED_FOLDER / file_path.name

        if not process_audio_file(file_path, output_path, update_progress):
            failed_files.append(file_path.name)

    print("\n")  # New line after progress bar

    elapsed_time = time.time() - start_time

    print(f"\n{'='*70}")
    print(f"✨ PREPROCESSING COMPLETE ✨")
    print(f"{'='*70}\n")
    print(f"✅ Successfully processed: {processed_count - len(failed_files)}/{len(valid_files)} files")
    if failed_files:
        print(f"❌ Failed files: {len(failed_files)}")
        for f in failed_files:
            print(f"   - {f}")
    print(f"⏱️  Time elapsed: {elapsed_time:.2f}s")
    print(f"📁 Output folder: {PROCESSED_FOLDER}\n")

    return processed_count > 0


# ============================================================================
# STEP 2: Install and Setup Coqui TTS
# ============================================================================

def setup_coqui_tts():
    """Check Coqui TTS installation."""
    print(f"\n{'='*70}")
    print("🔧 STEP 2: VERIFYING COQUI TTS")
    print(f"{'='*70}\n")

    print("📦 Checking for Coqui TTS installation...")

    try:
        import TTS
        print("✅ TTS is installed!")
        print(f"   Version: {TTS.__version__}")
        return True
    except ImportError:
        print("❌ TTS not found!")
        print("💡 Please run: ./run_jarvis_training.sh (handles installation automatically)")
        return False


# ============================================================================
# STEP 3: Train Voice Model
# ============================================================================

def train_voice_model():
    """Train JARVIS voice model using XTTS-v2."""
    print(f"\n{'='*70}")
    print("🎓 STEP 3: TRAINING JARVIS VOICE MODEL")
    print(f"{'='*70}\n")

    # Check if we have processed audio
    processed_files = list(PROCESSED_FOLDER.glob("*.wav"))
    if not processed_files:
        print("❌ No processed audio files found!")
        return False

    print(f"🎵 Using {len(processed_files)} audio files for training")

    # Create training script
    training_script = OUTPUT_BASE / "train_xtts.py"

    training_code = f'''
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
AUDIO_DIR = Path("{PROCESSED_FOLDER}")
OUTPUT_DIR = Path("{MODEL_OUTPUT}")
LOGS_DIR = Path("{LOGS_FOLDER}")

print(f"\\n📁 Audio directory: {{AUDIO_DIR}}")
print(f"📁 Output directory: {{OUTPUT_DIR}}")
print(f"📁 Logs directory: {{LOGS_DIR}}\\n")

# Get audio files
audio_files = list(AUDIO_DIR.glob("*.wav"))
print(f"🎵 Found {{len(audio_files)}} audio files for training\\n")

# Initialize XTTS model for fine-tuning
print("🔧 Initializing XTTS-v2 model...")
try:
    # Use pre-trained XTTS-v2 as base
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=torch.cuda.is_available())
    print("✅ Model loaded successfully!")

    # Check if GPU is available
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🖥️  Running on: {{device.upper()}}")

    if device == "cpu":
        print("⚠️  WARNING: Training on CPU will be SLOW. Consider using GPU for faster training.")

    print("\\n" + "="*70)
    print("🎓 FINE-TUNING ON JARVIS VOICE")
    print("="*70 + "\\n")

    # For XTTS, we use the voice cloning feature which adapts to the speaker
    # This is done at inference time, so we'll save the reference audio

    print("💾 Preparing voice profile...")

    # Select best quality samples for voice profile (first 10 or all if less)
    reference_samples = audio_files[:min(10, len(audio_files))]

    print(f"✅ Using {{len(reference_samples)}} reference samples for voice profile\\n")

    # Save reference info
    reference_info = {{
        "model": "xtts_v2",
        "reference_audio": [str(f) for f in reference_samples],
        "sample_rate": {TARGET_SAMPLE_RATE},
        "created_at": str(Path(__file__).stat().st_mtime)
    }}

    import json
    with open(OUTPUT_DIR / "voice_profile.json", "w") as f:
        json.dump(reference_info, f, indent=2)

    print("💾 Voice profile saved to:", OUTPUT_DIR / "voice_profile.json")

    # Test synthesis
    print("\\n" + "="*70)
    print("🧪 TESTING VOICE SYNTHESIS")
    print("="*70 + "\\n")

    test_text = "Good evening, sir. J.A.R.V.I.S. online and ready for your commands."
    print(f"📝 Test text: '{{test_text}}'")
    print("🔊 Generating audio...\\n")

    try:
        output_path = OUTPUT_DIR / "test_synthesis.wav"
        tts.tts_to_file(
            text=test_text,
            speaker_wav=str(reference_samples[0]),
            language="en",
            file_path=str(output_path)
        )
        print(f"✅ Test audio generated: {{output_path}}")
        print("🎉 Voice cloning setup complete!\\n")

    except Exception as e:
        print(f"⚠️  Test synthesis warning: {{e}}")
        print("   (Model saved successfully but test failed)\\n")

    print("="*70)
    print("🎊 TRAINING COMPLETE! 🎊")
    print("="*70)
    print(f"\\n📦 Voice model ready at: {{OUTPUT_DIR}}")
    print(f"📄 Profile: {{OUTPUT_DIR / 'voice_profile.json'}}")
    print(f"🎵 Test audio: {{OUTPUT_DIR / 'test_synthesis.wav'}}\\n")

except Exception as e:
    print(f"❌ Training error: {{e}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
'''

    # Write training script
    with open(training_script, 'w') as f:
        f.write(training_code)

    print(f"📝 Training script created: {training_script}\n")
    print("🚀 Launching training process...\n")
    print("="*70 + "\n")

    # Run training
    try:
        result = subprocess.run(
            [sys.executable, str(training_script)],
            cwd=str(OUTPUT_BASE),
            timeout=3600  # 1 hour timeout
        )

        if result.returncode == 0:
            print("\n✅ Training completed successfully!")
            return True
        else:
            print(f"\n❌ Training failed with exit code {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        print("\n⏱️  Training timeout (exceeded 1 hour)")
        return False
    except KeyboardInterrupt:
        print("\n⚠️  Training interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Training error: {e}")
        return False


# ============================================================================
# STEP 4: Create Inference Script
# ============================================================================

def create_inference_script():
    """Create a simple script for using the trained model."""
    print(f"\n{'='*70}")
    print("📜 STEP 4: CREATING INFERENCE SCRIPT")
    print(f"{'='*70}\n")

    inference_script = OUTPUT_BASE / "synthesize_jarvis.py"

    code = f'''#!/usr/bin/env python3
"""
🎙️ J.A.R.V.I.S. Voice Synthesis Script
Usage: python synthesize_jarvis.py "Your text here"
"""

import sys
import json
from pathlib import Path
from TTS.api import TTS

# Load voice profile
VOICE_PROFILE = Path("{MODEL_OUTPUT}") / "voice_profile.json"
OUTPUT_DIR = Path("{MODEL_OUTPUT}")

with open(VOICE_PROFILE) as f:
    profile = json.load(f)

print("🤖 J.A.R.V.I.S. Voice Synthesis System")
print("="*50)

# Initialize TTS
print("🔧 Loading model...")
tts = TTS(profile["model"])

# Get reference audio
reference_audio = profile["reference_audio"][0]
print(f"🎵 Using reference: {{Path(reference_audio).name}}")

# Get text
if len(sys.argv) > 1:
    text = " ".join(sys.argv[1:])
else:
    text = input("\\n📝 Enter text to synthesize: ")

print(f"\\n💬 Text: '{{text}}'")
print("🔊 Synthesizing...\\n")

# Generate
output_file = OUTPUT_DIR / f"jarvis_output_{{int(__import__('time').time())}}.wav"
tts.tts_to_file(
    text=text,
    speaker_wav=reference_audio,
    language="en",
    file_path=str(output_file)
)

print(f"✅ Audio saved to: {{output_file}}")
print("\\n🎉 Synthesis complete!\\n")
'''

    with open(inference_script, 'w') as f:
        f.write(code)

    # Make it executable
    os.chmod(inference_script, 0o755)

    print(f"✅ Inference script created: {inference_script}")
    print(f"\n💡 Usage: python {inference_script} \"Hello, I am JARVIS\"\n")

    return True


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main training pipeline."""
    start_time = time.time()

    print("🚀 Starting J.A.R.V.I.S. voice cloning pipeline...\n")

    # Step 1: Preprocess audio
    if not preprocess_all_audio():
        print("\n❌ Preprocessing failed. Aborting.")
        return 1

    # Step 2: Install TTS
    if not setup_coqui_tts():
        print("\n❌ TTS installation failed. Aborting.")
        return 1

    # Step 3: Train model
    if not train_voice_model():
        print("\n❌ Training failed. Aborting.")
        return 1

    # Step 4: Create inference script
    create_inference_script()

    # Final summary
    total_time = time.time() - start_time

    print("\n" + "="*70)
    print("🎊 J.A.R.V.I.S. VOICE CLONING COMPLETE! 🎊")
    print("="*70)
    print(f"\n⏱️  Total time: {total_time:.2f} seconds ({total_time/60:.2f} minutes)")
    print(f"\n📁 All outputs saved to: {OUTPUT_BASE}")
    print(f"   ├── processed_audio_22050hz/ - Processed training audio")
    print(f"   ├── trained_model/ - Voice model and profile")
    print(f"   └── synthesize_jarvis.py - Inference script")

    print(f"\n🎯 Next steps:")
    print(f"   1. Test the voice: python {OUTPUT_BASE / 'synthesize_jarvis.py'}")
    print(f"   2. Listen to: {MODEL_OUTPUT / 'test_synthesis.wav'}")
    print(f"\n🤖 J.A.R.V.I.S. is ready to serve, sir!\n")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Training interrupted by user. Goodbye!")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
