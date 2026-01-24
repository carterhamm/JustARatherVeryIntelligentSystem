#!/bin/bash

# 🎙️ Wait for JARVIS Training to Complete 🎙️

LOG_FILE="/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_training_output.log"

echo "🎙️  Waiting for JARVIS training to complete..."
echo "========================================================================"
echo ""

# Check if training is running
if ! pgrep -f "jarvis_voice_trainer.py" > /dev/null && ! pgrep -f "pip install TTS" > /dev/null; then
    echo "⚠️  Training doesn't appear to be running."
    echo "   Start it with: nohup bash run_jarvis_training.sh &"
    exit 1
fi

# Monitor until complete
while true; do
    clear
    echo "🎙️  J.A.R.V.I.S. TRAINING IN PROGRESS..."
    echo "========================================================================"
    echo ""

    # Check if still installing
    if pgrep -f "pip install TTS" > /dev/null; then
        echo "📦 Status: Installing Coqui TTS dependencies..."
        echo "⏳ This takes 5-10 minutes. Please wait..."
        echo ""
        echo "💡 You can safely close this and check later with:"
        echo "   ./check_training_status.sh"
    elif pgrep -f "jarvis_voice_trainer.py" > /dev/null; then
        echo "🎓 Status: Training voice model..."
        echo ""
        # Show last 20 lines of log
        tail -20 "$LOG_FILE" 2>/dev/null | grep -E "^(🎵|✅|📊|🔧|⏱|🎓|💾|🧪|📈|🎉|\[)" || echo "Processing..."
    else
        echo "✅ TRAINING COMPLETE!"
        echo ""
        tail -30 "$LOG_FILE" 2>/dev/null
        break
    fi

    echo ""
    echo "========================================================================"
    echo "Press Ctrl+C to exit this monitor (training will continue in background)"
    echo "Updated: $(date '+%H:%M:%S')"

    sleep 10
done

echo ""
echo "🎉 Training finished! Check output with:"
echo "   ./check_training_status.sh"
