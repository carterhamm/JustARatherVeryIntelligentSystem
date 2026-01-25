# 🎙️ JARVIS Voice Synthesis

High-quality JARVIS voice synthesis using Coqui XTTS-v2.

## Quick Start

```bash
# Synthesize speech
./jarvis "Your text here"
```

Output saved to: `output/jarvis_*.wav`

## Features

- ✅ **CD Quality**: 16-bit / 44.1 kHz output
- ✅ **Crystal Clear**: Clarity boost removes muffled sound
- ✅ **Original Voice**: Uses 144kHz reference audio (no quality loss)

## Audio Quality

| Specification | Value |
|---------------|-------|
| Sample Rate | 44,100 Hz (CD quality) |
| Bit Depth | 16-bit PCM |
| Bitrate | ~705 kb/s |
| Format | WAV (lossless) |

## Usage Examples

```bash
# Simple text
./jarvis "JARVIS online"

# Natural speech
./jarvis "Good evening, sir. JARVIS ready."

# Longer text
./jarvis "All systems operational. Standing by for further instructions."
```

## Files

```
jarvis_voice_training/
├── jarvis                          # Main launcher script
├── synthesize_jarvis_final.py      # Synthesis engine
├── train_xtts_hq.py                # Training script
├── trained_model_hq/
│   ├── voice_profile_hq.json      # Voice configuration
│   └── test_synthesis_hq.wav      # Test sample
├── output/                         # Generated audio files
└── jarvis_venv/                    # Python environment
```

## Technical Details

### Voice Training
- Model: XTTS-v2 (multi-lingual, multi-speaker)
- Reference Audio: 144kHz original JARVIS samples
- Training: Voice cloning approach (no fine-tuning needed)

### Audio Processing
1. Synthesis at native 24kHz
2. Upsample to 44.1kHz (CD quality)
3. Clarity boost (+2dB at 3.5kHz) - removes muffled sound
4. Normalize to -1dB peak

### Why 44.1kHz?
- Industry standard (CD quality)
- Better compatibility
- Professional output
- Preserves all voice detail

## Regenerate Test Sample

```bash
cd jarvis_voice_training
source jarvis_venv/bin/activate
python3 train_xtts_hq.py
```

## Requirements

- Python 3.11
- Virtual environment (included)
- Dependencies: TTS, scipy, soundfile

## Output Location

All generated files: `output/jarvis_*.wav`

Each file is timestamped for easy identification.

---

**Simple. Clean. High-quality JARVIS voice.** 🎙️
