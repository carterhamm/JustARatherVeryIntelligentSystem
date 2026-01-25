# 🎙️ JARVIS Voice Synthesis

High-quality JARVIS voice synthesis using Coqui XTTS-v2.

## Quick Start

```bash
# Synthesize speech (auto-starts server on first run)
./jarvis "Your text here"
```

Output saved to: `output/jarvis_*.wav`

**First run**: Takes ~20-30 seconds (starts server + loads model)
**Subsequent runs**: Takes ~10-15 seconds (model already loaded) ⚡

## Features

- ✅ **CD Quality**: 16-bit / 44.1 kHz output
- ✅ **Crystal Clear**: Clarity boost removes muffled sound
- ✅ **Fast**: Background server keeps model loaded
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

## Server Management

The voice server runs in the background and keeps the model loaded for fast synthesis.

```bash
# Check server status
./jarvis_ctl status

# Manually start server (optional - auto-starts on first ./jarvis call)
./jarvis_ctl start

# Stop server (frees ~2GB memory)
./jarvis_ctl stop

# Restart server
./jarvis_ctl restart

# View server logs
./jarvis_ctl logs
```

**Note**: Server auto-starts when you run `./jarvis` if not already running.

## Files

```
jarvis_voice_training/
├── jarvis                          # Main launcher (uses fast server)
├── jarvis_ctl                      # Server control (start/stop/status)
├── jarvis_client.py                # Client (sends text to server)
├── jarvis_server.py                # Background server (keeps model loaded)
├── synthesize_jarvis_final.py      # Legacy direct synthesis
├── train_xtts_hq.py                # Training script
├── trained_model_hq/
│   ├── voice_profile_hq.json      # Voice configuration
│   └── test_synthesis_hq.wav      # Test sample
├── output/                         # Generated audio files
└── jarvis_venv/                    # Python environment
```

## Performance

### Speed Comparison

| Mode | First Run | Subsequent Runs |
|------|-----------|-----------------|
| **Old (no server)** | ~60 seconds | ~60 seconds |
| **New (with server)** | ~20-30 seconds | ~10-15 seconds ⚡ |

The background server keeps the XTTS-v2 model loaded in memory (~2GB RAM), reducing wait time by **~75%** on subsequent requests.

**Why still 10-15s?** The XTTS-v2 model synthesis itself takes ~10s on CPU. For even faster speeds, GPU acceleration would be needed (not currently configured).

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

### Server Architecture
- **Server**: Loads model once, listens on Unix socket
- **Client**: Sends text via socket, receives audio path
- **Communication**: Fast Unix domain sockets (no network overhead)
- **Memory**: ~2GB while server is running

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
