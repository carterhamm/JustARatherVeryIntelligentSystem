"""
JARVIS Voice — Modal Deployment
Serves XTTS-v2 voice synthesis with the trained JARVIS voice profile.
GPU-accelerated, scales to zero when idle, HTTPS + API key auth.

Setup:  modal run modal_jarvis_voice.py      # Upload ref audio + smoke test
Deploy: modal deploy modal_jarvis_voice.py
"""

import os

import modal

MINUTES = 60

app = modal.App("jarvis-voice")

# ── Container image with Coqui TTS + CUDA ────────────────────────────────────
tts_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.1.0-runtime-ubuntu22.04", add_python="3.11"
    )
    .entrypoint([])
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install(
        "torch==2.1.0",
        "torchaudio==2.1.0",
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
    .pip_install(
        "TTS==0.22.0",
        "transformers==4.33.0",
        "numpy<2",
        "scipy",
        "soundfile",
        "noisereduce",
        "fastapi[standard]",
    )
    .env({"COQUI_TOS_AGREED": "1"})
)

# ── Persistent volumes ───────────────────────────────────────────────────────
ref_audio_vol = modal.Volume.from_name("jarvis-voice-ref", create_if_missing=True)
model_cache = modal.Volume.from_name("jarvis-voice-cache", create_if_missing=True)


# ── ASGI server ──────────────────────────────────────────────────────────────
@app.function(
    image=tts_image,
    gpu="L4",
    scaledown_window=10 * MINUTES,
    timeout=10 * MINUTES,
    volumes={
        "/ref_audio": ref_audio_vol,
        "/root/.cache": model_cache,
    },
    secrets=[modal.Secret.from_name("stark-protocol-key")],
)
@modal.asgi_app()
def serve():
    import io
    import tempfile
    import time

    import numpy as np
    import soundfile as sf
    import torch
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from scipy import signal
    from scipy.signal import resample_poly

    os.environ["COQUI_TOS_AGREED"] = "1"
    from TTS.api import TTS

    # ── Load reference audio ──────────────────────────────────────────────────
    ref_dir = "/ref_audio"
    ref_files = sorted(
        os.path.join(ref_dir, f)
        for f in os.listdir(ref_dir)
        if f.endswith(".wav")
    )
    if not ref_files:
        raise RuntimeError(
            "No reference audio in /ref_audio. Run: modal run modal_jarvis_voice.py"
        )
    print(f"Reference audio: {len(ref_files)} files")

    # ── Load XTTS-v2 model ────────────────────────────────────────────────────
    print("Loading XTTS-v2 model...")
    tts = TTS("xtts_v2", progress_bar=False)

    if torch.cuda.is_available():
        print(f"Moving model to CUDA ({torch.cuda.get_device_name(0)})...")
        tts.to("cuda")
        print("GPU acceleration enabled!")
    else:
        print("WARNING: CUDA not available, using CPU")

    print("JARVIS Voice server ready!")

    # ── Config ────────────────────────────────────────────────────────────────
    API_KEY = os.environ.get("STARK_API_KEY", "")
    TARGET_SR = 44100

    # ── Audio processing (V2 EQ chain) ────────────────────────────────────────
    def parametric_eq(audio, sr, freq, gain_db, q):
        w0 = freq / (sr / 2)
        A = 10 ** (gain_db / 40)
        alpha = np.sin(2 * np.pi * w0 / sr) / (2 * q)
        b0 = 1 + alpha * A
        b1 = -2 * np.cos(2 * np.pi * w0 / sr)
        b2 = 1 - alpha * A
        a0 = 1 + alpha / A
        a1 = b1
        a2 = 1 - alpha / A
        b = np.array([b0, b1, b2]) / a0
        a = np.array([1.0, a1 / a0, a2 / a0])
        return signal.filtfilt(b, a, audio)

    def apply_eq(audio, sr):
        """V2 EQ: warmth + body + clarity."""
        audio = parametric_eq(audio, sr, freq=180, gain_db=+5.0, q=0.8)
        audio = parametric_eq(audio, sr, freq=350, gain_db=+3.0, q=1.0)
        audio = parametric_eq(audio, sr, freq=1500, gain_db=-1.0, q=1.5)
        audio = parametric_eq(audio, sr, freq=3500, gain_db=+1.0, q=2.0)
        return audio

    def normalize(audio, target_peak=0.891):
        peak = np.abs(audio).max()
        if peak > 0:
            audio = audio * (target_peak / peak)
        return audio

    # ── FastAPI ───────────────────────────────────────────────────────────────
    api = FastAPI(title="JARVIS Voice")
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def check_auth(request: Request):
        if not API_KEY:
            return
        auth = request.headers.get("authorization", "")
        key = auth.removeprefix("Bearer ").strip() if auth else ""
        if key != API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")

    @api.get("/health")
    async def health():
        return {
            "status": "ok",
            "model": "xtts_v2",
            "gpu": torch.cuda.is_available(),
            "ref_files": len(ref_files),
        }

    @api.post("/synthesize")
    async def synthesize(request: Request):
        check_auth(request)
        body = await request.json()
        text = body.get("text", "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="No text provided")

        t0 = time.time()

        # Synthesize to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        tts.tts_to_file(
            text=text,
            speaker_wav=ref_files,
            language="en",
            file_path=tmp_path,
        )

        # Post-process
        audio, sr = sf.read(tmp_path)
        os.unlink(tmp_path)

        # Resample to 44.1kHz
        if sr != TARGET_SR:
            gcd = np.gcd(TARGET_SR, int(sr))
            audio = resample_poly(audio, TARGET_SR // gcd, int(sr) // gcd)

        # EQ + normalize
        audio = apply_eq(audio, TARGET_SR)
        audio = normalize(audio)

        # Encode to WAV bytes
        buf = io.BytesIO()
        sf.write(buf, audio, TARGET_SR, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()

        elapsed = time.time() - t0
        duration = len(audio) / TARGET_SR
        print(
            f"Synthesized '{text[:60]}' in {elapsed:.1f}s ({duration:.1f}s audio)"
        )

        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "X-Duration": str(round(duration, 2)),
                "X-Processing-Time": str(round(elapsed, 2)),
            },
        )

    return api


# ── Local entrypoint: upload ref audio + smoke test ──────────────────────────
@app.local_entrypoint()
def main():
    """Upload JARVIS reference audio files to Modal volume."""

    ref_dir = (
        "/Users/mr.stark/Downloads/"
        "J.A.R.V.I.S. Resources/J.A.R.V.I.S. Voice FIles/ElevenLabs-Upscaled3x"
    )
    ref_names = [
        "chunk_1.wav",
        "chunk_2.wav",
        "chunk_13.wav",
        "chunk_18.wav",
        "chunk_21.wav",
    ]

    vol = modal.Volume.from_name("jarvis-voice-ref")

    print("Uploading reference audio to Modal volume...")
    with vol.batch_upload() as batch:
        for name in ref_names:
            filepath = os.path.join(ref_dir, name)
            if os.path.exists(filepath):
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                print(f"  {name} ({size_mb:.1f} MB)")
                batch.put_file(filepath, f"/{name}")
            else:
                print(f"  WARNING: {name} not found at {filepath}")

    print("\nReference audio uploaded!")
    print("Deploy with: modal deploy modal_jarvis_voice.py")
