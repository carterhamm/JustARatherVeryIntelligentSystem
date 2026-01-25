#!/usr/bin/env python3
"""
🎙️ JARVIS Voice Client - Fast synthesis via server
"""

import sys
import socket
import subprocess
import time
import os
from pathlib import Path

SOCKET_PATH = "/tmp/jarvis_voice_server.sock"
SERVER_SCRIPT = Path(__file__).parent / "jarvis_server.py"
VENV_PYTHON = Path(__file__).parent / "jarvis_venv" / "bin" / "python3"

def is_server_running():
    """Check if server is running."""
    return os.path.exists(SOCKET_PATH)

def start_server():
    """Start the server in background."""
    print("🚀 Starting JARVIS voice server...")
    print("   (This will take ~10-20 seconds on first start)")
    print()

    # Start server in background, log to file
    log_file = open('/tmp/jarvis_server.log', 'w')
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'  # Force unbuffered output
    subprocess.Popen(
        [str(VENV_PYTHON), str(SERVER_SCRIPT)],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env
    )

    # Wait for server to be ready (socket file appears)
    print("⏳ Waiting for server to load model...", end=" ", flush=True)
    max_wait = 40  # seconds (increased for model loading)
    waited = 0
    while not os.path.exists(SOCKET_PATH) and waited < max_wait:
        time.sleep(0.5)
        waited += 0.5
        if waited % 2 == 0:
            print(".", end="", flush=True)

    if not os.path.exists(SOCKET_PATH):
        print("\n❌ Server failed to start!")
        print("Check logs: tail /tmp/jarvis_server.log")
        sys.exit(1)

    print(" ✅")
    print("🎉 Server ready!\n")

def synthesize(text):
    """Send text to server for synthesis."""
    try:
        # Connect to server
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SOCKET_PATH)

        # Send text
        client.sendall(text.encode('utf-8'))

        # Receive output file path
        response = client.recv(4096).decode('utf-8')
        client.close()

        if response == "ERROR":
            print("❌ Synthesis error!")
            return None

        return response

    except Exception as e:
        print(f"❌ Connection error: {e}")
        return None

def main():
    # Get text
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        print("Usage: ./jarvis \"Your text here\"")
        sys.exit(1)

    # Check if server is running, start if needed
    if not is_server_running():
        start_server()
        # Give it a moment to fully initialize
        time.sleep(1)

    # Synthesize
    print(f"💬 Text: '{text}'")
    print("🔊 Synthesizing...", end=" ", flush=True)

    start = time.time()
    output_file = synthesize(text)
    elapsed = time.time() - start

    if output_file:
        print(f"✅ Done in {elapsed:.1f}s")
        print(f"📁 {Path(output_file).name}")
        print()

        # Auto-play on macOS
        if sys.platform == 'darwin':
            subprocess.run(['afplay', output_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print("❌ Failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
