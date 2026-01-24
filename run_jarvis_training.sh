#!/bin/bash

# 🎙️ J.A.R.V.I.S. Voice Training Launcher 🎙️
# Handles virtual environment setup automatically

# REDIRECT ALL OUTPUT TO LOG FILE IMMEDIATELY
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_FILE="$SCRIPT_DIR/jarvis_training_full.log"

# Redirect stdout and stderr to log file
exec > "$LOG_FILE" 2>&1

set -e  # Exit on error

VENV_DIR="$SCRIPT_DIR/jarvis_venv"
TRAINING_LOG="$SCRIPT_DIR/jarvis_training_output.log"

echo "🤖 J.A.R.V.I.S. Voice Training Launcher 🤖"
echo "========================================================================"
echo "Started: $(date)"
echo ""

# Remove old venv if it exists with wrong Python version
if [ -d "$VENV_DIR" ]; then
    echo "🧹 Removing old virtual environment..."
    rm -rf "$VENV_DIR"
fi

# Create virtual environment with Python 3.11 (required for Coqui TTS)
echo "📦 Creating Python 3.11 virtual environment..."
python3.11 -m venv "$VENV_DIR"
echo "✅ Virtual environment created with Python 3.11!"

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "📥 Upgrading pip..."
python -m pip install --upgrade pip --quiet

# Install Coqui TTS if not already installed
if ! python -c "import TTS" 2>/dev/null; then
    echo "📦 Installing Coqui TTS with compatible dependencies (this may take a few minutes)..."
    # Install compatible versions for TTS
    pip install 'torch==2.1.0' 'torchaudio==2.1.0' 'transformers==4.33.0' --quiet
    pip install TTS --quiet
    echo "✅ Coqui TTS installed!"
else
    echo "✅ Coqui TTS already installed!"
fi

# Install additional dependencies
echo "📦 Installing audio processing tools..."
pip install numpy scipy soundfile librosa --quiet

echo ""
echo "========================================================================"
echo "🚀 STARTING TRAINING"
echo "========================================================================"
echo ""

# Run training script (use Python from venv)
"$VENV_DIR/bin/python" "$SCRIPT_DIR/jarvis_voice_trainer.py" > "$TRAINING_LOG" 2>&1

# Deactivate virtual environment
deactivate

echo ""
echo "✅ Training session complete!"
echo "📄 Training log: $TRAINING_LOG"
echo "📄 Full log: $LOG_FILE"
echo "Completed: $(date)"
