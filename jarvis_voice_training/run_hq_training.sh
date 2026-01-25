#!/bin/bash
# High-Quality JARVIS Voice Training Launcher
# Uses original files without preprocessing

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$SCRIPT_DIR/jarvis_venv"

echo "🎙️  Starting high-quality JARVIS voice training..."
echo ""

# Check if venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please run ./run_jarvis_training.sh first to set up the environment"
    exit 1
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Run training
cd "$SCRIPT_DIR"
python3 train_xtts_hq.py

echo ""
echo "✅ Training complete!"
echo ""
