"""Local JARVIS TTS integration via Coqui XTTS-v2 voice server.

Connects to the local JARVIS voice server daemon that runs XTTS-v2 with
a trained JARVIS voice profile. Communication is via Unix domain socket.

The server must be started separately:
  cd /path/to/jarvis_voice_training && ./jarvis_ctl start
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.tts.local")

SOCKET_PATH = "/tmp/jarvis_voice_server.sock"


class JarvisTTSClient:
    """Client for the local JARVIS voice synthesis server."""

    def __init__(self, voice_server_dir: str = "") -> None:
        self._voice_dir = Path(voice_server_dir) if voice_server_dir else None
        self._server_script = (
            self._voice_dir / "jarvis_server.py" if self._voice_dir else None
        )
        self._venv_python = (
            self._voice_dir / "jarvis_venv" / "bin" / "python3"
            if self._voice_dir
            else None
        )

    def _is_server_running(self) -> bool:
        """Check if the JARVIS voice server is running."""
        return os.path.exists(SOCKET_PATH)

    async def _start_server(self) -> bool:
        """Attempt to start the voice server in background."""
        if not self._server_script or not self._server_script.exists():
            logger.warning("JARVIS voice server script not found at %s", self._server_script)
            return False
        if not self._venv_python or not self._venv_python.exists():
            logger.warning("JARVIS voice venv not found at %s", self._venv_python)
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

        # Wait for server to start (up to 45s for model loading)
        for _ in range(90):
            if os.path.exists(SOCKET_PATH):
                logger.info("JARVIS voice server started successfully")
                return True
            await asyncio.sleep(0.5)

        logger.error("JARVIS voice server failed to start within timeout")
        return False

    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio bytes (WAV format).

        Connects to the local JARVIS voice server, sends text, receives
        the path to the generated WAV file, and returns its contents.
        """
        if not self._is_server_running():
            started = await self._start_server()
            if not started:
                raise RuntimeError(
                    "JARVIS voice server is not running and could not be started. "
                    "Run: cd jarvis_voice_training && ./jarvis_ctl start"
                )

        # Send text to server via Unix socket
        loop = asyncio.get_event_loop()
        wav_path = await loop.run_in_executor(None, self._synthesize_sync, text)

        if not wav_path or wav_path == "ERROR":
            raise RuntimeError("JARVIS voice synthesis failed")

        # Read the WAV file
        wav_file = Path(wav_path)
        if not wav_file.exists():
            raise RuntimeError(f"Synthesized audio file not found: {wav_path}")

        audio_bytes = wav_file.read_bytes()
        logger.info("JARVIS TTS: synthesized %d bytes for text: '%s...'", len(audio_bytes), text[:50])
        return audio_bytes

    def _synthesize_sync(self, text: str) -> Optional[str]:
        """Blocking synthesis call via Unix socket."""
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(120.0)  # 2 min timeout for synthesis
            client.connect(SOCKET_PATH)
            client.sendall(text.encode("utf-8"))
            response = client.recv(4096).decode("utf-8")
            client.close()
            return response
        except Exception as exc:
            logger.error("JARVIS voice server connection error: %s", exc)
            return None

    async def is_available(self) -> bool:
        """Check if the JARVIS voice server is running and responsive."""
        if not self._is_server_running():
            return False
        try:
            # Try a quick connection test
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._ping)
            return result
        except Exception:
            return False

    def _ping(self) -> bool:
        """Quick connectivity check."""
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(2.0)
            client.connect(SOCKET_PATH)
            client.close()
            return True
        except Exception:
            return False
