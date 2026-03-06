"""JARVIS TTS integration — local (Unix socket) or remote (HTTP/Modal).

Local mode:
  Connects to the JARVIS voice server daemon running XTTS-v2 locally.
  Server must be started: cd jarvis_voice_training && ./jarvis_ctl start

Remote mode:
  Calls a remote JARVIS Voice API (deployed on Modal) over HTTPS.
  Set JARVIS_VOICE_URL and JARVIS_VOICE_API_KEY in environment.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.tts")

SOCKET_PATH = "/tmp/jarvis_voice_server.sock"


class JarvisTTSClient:
    """Client for JARVIS voice synthesis — supports local and remote backends."""

    def __init__(
        self,
        voice_server_dir: str = "",
        remote_url: str = "",
        api_key: str = "",
    ) -> None:
        # Remote (HTTP) mode
        self._remote_url = remote_url.rstrip("/") if remote_url else ""
        self._api_key = api_key
        self._is_remote = bool(self._remote_url)

        # Local (Unix socket) mode
        self._voice_dir = Path(voice_server_dir) if voice_server_dir else None
        self._server_script = (
            self._voice_dir / "jarvis_server.py" if self._voice_dir else None
        )
        self._venv_python = (
            self._voice_dir / "jarvis_venv" / "bin" / "python3"
            if self._voice_dir
            else None
        )

        mode = "remote" if self._is_remote else "local"
        target = self._remote_url or str(self._voice_dir or "none")
        logger.info("JARVIS TTS client initialized (%s): %s", mode, target)

    # ── Public interface ──────────────────────────────────────────────────────

    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio bytes (WAV format)."""
        if self._is_remote:
            return await self._synthesize_remote(text)
        return await self._synthesize_local(text)

    async def is_available(self) -> bool:
        """Check if the JARVIS voice backend is reachable."""
        if self._is_remote:
            return await self._health_check_remote()
        return await self._health_check_local()

    # ── Remote (HTTP) mode ────────────────────────────────────────────────────

    async def _synthesize_remote(self, text: str) -> bytes:
        """Call the remote JARVIS Voice API."""
        import httpx

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # Long timeout for cold starts + synthesis
        timeout = httpx.Timeout(connect=120.0, read=300.0, write=30.0, pool=30.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self._remote_url}/synthesize",
                json={"text": text},
                headers=headers,
            )
            resp.raise_for_status()

        audio_bytes = resp.content
        logger.info(
            "JARVIS TTS (remote): synthesized %d bytes for '%s...'",
            len(audio_bytes),
            text[:50],
        )
        return audio_bytes

    async def _health_check_remote(self) -> bool:
        """Quick health check against the remote endpoint."""
        import httpx

        try:
            timeout = httpx.Timeout(connect=10.0, read=10.0, write=5.0, pool=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(f"{self._remote_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    # ── Local (Unix socket) mode ──────────────────────────────────────────────

    def _is_server_running(self) -> bool:
        return os.path.exists(SOCKET_PATH)

    async def _start_server(self) -> bool:
        if not self._server_script or not self._server_script.exists():
            logger.warning(
                "JARVIS voice server script not found at %s", self._server_script
            )
            return False
        if not self._venv_python or not self._venv_python.exists():
            logger.warning(
                "JARVIS voice venv not found at %s", self._venv_python
            )
            return False

        logger.info("Starting JARVIS voice server...")
        log_file = open("/tmp/jarvis_server.log", "w")
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["COQUI_TOS_AGREED"] = "1"

        subprocess.Popen(
            [str(self._venv_python), str(self._server_script)],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )

        for _ in range(90):
            if os.path.exists(SOCKET_PATH):
                logger.info("JARVIS voice server started successfully")
                return True
            await asyncio.sleep(0.5)

        logger.error("JARVIS voice server failed to start within timeout")
        return False

    async def _synthesize_local(self, text: str) -> bytes:
        """Synthesize via the local Unix socket voice server."""
        if not self._is_server_running():
            started = await self._start_server()
            if not started:
                raise RuntimeError(
                    "JARVIS voice server is not running and could not be started. "
                    "Run: cd jarvis_voice_training && ./jarvis_ctl start"
                )

        loop = asyncio.get_event_loop()
        wav_path = await loop.run_in_executor(None, self._synthesize_sync, text)

        if not wav_path or wav_path == "ERROR":
            raise RuntimeError("JARVIS voice synthesis failed")

        wav_file = Path(wav_path)
        if not wav_file.exists():
            raise RuntimeError(f"Synthesized audio file not found: {wav_path}")

        audio_bytes = wav_file.read_bytes()
        logger.info(
            "JARVIS TTS (local): synthesized %d bytes for '%s...'",
            len(audio_bytes),
            text[:50],
        )
        return audio_bytes

    def _synthesize_sync(self, text: str) -> Optional[str]:
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(120.0)
            client.connect(SOCKET_PATH)
            client.sendall(text.encode("utf-8"))
            response = client.recv(4096).decode("utf-8")
            client.close()
            return response
        except Exception as exc:
            logger.error("JARVIS voice server connection error: %s", exc)
            return None

    async def _health_check_local(self) -> bool:
        if not self._is_server_running():
            return False
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._ping)
        except Exception:
            return False

    def _ping(self) -> bool:
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(2.0)
            client.connect(SOCKET_PATH)
            client.close()
            return True
        except Exception:
            return False
