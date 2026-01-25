#!/usr/bin/env python3
"""
🎙️ JARVIS Voice Server - Keep model loaded for fast synthesis
Runs in background, keeps model in memory for instant responses
"""

import os
import json
import socket
import tempfile
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
from scipy import signal
import soundfile as sf
import torch
import noisereduce as nr

os.environ['COQUI_TOS_AGREED'] = '1'
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'  # Enable CPU fallback for unsupported MPS ops
from TTS.api import TTS

# Paths
VOICE_PROFILE = Path(__file__).parent / "trained_model_hq" / "voice_profile_hq.json"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Server config
SOCKET_PATH = "/tmp/jarvis_voice_server.sock"
TARGET_SAMPLE_RATE = 44100

class JarvisVoiceServer:
    def __init__(self):
        print("🎙️  JARVIS Voice Server - High Quality")
        print("="*70)

        # Load voice profile
        with open(VOICE_PROFILE) as f:
            self.profile = json.load(f)

        self.reference_audio = self.profile["reference_audio"][0]

        # Use CPU for stability (MPS support in TTS is incomplete)
        self.device = "cpu"

        # Load model ONCE (this is the slow part)
        print("🔧 Loading XTTS-v2 model into memory...")
        print("   (This takes ~10-20 seconds, but only happens once)")
        self.tts = TTS(self.profile["model"], progress_bar=False)

        print(f"✅ Model loaded and ready!")
        print(f"🎵 Reference: {Path(self.reference_audio).name}")
        print("="*70)
        print("⚡ Server ready - subsequent requests will be FAST")
        print(f"🔌 Listening on: {SOCKET_PATH}")
        print("="*70)
        print()

    def gentle_noise_removal(self, audio, sr):
        """
        Gentle noise removal - preserves voice quality while reducing static.
        Same as the ultimate version that user liked.
        """
        audio_clean = nr.reduce_noise(
            y=audio,
            sr=sr,
            stationary=True,
            prop_decrease=0.75,  # Gentle reduction
        )
        return audio_clean

    def add_clarity_boost(self, audio, sr):
        """Add high-frequency clarity boost."""
        freq = 3500
        q = 1.5
        gain_db = 2

        w0 = freq / (sr / 2)
        A = 10 ** (gain_db / 40)
        alpha = np.sin(2 * np.pi * w0 / sr) / (2 * q)

        b0 = 1 + alpha * A
        b1 = -2 * np.cos(2 * np.pi * w0 / sr)
        b2 = 1 - alpha * A
        a0 = 1 + alpha / A
        a1 = -2 * np.cos(2 * np.pi * w0 / sr)
        a2 = 1 - alpha / A

        b = np.array([b0, b1, b2]) / a0
        a = np.array([a0, a1, a2]) / a0

        return signal.filtfilt(b, a, audio)

    def normalize_audio(self, audio):
        """Normalize audio to -1dB peak."""
        peak = np.abs(audio).max()
        if peak > 0:
            target_peak = 0.891
            audio = audio * (target_peak / peak)
        return audio

    def synthesize(self, text):
        """Synthesize audio (fast - model already loaded, GPU accelerated)."""
        import time
        start_time = time.time()

        # Generate audio (with GPU if available)
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            temp_file = tmp.name

        # Use GPU for synthesis if available
        # Note: TTS library doesn't fully support MPS yet, so we use CPU for now
        # but keep preprocessing on GPU where possible
        self.tts.tts_to_file(
            text=text,
            speaker_wav=str(self.reference_audio),
            language="en",
            file_path=temp_file
        )

        # Load and process
        audio, sr_original = sf.read(temp_file)
        os.unlink(temp_file)

        # Resample to 44.1kHz
        if sr_original != TARGET_SAMPLE_RATE:
            gcd = np.gcd(TARGET_SAMPLE_RATE, sr_original)
            up = TARGET_SAMPLE_RATE // gcd
            down = sr_original // gcd
            audio = resample_poly(audio, up, down)
            sr = TARGET_SAMPLE_RATE
        else:
            sr = sr_original

        # Add clarity boost (same as the favorite version - NO noise reduction!)
        audio_clear = self.add_clarity_boost(audio, sr)
        audio_clear = self.normalize_audio(audio_clear)

        # Save output
        output_file = OUTPUT_DIR / f"jarvis_{int(time.time())}.wav"
        sf.write(output_file, audio_clear, sr, subtype='PCM_16')

        elapsed = time.time() - start_time
        duration = len(audio_clear) / sr

        return output_file, duration, elapsed

    def run(self):
        """Run the server loop."""
        # Remove old socket if exists
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)

        # Create Unix socket server
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        server.listen(1)

        print("🎧 Waiting for synthesis requests...\n")

        try:
            while True:
                conn, _ = server.accept()
                try:
                    # Receive text (max 4KB)
                    text = conn.recv(4096).decode('utf-8')
                    if not text:
                        continue

                    print(f"📝 Request: '{text}'", flush=True)
                    print("🔊 Synthesizing...", end=" ", flush=True)

                    # Synthesize
                    try:
                        output_file, duration, elapsed = self.synthesize(text)
                    except Exception as synth_error:
                        import traceback
                        print(f"\n❌ Synthesis error: {synth_error}", flush=True)
                        print(traceback.format_exc(), flush=True)
                        conn.sendall(b"ERROR")
                        conn.close()
                        continue

                    print(f"✅ Done in {elapsed:.1f}s (audio: {duration:.1f}s)", flush=True)
                    print(f"   💾 {output_file.name}\n", flush=True)

                    # Send back the file path
                    conn.sendall(str(output_file).encode('utf-8'))

                except Exception as e:
                    import traceback
                    print(f"❌ Connection error: {e}\n", flush=True)
                    print(traceback.format_exc(), flush=True)
                    try:
                        conn.sendall(b"ERROR")
                    except:
                        pass
                finally:
                    conn.close()

        except KeyboardInterrupt:
            print("\n\n🛑 Server shutting down...")
        finally:
            server.close()
            if os.path.exists(SOCKET_PATH):
                os.unlink(SOCKET_PATH)

if __name__ == "__main__":
    server = JarvisVoiceServer()
    server.run()
