"""
Stark Protocol — Modal Deployment
Serves Gemma 3 4B via vLLM with OpenAI-compatible API.
Scales to zero when idle. HTTPS + API key auth.

Deploy:  modal deploy modal_stark.py
Test:    modal run modal_stark.py
"""

import modal

# ── Container image with vLLM ──────────────────────────────────
vllm_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.12"
    )
    .entrypoint([])
    .uv_pip_install("vllm==0.13.0", "huggingface-hub==0.36.0")
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})
)

# ── Configuration ──────────────────────────────────────────────
MODEL_NAME = "unsloth/gemma-3-4b-it"
# Accept requests using any of these model names
SERVED_NAMES = [MODEL_NAME, "gemma-3-4b-it", "gemma-3-4b-it-abliterated-text", "google/gemma-3-4b-it"]
VLLM_PORT = 8000
MINUTES = 60

# ── Persistent volumes for model weight cache ─────────────────
hf_cache = modal.Volume.from_name("stark-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("stark-vllm-cache", create_if_missing=True)

app = modal.App("stark-protocol")


@app.function(
    image=vllm_image,
    gpu="L4",  # 24GB VRAM — plenty for Gemma 3 4B, cheapest reliable option
    scaledown_window=10 * MINUTES,  # scale to zero after 10 min idle
    timeout=10 * MINUTES,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/root/.cache/vllm": vllm_cache,
    },
    secrets=[modal.Secret.from_name("stark-protocol-key")],
)
@modal.concurrent(max_inputs=8)
@modal.web_server(port=VLLM_PORT, startup_timeout=10 * MINUTES)
def serve():
    import os
    import subprocess

    api_key = os.environ.get("STARK_API_KEY", "")

    cmd = [
        "vllm",
        "serve",
        MODEL_NAME,
        "--host",
        "0.0.0.0",
        "--port",
        str(VLLM_PORT),
        "--served-model-name",
        *SERVED_NAMES,
        "--max-model-len",
        "4096",
        "--enforce-eager",
        "--tensor-parallel-size",
        "1",
        "--dtype",
        "auto",
        "--uvicorn-log-level=info",
    ]

    if api_key:
        cmd += ["--api-key", api_key]

    print("Starting vLLM:", " ".join(cmd))
    subprocess.Popen(cmd)


@app.local_entrypoint()
async def test():
    """Quick smoke test — sends a chat completion request."""
    import json
    import os

    import aiohttp

    url = await serve.get_web_url.aio()
    api_key = os.environ.get("STARK_API_KEY", "")

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": "gemma-3-4b-it",
        "messages": [
            {"role": "user", "content": "Say hello in one sentence."},
        ],
        "stream": True,
        "max_tokens": 64,
    }

    print(f"Health check: {url}/health")
    async with aiohttp.ClientSession(base_url=url) as session:
        async with session.get("/health", timeout=aiohttp.ClientTimeout(total=300)) as resp:
            assert resp.status == 200, f"Health check failed: {resp.status}"
        print("Health OK. Sending test request...")

        async with session.post(
            "/v1/chat/completions", json=payload, headers=headers
        ) as resp:
            async for raw in resp.content:
                line = raw.decode().strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    chunk = json.loads(line[6:])
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    print(delta, end="", flush=True)
    print("\nDone.")
