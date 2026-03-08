#!/usr/bin/env python3
"""
iMCP HTTP Bridge — Exposes the iMCP stdio server over HTTP.

Run this on the MacBook where iMCP is installed, then expose via
Cloudflare tunnel so the JARVIS backend on Railway can call it.

Usage:
    python3 imcp_bridge.py                          # default port 8787
    python3 imcp_bridge.py --port 9090              # custom port
    IMCP_BRIDGE_KEY=mysecret python3 imcp_bridge.py # with auth

Cloudflare tunnel:
    cloudflared tunnel route dns jarvis imcp.malibupoint.dev
    cloudflared tunnel --config ~/.cloudflared/config.yml run jarvis

Dependencies (install once):
    pip3 install uvicorn fastapi
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("imcp-bridge")

IMCP_COMMAND = "/Applications/iMCP.app/Contents/MacOS/imcp-server"
BRIDGE_KEY = os.environ.get("IMCP_BRIDGE_KEY", "")


# ── MCP Stdio Client (embedded, no external deps) ───────────────────────

class IMCPProcess:
    """Manages the iMCP stdio subprocess."""

    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self):
        if self._process is not None:
            return

        self._process = await asyncio.create_subprocess_exec(
            IMCP_COMMAND,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("iMCP process started: pid=%s", self._process.pid)

        self._reader_task = asyncio.create_task(self._read_loop())

        # MCP handshake
        result = await self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "jarvis-bridge", "version": "1.0.0"},
        })
        logger.info("iMCP initialized: %s", str(result)[:200])
        await self._notify("notifications/initialized", {})

    async def stop(self):
        if self._process is None:
            return
        if self._reader_task:
            self._reader_task.cancel()
        if self._process.stdin:
            self._process.stdin.close()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=5)
        except asyncio.TimeoutError:
            self._process.kill()
        self._process = None
        logger.info("iMCP process stopped")

    async def list_tools(self) -> list[dict]:
        result = await self._request("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: dict) -> Any:
        result = await self._request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        content = result.get("content", [])
        if not content:
            return result
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "image":
                    texts.append(f"[Image: {block.get('mimeType', 'image')}]")
                else:
                    texts.append(json.dumps(block, default=str))
            else:
                texts.append(str(block))
        combined = "\n".join(texts)
        if combined.strip().startswith(("{", "[")):
            try:
                return json.loads(combined)
            except json.JSONDecodeError:
                pass
        return combined

    async def _request(self, method: str, params: dict) -> dict:
        async with self._lock:
            if not self._process or not self._process.stdin:
                raise ConnectionError("iMCP not started")
            self._request_id += 1
            rid = self._request_id
            msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self._pending[rid] = fut
            self._process.stdin.write((json.dumps(msg) + "\n").encode())
            await self._process.stdin.drain()
            try:
                return await asyncio.wait_for(fut, timeout=30.0)
            except asyncio.TimeoutError:
                self._pending.pop(rid, None)
                raise

    async def _notify(self, method: str, params: dict):
        if not self._process or not self._process.stdin:
            return
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        self._process.stdin.write((json.dumps(msg) + "\n").encode())
        await self._process.stdin.drain()

    async def _read_loop(self):
        assert self._process and self._process.stdout
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                text = line.decode().strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    continue
                mid = msg.get("id")
                if mid is not None and mid in self._pending:
                    fut = self._pending.pop(mid)
                    if not fut.done():
                        if "error" in msg:
                            fut.set_exception(RuntimeError(f"MCP error: {msg['error']}"))
                        else:
                            fut.set_result(msg.get("result", {}))
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Reader loop error")


# ── FastAPI HTTP Bridge ──────────────────────────────────────────────────

imcp = IMCPProcess()


def create_app():
    from fastapi import FastAPI, HTTPException, Header
    from fastapi.responses import JSONResponse

    app = FastAPI(title="iMCP Bridge", docs_url=None, redoc_url=None)

    def _check_auth(authorization: str | None = Header(None)):
        if BRIDGE_KEY:
            expected = f"Bearer {BRIDGE_KEY}"
            if not authorization or authorization != expected:
                raise HTTPException(status_code=403, detail="Unauthorized")

    @app.on_event("startup")
    async def startup():
        await imcp.start()

    @app.on_event("shutdown")
    async def shutdown():
        await imcp.stop()

    @app.get("/health")
    async def health():
        return {"status": "ok", "imcp": imcp._process is not None}

    @app.get("/tools")
    async def list_tools(authorization: str | None = Header(None)):
        _check_auth(authorization)
        tools = await imcp.list_tools()
        return {"tools": tools}

    @app.post("/tools/{tool_name}")
    async def call_tool(
        tool_name: str,
        body: dict = {},
        authorization: str | None = Header(None),
    ):
        _check_auth(authorization)
        try:
            result = await imcp.call_tool(tool_name, body.get("arguments", {}))
            return {"result": result}
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"error": str(exc)},
            )

    return app


# ── Entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="iMCP HTTP Bridge")
    parser.add_argument("--port", type=int, default=8787, help="Port (default: 8787)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    args = parser.parse_args()

    import uvicorn
    logger.info("Starting iMCP bridge on %s:%d", args.host, args.port)
    if BRIDGE_KEY:
        logger.info("Authentication enabled (IMCP_BRIDGE_KEY set)")
    else:
        logger.warning("No IMCP_BRIDGE_KEY set — bridge is open (use Cloudflare tunnel auth)")

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
