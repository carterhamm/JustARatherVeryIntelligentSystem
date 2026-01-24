#!/bin/bash

# 🎙️ J.A.R.V.I.S. Voice Training Launcher 🎙️
# Handles virtual environment setup automatically

set -e  # Exit on error

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$SCRIPT_DIR/jarvis_venv"
LOG_FILE="$SCRIPT_DIR/jarvis_training_output.log"

echo "🤖 J.A.R.V.I.S. Voice Training Launcher 🤖"
echo "========================================================================"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "✅ Virtual environment created!"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "📥 Upgrading pip..."
python -m pip install --upgrade pip > /dev/null 2>&1

# Install Coqui TTS if not already installed
if ! python -c "import TTS" 2>/dev/null; then
    echo "📦 Installing Coqui TTS (this may take a few minutes)..."
    pip install TTS > /dev/null 2>&1
    echo "✅ Coqui TTS installed!"
else
    echo "✅ Coqui TTS already installed!"
fi

# Install additional dependencies
echo "📦 Installing audio processing tools..."
pip install numpy scipy soundfile librosa > /dev/null 2>&1

echo ""
echo "========================================================================"
echo "🚀 STARTING TRAINING"
echo "========================================================================"
echo ""

# Run training script
python "$SCRIPT_DIR/jarvis_voice_trainer.py" 2>&1 | tee "$LOG_FILE"

# Deactivate virtual environment
deactivate

echo ""
echo "✅ Training session complete!"
echo "📄 Full log saved to: $LOG_FILE"
