"""
Generic MCP (Model Context Protocol) stdio client.

Spawns an MCP server process and communicates via JSON-RPC over stdin/stdout.
Used to connect to iMCP and any other stdio-based MCP servers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger("jarvis.integrations.mcp_client")


class MCPStdioClient:
    """Async client that speaks MCP JSON-RPC over a child process's stdio."""

    def __init__(self, command: str, args: list[str] | None = None, timeout: float = 30.0):
        self._command = command
        self._args = args or []
        self._timeout = timeout
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._initialized = False

    # ── lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Spawn the MCP server process and perform the initialize handshake."""
        if self._process is not None:
            return

        self._process = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("MCP server started: pid=%s cmd=%s", self._process.pid, self._command)

        # Start background reader
        self._reader_task = asyncio.create_task(self._read_loop())

        # MCP initialize handshake
        init_result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "jarvis", "version": "1.0.0"},
        })
        logger.info("MCP initialized: %s", json.dumps(init_result, default=str)[:200])

        # Send initialized notification (no response expected)
        await self._send_notification("notifications/initialized", {})
        self._initialized = True

    async def stop(self) -> None:
        """Shut down the MCP server process."""
        if self._process is None:
            return

        # Cancel reader
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        # Close stdin to signal EOF
        if self._process.stdin:
            self._process.stdin.close()

        try:
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            self._process.kill()
            await self._process.wait()

        logger.info("MCP server stopped: pid=%s", self._process.pid)
        self._process = None
        self._initialized = False

        # Fail any pending requests
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("MCP server stopped"))
        self._pending.clear()

    async def __aenter__(self) -> MCPStdioClient:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    # ── public API ───────────────────────────────────────────────────────

    async def list_tools(self) -> list[dict[str, Any]]:
        """Call tools/list and return the list of tool definitions."""
        result = await self._send_request("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call a specific tool by name and return its result."""
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })
        # MCP tools return content as a list of content blocks
        content = result.get("content", [])
        if not content:
            return result

        # Combine text blocks
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

        # Try to parse as JSON if it looks like it
        if combined.strip().startswith(("{", "[")):
            try:
                return json.loads(combined)
            except json.JSONDecodeError:
                pass

        return combined

    # ── JSON-RPC transport ───────────────────────────────────────────────

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and await the response."""
        if self._process is None or self._process.stdin is None:
            raise ConnectionError("MCP server not started")

        self._request_id += 1
        req_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        # Create future for this request
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = fut

        # Write to stdin
        data = json.dumps(message) + "\n"
        self._process.stdin.write(data.encode())
        await self._process.stdin.drain()

        logger.debug("MCP request sent: id=%d method=%s", req_id, method)

        # Await response with timeout
        try:
            result = await asyncio.wait_for(fut, timeout=self._timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"MCP request timed out: {method} (id={req_id})")

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if self._process is None or self._process.stdin is None:
            return

        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        data = json.dumps(message) + "\n"
        self._process.stdin.write(data.encode())
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        """Continuously read JSON-RPC responses from the process stdout."""
        assert self._process is not None and self._process.stdout is not None

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break  # EOF

                line_str = line.decode().strip()
                if not line_str:
                    continue

                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError:
                    logger.warning("MCP non-JSON output: %s", line_str[:200])
                    continue

                # Handle response (has "id")
                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        if "error" in msg:
                            fut.set_exception(
                                RuntimeError(f"MCP error: {msg['error']}")
                            )
                        else:
                            fut.set_result(msg.get("result", {}))
                elif "method" in msg:
                    # Server-initiated notification — log and ignore
                    logger.debug("MCP notification: %s", msg.get("method"))
                else:
                    logger.debug("MCP unhandled message: %s", line_str[:200])

        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("MCP reader loop error")


# ── Singleton for iMCP ───────────────────────────────────────────────────

_imcp_client: Optional[MCPStdioClient] = None


def get_imcp_client() -> MCPStdioClient:
    """Return a singleton MCPStdioClient configured for iMCP."""
    global _imcp_client
    if _imcp_client is None:
        _imcp_client = MCPStdioClient(
            command="/Applications/iMCP.app/Contents/MacOS/imcp-server",
            timeout=30.0,
        )
    return _imcp_client


async def close_imcp_client() -> None:
    """Shut down the singleton iMCP client."""
    global _imcp_client
    if _imcp_client is not None:
        await _imcp_client.stop()
        _imcp_client = None
