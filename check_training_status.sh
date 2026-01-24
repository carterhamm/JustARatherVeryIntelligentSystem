#!/bin/bash

# 🎙️ Quick Training Status Check 🎙️

TRAINING_LOG="/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_training_full.log"
MODEL_DIR="/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/jarvis_voice_training/trained_model"
TEST_AUDIO="$MODEL_DIR/test_synthesis.wav"

clear
echo "🎙️  J.A.R.V.I.S. VOICE TRAINING STATUS 🎙️"
echo "========================================================================"
echo ""

# Check if training is running
if pgrep -f "run_jarvis_training.sh" > /dev/null || pgrep -f "jarvis_voice_trainer.py" > /dev/null; then
    echo "🔄 STATUS: TRAINING IN PROGRESS ⏳"
    echo ""

    # Show recent log lines
    if [ -f "$TRAINING_LOG" ]; then
        echo "📊 Latest Progress:"
        echo "-------------------"
        tail -25 "$TRAINING_LOG" | grep -E "^(🎵|✅|📊|🔧|⏱|🎓|💾|🧪|📈|🎉|\[)" || tail -25 "$TRAINING_LOG"
        echo ""

        # Check current step
        if grep -q "STEP 1" "$TRAINING_LOG" && ! grep -q "STEP 2" "$TRAINING_LOG"; then
            echo "📍 Current: Audio Preprocessing (Step 1/4)"
        elif grep -q "STEP 2" "$TRAINING_LOG" && ! grep -q "STEP 3" "$TRAINING_LOG"; then
            echo "📍 Current: Setting up Coqui TTS (Step 2/4)"
        elif grep -q "STEP 3" "$TRAINING_LOG" && ! grep -q "STEP 4" "$TRAINING_LOG"; then
            echo "📍 Current: Training Voice Model (Step 3/4)"
        elif grep -q "STEP 4" "$TRAINING_LOG"; then
            echo "📍 Current: Finalizing (Step 4/4)"
        fi

        echo ""
        echo "💡 Monitor live: tail -f $TRAINING_LOG"
    else
        echo "⏳ Training is starting up..."
    fi

elif [ -f "$TEST_AUDIO" ]; then
    echo "✅ STATUS: TRAINING COMPLETE! 🎉"
    echo ""
    echo "📦 Model Location: $MODEL_DIR"
    echo "🎵 Test Audio: $TEST_AUDIO"
    echo ""
    echo "🎯 Try it out:"
    echo "   cd jarvis_voice_training"
    echo "   python3 synthesize_jarvis.py \"Hello sir, JARVIS online.\""
    echo ""

    # Show final stats
    if [ -f "$TRAINING_LOG" ]; then
        echo "📊 Training Summary:"
        echo "-------------------"
        grep -E "(Total time|Successfully processed|Audio duration)" "$TRAINING_LOG" | tail -5
    fi

elif [ -f "$TRAINING_LOG" ]; then
    if grep -q "❌" "$TRAINING_LOG"; then
        echo "❌ STATUS: TRAINING FAILED"
        echo ""
        echo "💥 Last errors:"
        echo "---------------"
        grep "❌" "$TRAINING_LOG" | tail -5
        echo ""
        echo "📄 Check full log: $TRAINING_LOG"
    else
        echo "⏸️  STATUS: TRAINING NOT RUNNING"
        echo ""
        echo "🚀 Start training: ./run_jarvis_training.sh &"
    fi
else
    echo "⏸️  STATUS: NOT STARTED"
    echo ""
    echo "🚀 Start training: ./run_jarvis_training.sh &"
fi

echo ""
echo "========================================================================"
echo "Updated: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================================================"
