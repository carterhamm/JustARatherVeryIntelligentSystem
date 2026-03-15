"""
Kali Linux Docker integration for JARVIS.

Provides safe, whitelisted access to security tools running in an isolated
Kali Linux container on the Mac Mini. All commands require explicit user
approval and are logged for transparency.

For educational, simulated, and consented purposes only.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.db.redis import get_redis_client
from app.integrations.mac_mini import is_configured, remote_exec

logger = logging.getLogger("jarvis.kali_service")

CONTAINER_NAME = "jarvis-kali"
AUDIT_KEY_PREFIX = "jarvis:kali:audit_log"
AUDIT_TTL_SECONDS = 90 * 24 * 60 * 60  # 90 days

# ── Tool whitelist ───────────────────────────────────────────────────────────

_TOOL_WHITELIST: dict[str, dict[str, Any]] = {
    "nmap": {
        "allowed_flags": ["-sn", "-sV", "-sC", "-p", "-O", "--top-ports", "-A"],
        "requires_private_ip": True,
    },
    "whois": {
        "allowed_flags": [],
        "requires_private_ip": False,
    },
    "dig": {
        "allowed_flags": ["ANY", "A", "AAAA", "MX", "NS", "TXT", "+short"],
        "requires_private_ip": False,
    },
    "nslookup": {
        "allowed_flags": [],
        "requires_private_ip": False,
    },
    "traceroute": {
        "allowed_flags": ["-m"],
        "requires_private_ip": False,
    },
    "ping": {
        "allowed_flags": ["-c"],
        "requires_private_ip": False,
    },
    "curl": {
        "allowed_flags": ["-I", "-s", "-v", "-L", "--head"],
        "requires_private_ip": False,
    },
    "nikto": {
        "allowed_flags": ["-h", "-p", "-ssl"],
        "requires_private_ip": True,
    },
    "dirb": {
        "allowed_flags": [],
        "requires_private_ip": True,
    },
    "sqlmap": {
        "allowed_flags": ["-u", "--batch", "--level", "--risk"],
        "requires_private_ip": True,
    },
}

# Patterns that must never appear in a command
_DANGEROUS_PATTERNS = re.compile(
    r"""
    \brm\s      |   # rm with args
    \bdd\s      |   # disk destroy
    \bmkfs\b    |   # format filesystem
    ;           |   # command chaining
    &&          |   # command chaining
    \|\|        |   # command chaining
    \|          |   # piping
    `           |   # backtick substitution
    \$\(        |   # subshell substitution
    >>?\s       |   # output redirection
    <               # input redirection
    """,
    re.VERBOSE,
)


# ── Public API ───────────────────────────────────────────────────────────────


async def execute_kali_command(
    command: str,
    timeout: int = 60,
    user: str = "unknown",
) -> dict[str, Any]:
    """Execute a whitelisted security tool in the Kali container.

    Args:
        command: The security tool command to run (e.g. ``nmap -sn 192.168.1.0/24``).
        timeout: Max seconds to wait for the command to complete.
        user: Username for audit logging.

    Returns:
        Dict with success, output, command, tool, and educational_context.
    """
    if not is_configured():
        return {
            "success": False,
            "output": "Mac Mini agent not configured — cannot reach Kali container.",
            "command": command,
            "tool": "",
            "educational_context": "",
        }

    allowed, reason = _validate_command(command)
    if not allowed:
        return {
            "success": False,
            "output": f"Command blocked: {reason}",
            "command": command,
            "tool": "",
            "educational_context": (
                "Only whitelisted security tools are permitted. "
                f"Allowed tools: {', '.join(sorted(_TOOL_WHITELIST.keys()))}."
            ),
        }

    tool = command.strip().split()[0]
    docker_cmd = f"docker exec {CONTAINER_NAME} {command}"

    logger.info(
        "Executing Kali command",
        extra={"tool": tool, "command": command, "user": user},
    )

    result = await remote_exec(command=docker_cmd, timeout=timeout)

    success = result.get("success", False)
    output = result.get("stdout", "") or result.get("stderr", "")

    # Audit log
    await _store_audit_entry(
        tool=tool,
        command=command,
        user=user,
        success=success,
        output_snippet=output[:500],
    )

    return {
        "success": success,
        "output": output,
        "command": command,
        "tool": tool,
        "educational_context": _get_educational_context(tool),
    }


async def get_kali_status() -> dict[str, Any]:
    """Check if the Kali container is running on the Mac Mini."""
    if not is_configured():
        return {
            "running": False,
            "tools_available": [],
            "uptime": "",
            "last_command": None,
        }

    result = await remote_exec(
        command=f"docker inspect --format '{{{{.State.Status}}}} {{{{.State.StartedAt}}}}' {CONTAINER_NAME}",
        timeout=15,
    )

    running = False
    uptime = ""
    if result.get("success"):
        parts = result.get("stdout", "").strip().split(" ", 1)
        running = parts[0] == "running" if parts else False
        uptime = parts[1] if len(parts) > 1 else ""

    # Fetch last audit entry
    last_command = None
    try:
        redis = await get_redis_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{AUDIT_KEY_PREFIX}:{today}"
        entries = await redis.client.lrange(key, 0, 0)
        if entries:
            last_command = json.loads(entries[0])
    except Exception:
        logger.debug("Could not fetch last Kali command from Redis")

    return {
        "running": running,
        "tools_available": sorted(_TOOL_WHITELIST.keys()),
        "uptime": uptime,
        "last_command": last_command,
    }


async def get_audit_log(days: int = 7) -> list[dict[str, Any]]:
    """Return recent Kali command executions from Redis.

    Args:
        days: Number of days of history to retrieve (default 7).

    Returns:
        List of audit entries, newest first.
    """
    entries: list[dict[str, Any]] = []
    try:
        redis = await get_redis_client()
        now = datetime.now(timezone.utc)
        for offset in range(days):
            day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            day = day.replace(day=now.day - offset) if offset == 0 else _subtract_days(now, offset)
            key = f"{AUDIT_KEY_PREFIX}:{day.strftime('%Y-%m-%d')}"
            raw = await redis.client.lrange(key, 0, -1)
            for item in raw:
                entries.append(json.loads(item))
    except Exception:
        logger.exception("Failed to retrieve Kali audit log")
    return entries


# ── Validation ───────────────────────────────────────────────────────────────


def _validate_command(command: str) -> tuple[bool, str]:
    """Validate a command against the tool whitelist and safety rules.

    Returns:
        Tuple of (allowed, reason). If allowed is ``True``, reason is empty.
    """
    stripped = command.strip()
    if not stripped:
        return False, "Empty command."

    parts = stripped.split()
    tool = parts[0]

    if tool not in _TOOL_WHITELIST:
        return False, f"Tool '{tool}' is not whitelisted. Allowed: {', '.join(sorted(_TOOL_WHITELIST.keys()))}."

    # Check for dangerous patterns
    if _DANGEROUS_PATTERNS.search(stripped):
        return False, "Command contains dangerous patterns (shell operators, redirects, or destructive commands)."

    config = _TOOL_WHITELIST[tool]

    # If the tool requires private IP, find and validate the target
    if config["requires_private_ip"]:
        target = _extract_target(parts[1:], tool)
        if target and not _is_private_ip(target):
            return (
                False,
                f"Tool '{tool}' requires a private/local IP target. "
                f"'{target}' is not in a private range (10.x, 172.16-31.x, 192.168.x).",
            )
        if not target and tool in ("nmap", "nikto", "dirb", "sqlmap"):
            return False, f"Tool '{tool}' requires a target — none detected in the command."

    return True, ""


def _extract_target(args: list[str], tool: str) -> str | None:
    """Best-effort extraction of the target host/IP from command arguments."""
    for arg in reversed(args):
        if arg.startswith("-") or arg.startswith("/"):
            continue
        # Strip URL scheme for curl-style targets
        cleaned = re.sub(r"^https?://", "", arg).split("/")[0].split(":")[0]
        if cleaned:
            return cleaned
    return None


def _is_private_ip(target: str) -> bool:
    """Check if a target string resolves to a private/local IP range."""
    # Handle CIDR notation
    try:
        if "/" in target:
            net = ipaddress.ip_network(target, strict=False)
            return net.is_private
        addr = ipaddress.ip_address(target)
        return addr.is_private or addr.is_loopback
    except ValueError:
        # Not a valid IP — might be a hostname. Reject for safety.
        return False


def _get_educational_context(tool: str) -> str:
    """Return a brief educational explanation of the given security tool."""
    context_map: dict[str, str] = {
        "nmap": (
            "Nmap (Network Mapper) discovers hosts and services on a network by "
            "sending packets and analysing responses. Used for network inventory, "
            "service auditing, and security assessments."
        ),
        "whois": (
            "WHOIS queries public registrar databases to retrieve domain ownership, "
            "registration dates, and nameserver information."
        ),
        "dig": (
            "dig (Domain Information Groper) queries DNS servers for record types "
            "like A, AAAA, MX, and TXT — essential for verifying DNS configuration."
        ),
        "nslookup": (
            "nslookup performs forward and reverse DNS lookups, translating domain "
            "names to IPs and vice versa."
        ),
        "traceroute": (
            "traceroute maps the network path packets take from source to "
            "destination, showing each hop and its latency."
        ),
        "ping": (
            "ping sends ICMP echo requests to verify host reachability and measure "
            "round-trip latency."
        ),
        "curl": (
            "curl transfers data from URLs, commonly used to inspect HTTP headers, "
            "test API endpoints, and check server responses."
        ),
        "nikto": (
            "Nikto is a web server scanner that checks for dangerous files, outdated "
            "software, and common misconfigurations. Only used against authorised targets."
        ),
        "dirb": (
            "DIRB brute-forces web paths using wordlists to discover hidden "
            "directories and files on a web server. Only used against authorised targets."
        ),
        "sqlmap": (
            "sqlmap automates detection and exploitation of SQL injection flaws. "
            "Only used against authorised targets in controlled lab environments."
        ),
    }
    return context_map.get(tool, f"{tool} is a security utility available in the Kali Linux toolkit.")


# ── Internal helpers ─────────────────────────────────────────────────────────


async def _store_audit_entry(
    tool: str,
    command: str,
    user: str,
    success: bool,
    output_snippet: str,
) -> None:
    """Push an audit entry to the daily Redis list."""
    try:
        redis = await get_redis_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{AUDIT_KEY_PREFIX}:{today}"
        entry = json.dumps({
            "tool": tool,
            "command": command,
            "user": user,
            "success": success,
            "output_snippet": output_snippet,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await redis.client.lpush(key, entry)
        await redis.client.expire(key, AUDIT_TTL_SECONDS)
    except Exception:
        logger.debug("Failed to store Kali audit entry in Redis")


def _subtract_days(dt: datetime, days: int) -> datetime:
    """Subtract *days* from a datetime (avoids timedelta import at module level)."""
    from datetime import timedelta

    return dt - timedelta(days=days)
