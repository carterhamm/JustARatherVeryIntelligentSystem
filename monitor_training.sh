#!/bin/bash

# 🎙️ J.A.R.V.I.S. Training Monitor 🎙️

LOG_FILE="/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_training_output.log"
TRAINING_DIR="/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training"

echo "🎙️  J.A.R.V.I.S. Voice Training Monitor 🎙️"
echo "========================================================================"
echo ""

# Check if log exists
if [ ! -f "$LOG_FILE" ]; then
    echo "⚠️  Training log not found. Training may not have started yet."
    echo "   Looking for: $LOG_FILE"
    exit 1
fi

# Check if training is complete
if grep -q "J.A.R.V.I.S. VOICE CLONING COMPLETE" "$LOG_FILE" 2>/dev/null; then
    echo "🎉 TRAINING COMPLETE! 🎉"
    echo ""
    echo "📊 Final Results:"
    echo "----------------"
    tail -20 "$LOG_FILE"
    echo ""
    echo "📁 Outputs:"
    echo "   - Processed audio: $TRAINING_DIR/processed_audio_22050hz/"
    echo "   - Trained model: $TRAINING_DIR/trained_model/"
    echo "   - Test synthesis: $TRAINING_DIR/trained_model/test_synthesis.wav"
    echo ""
    echo "🎯 Test the voice:"
    echo "   python3 $TRAINING_DIR/synthesize_jarvis.py \"Hello, I am JARVIS\""
    echo ""
    exit 0
fi

# Check for errors
if grep -q "❌" "$LOG_FILE" 2>/dev/null; then
    echo "⚠️  Errors detected in training log"
    echo ""
fi

# Show live progress
echo "📊 Current Progress:"
echo "--------------------"
tail -30 "$LOG_FILE"
echo ""
echo "========================================================================"
echo "💡 Live monitoring: tail -f $LOG_FILE"
echo "========================================================================"
