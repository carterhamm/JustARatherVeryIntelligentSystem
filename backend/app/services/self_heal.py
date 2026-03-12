"""JARVIS Self-Healing Daemon — automatic deployment error detection and repair.

Runs every 15 minutes (same cadence as heartbeat) and:

  1. Health-checks the live backend (HTTP + Railway deploy status)
  2. Scans recent deploy logs for Python tracebacks / crash signatures
  3. If an error is found, dispatches Claude Code on the Mac Mini to fix,
     commit, push, and redeploy
  4. Notifies the owner via iMessage with what was detected and fixed

The self-healer itself must NEVER crash — every phase is wrapped in
exception handling so a failure in one stage doesn't block the rest.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger("jarvis.self_heal")

_MTN = ZoneInfo("America/Denver")

# Owner phone (for iMessage notifications)
_OWNER_PHONE = "+17192136213"

# Railway API constants
_RAILWAY_GQL_URL = "https://backboard.railway.com/graphql/v2"
_RAILWAY_PROJECT_ID = "db91f313-470d-40d0-85b1-a652f2bcdd7d"
_RAILWAY_SERVICE_ID = "adb6b312-0380-40aa-91e5-39c047a52ee2"
_RAILWAY_ENV_ID = "67600b40-eef5-4b9c-9819-ce98b370d2f9"
_RAILWAY_TOKEN = "90e04bb8-a13d-46b5-b1d9-abc8641d70f0"

# Backend base URL
_BACKEND_URL = "https://app.malibupoint.dev"

# Error patterns to scan for in logs
_ERROR_PATTERNS = [
    "Traceback (most recent call last)",
    "ImportError:",
    "ModuleNotFoundError:",
    "SyntaxError:",
    "IndentationError:",
    "TypeError:",
    "AttributeError:",
    "Internal Server Error",
    "Application startup failed",
    "Worker failed to boot",
    "SIGKILL",
    "OOMKilled",
    "exit code 1",
]

# Repo path on the Mac Mini (home directory clone)
_REPO_PATH = "~/JustARatherVeryIntelligentSystem"


# ═════════════════════════════════════════════════════════════════════════════
# Phase 1 — Health Checks
# ═════════════════════════════════════════════════════════════════════════════

async def _check_backend_health() -> dict[str, Any]:
    """GET /health on the live backend. Returns status dict."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_BACKEND_URL}/health")
            return {
                "reachable": True,
                "status_code": resp.status_code,
                "healthy": resp.status_code == 200,
                "body": resp.json() if resp.status_code == 200 else resp.text[:500],
            }
    except httpx.ConnectError:
        return {"reachable": False, "healthy": False, "error": "Connection refused"}
    except httpx.TimeoutException:
        return {"reachable": False, "healthy": False, "error": "Timeout"}
    except Exception as exc:
        return {"reachable": False, "healthy": False, "error": str(exc)}


async def _check_widgets_status() -> dict[str, Any]:
    """Check /api/v1/widgets/status for service availability."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{_BACKEND_URL}/api/v1/widgets/status")
            if resp.status_code == 200:
                return {"available": True, "data": resp.json()}
            return {"available": True, "status_code": resp.status_code}
    except Exception as exc:
        # Widgets status is optional — not all deploys have it
        return {"available": False, "error": str(exc)}


async def _railway_graphql(query: str, variables: dict | None = None) -> dict[str, Any]:
    """Execute a Railway GraphQL query."""
    headers = {
        "Authorization": f"Bearer {_RAILWAY_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "JARVIS/1.0",
    }
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(_RAILWAY_GQL_URL, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def _check_railway_deploy_status() -> dict[str, Any]:
    """Query Railway for the latest deployment status."""
    query = """
    query($serviceId: String!, $environmentId: String!) {
      deployments(
        first: 3
        input: {
          serviceId: $serviceId
          environmentId: $environmentId
        }
      ) {
        edges {
          node {
            id
            status
            createdAt
            meta
          }
        }
      }
    }
    """
    try:
        result = await _railway_graphql(query, {
            "serviceId": _RAILWAY_SERVICE_ID,
            "environmentId": _RAILWAY_ENV_ID,
        })

        edges = result.get("data", {}).get("deployments", {}).get("edges", [])
        if not edges:
            return {"found": False, "error": "No deployments found"}

        latest = edges[0]["node"]
        return {
            "found": True,
            "deploy_id": latest["id"],
            "status": latest["status"],
            "created_at": latest.get("createdAt", ""),
            "meta": latest.get("meta"),
            "all_recent": [
                {
                    "id": e["node"]["id"],
                    "status": e["node"]["status"],
                    "created_at": e["node"].get("createdAt", ""),
                }
                for e in edges
            ],
        }
    except Exception as exc:
        logger.warning("Railway deploy status check failed: %s", exc)
        return {"found": False, "error": str(exc)}


async def _get_railway_deploy_logs() -> dict[str, Any]:
    """Fetch recent deploy logs from Railway."""
    query = """
    query($deploymentId: String!) {
      deploymentLogs(deploymentId: $deploymentId, limit: 100) {
        ... on Log {
          message
          timestamp
          severity
        }
      }
    }
    """
    # First get the latest deployment ID
    deploy_info = await _check_railway_deploy_status()
    if not deploy_info.get("found"):
        return {"logs": [], "error": deploy_info.get("error", "No deployment found")}

    deploy_id = deploy_info["deploy_id"]

    try:
        # Try the build/deploy logs endpoint
        log_query = """
        query($deploymentId: String!) {
          buildLogs(deploymentId: $deploymentId, limit: 100) {
            ... on Log {
              message
              timestamp
            }
          }
        }
        """
        result = await _railway_graphql(log_query, {"deploymentId": deploy_id})
        logs = result.get("data", {}).get("buildLogs", [])

        if not logs:
            # Try environment logs instead
            env_query = """
            query($environmentId: String!, $serviceId: String!) {
              environmentLogs(
                environmentId: $environmentId
                serviceId: $serviceId
                limit: 100
              )
            }
            """
            result = await _railway_graphql(env_query, {
                "environmentId": _RAILWAY_ENV_ID,
                "serviceId": _RAILWAY_SERVICE_ID,
            })
            logs = result.get("data", {}).get("environmentLogs", [])

        return {
            "deploy_id": deploy_id,
            "deploy_status": deploy_info.get("status"),
            "logs": logs if isinstance(logs, list) else [],
        }
    except Exception as exc:
        logger.warning("Railway log fetch failed: %s", exc)
        return {
            "deploy_id": deploy_id,
            "deploy_status": deploy_info.get("status"),
            "logs": [],
            "error": str(exc),
        }


# ═════════════════════════════════════════════════════════════════════════════
# Phase 2 — Error Detection
# ═════════════════════════════════════════════════════════════════════════════

def _scan_logs_for_errors(logs: list[Any]) -> list[dict[str, str]]:
    """Scan log entries for known error patterns.

    Returns a list of ``{"pattern": ..., "line": ...}`` dicts.
    """
    errors: list[dict[str, str]] = []
    seen_lines: set[str] = set()

    for entry in logs:
        line = ""
        if isinstance(entry, str):
            line = entry
        elif isinstance(entry, dict):
            line = entry.get("message", "") or entry.get("text", "") or str(entry)
        else:
            line = str(entry)

        if not line or line in seen_lines:
            continue
        seen_lines.add(line)

        for pattern in _ERROR_PATTERNS:
            if pattern.lower() in line.lower():
                errors.append({"pattern": pattern, "line": line[:500]})
                break  # one match per line is enough

    return errors


def _build_error_summary(
    health: dict[str, Any],
    deploy: dict[str, Any],
    log_errors: list[dict[str, str]],
) -> Optional[str]:
    """Compose a plain-text summary of everything that's wrong.

    Returns None if everything looks healthy.
    """
    problems: list[str] = []

    # Backend unreachable
    if not health.get("healthy"):
        if not health.get("reachable"):
            problems.append(
                f"Backend is UNREACHABLE at {_BACKEND_URL}: {health.get('error', 'unknown')}"
            )
        else:
            problems.append(
                f"Backend returned HTTP {health.get('status_code')} (expected 200)"
            )

    # Railway deploy in bad state
    deploy_status = deploy.get("status", "").upper()
    if deploy_status in ("FAILED", "CRASHED", "REMOVED", "ERROR"):
        problems.append(f"Railway deployment status: {deploy_status}")
    elif deploy_status == "BUILDING" and deploy.get("created_at"):
        # Possibly stuck — but we can't tell without age; flag cautiously
        problems.append(f"Railway deployment has been BUILDING (may be stuck)")

    # Log errors
    if log_errors:
        error_lines = "\n".join(
            f"  [{e['pattern']}] {e['line'][:200]}" for e in log_errors[:10]
        )
        problems.append(f"Found {len(log_errors)} error(s) in recent logs:\n{error_lines}")

    if not problems:
        return None

    return "\n\n".join(problems)


# ═════════════════════════════════════════════════════════════════════════════
# Phase 3 — Auto-Fix via Mac Mini Claude Code
# ═════════════════════════════════════════════════════════════════════════════

async def _attempt_auto_fix(error_summary: str) -> dict[str, Any]:
    """Dispatch Claude Code on the Mac Mini to diagnose and fix the error.

    Returns a dict with success, output, and duration_ms.
    """
    from app.integrations.mac_mini import run_claude_code, is_configured

    if not is_configured():
        logger.warning("Self-heal: Mac Mini agent not configured — cannot auto-fix")
        return {
            "success": False,
            "output": "Mac Mini agent not configured — manual intervention required",
            "attempted": False,
        }

    prompt = (
        f"JARVIS deployment error detected. Here is the problem:\n\n"
        f"{error_summary}\n\n"
        f"Instructions:\n"
        f"1. Check the codebase for the root cause of these errors\n"
        f"2. Fix the issue (edit the relevant file(s))\n"
        f"3. Run any tests if available to verify the fix\n"
        f"4. Commit the fix with a descriptive message\n"
        f"5. Push to git: git push origin master\n"
        f"6. Deploy: railway up --detach\n"
        f"7. Report exactly what you found and fixed\n\n"
        f"Be surgical — fix only what's broken. Do not refactor unrelated code."
    )

    logger.info("Self-heal: dispatching Claude Code to fix: %s", error_summary[:200])

    try:
        result = await run_claude_code(
            prompt=prompt,
            working_dir=_REPO_PATH,
            timeout=600,  # 10 minutes
        )
        return {
            "success": result.get("success", False),
            "output": result.get("output", "")[:2000],
            "exit_code": result.get("exit_code", -1),
            "duration_ms": result.get("duration_ms", 0),
            "attempted": True,
        }
    except Exception as exc:
        logger.exception("Self-heal: Claude Code dispatch failed")
        return {
            "success": False,
            "output": f"Claude Code dispatch failed: {exc}",
            "attempted": True,
        }


# ═════════════════════════════════════════════════════════════════════════════
# Phase 4 — Notification
# ═════════════════════════════════════════════════════════════════════════════

async def _notify_owner(
    error_summary: str,
    fix_result: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Send an iMessage to the owner about what was detected/fixed."""
    from app.integrations.mac_mini import send_imessage, is_configured

    if not is_configured():
        logger.warning("Self-heal: Mac Mini not configured — cannot send notification")
        return {"sent": False, "reason": "Mac Mini not configured"}

    # Compose the message
    now = datetime.now(tz=_MTN).strftime("%I:%M %p")
    lines = [f"**Self-Heal Report** ({now})"]

    # Summarise what was found (keep it brief for iMessage)
    # Trim the error summary to a reasonable length
    brief_error = error_summary[:300]
    if len(error_summary) > 300:
        brief_error += "..."
    lines.append(f"\n*Issue detected:*\n{brief_error}")

    if fix_result:
        if fix_result.get("attempted"):
            if fix_result.get("success"):
                fix_output = fix_result.get("output", "")[:400]
                lines.append(f"\n*Auto-fix applied:*\n{fix_output}")
            else:
                lines.append(
                    f"\n*Auto-fix attempted but failed:*\n{fix_result.get('output', 'unknown')[:200]}"
                )
        else:
            lines.append(f"\n*Could not attempt auto-fix:* {fix_result.get('output', '')[:200]}")
    else:
        lines.append("\n*No auto-fix attempted.*")

    message = "\n".join(lines)

    try:
        result = await send_imessage(to=_OWNER_PHONE, text=message)
        return {"sent": result.get("success", False), "detail": result}
    except Exception as exc:
        logger.warning("Self-heal notification failed: %s", exc)
        return {"sent": False, "error": str(exc)}


# ═════════════════════════════════════════════════════════════════════════════
# Redis persistence
# ═════════════════════════════════════════════════════════════════════════════

async def _store_result(result: dict[str, Any]) -> None:
    """Persist the latest self-heal result to Redis."""
    try:
        from app.db.redis import get_redis_client

        redis = await get_redis_client()
        await redis.cache_set(
            "jarvis:self_heal:last_result",
            json.dumps(result, default=str),
            ttl=86400 * 7,  # 7 days
        )

        # Append to today's log
        now = datetime.now(tz=_MTN)
        log_key = f"jarvis:self_heal:log:{now.strftime('%Y-%m-%d')}"
        existing = await redis.cache_get(log_key)
        entries = json.loads(existing) if existing else []
        entries.append({
            "time": result.get("timestamp", ""),
            "healthy": result.get("healthy", False),
            "error_count": result.get("error_count", 0),
            "fix_attempted": result.get("fix_attempted", False),
            "fix_success": result.get("fix_success", False),
        })
        await redis.cache_set(log_key, json.dumps(entries), ttl=86400 * 3)
    except Exception as exc:
        logger.warning("Failed to store self-heal result in Redis: %s", exc)


# ═════════════════════════════════════════════════════════════════════════════
# Anti-spam: don't fix the same error repeatedly
# ═════════════════════════════════════════════════════════════════════════════

async def _already_attempted_fix(error_hash: str) -> bool:
    """Check if we've already tried to fix this exact error recently."""
    try:
        from app.db.redis import get_redis_client

        redis = await get_redis_client()
        key = f"jarvis:self_heal:attempted:{error_hash}"
        val = await redis.cache_get(key)
        return val is not None
    except Exception:
        return False


async def _mark_fix_attempted(error_hash: str) -> None:
    """Mark an error as having been attempted, with 2-hour cooldown."""
    try:
        from app.db.redis import get_redis_client

        redis = await get_redis_client()
        key = f"jarvis:self_heal:attempted:{error_hash}"
        await redis.cache_set(key, "1", ttl=7200)  # 2 hours
    except Exception:
        pass


def _hash_error(summary: str) -> str:
    """Produce a stable hash for deduplication."""
    import hashlib
    return hashlib.sha256(summary.encode()).hexdigest()[:16]


# ═════════════════════════════════════════════════════════════════════════════
# Main entry point
# ═════════════════════════════════════════════════════════════════════════════

async def run_self_heal() -> dict[str, Any]:
    """Execute one self-healing cycle.

    1. Health check the live backend and Railway deployment
    2. Detect errors in logs
    3. If errors found, dispatch Claude Code to fix
    4. Notify owner of outcome
    5. Store results in Redis

    Returns a status dict summarising the cycle.
    """
    logger.info("Self-heal cycle starting")
    now = datetime.now(tz=_MTN)
    result: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "status": "ok",
        "healthy": True,
        "error_count": 0,
        "fix_attempted": False,
        "fix_success": False,
    }

    # ── Phase 1: Health checks ──────────────────────────────────────────
    try:
        health = await _check_backend_health()
        result["health"] = health
    except Exception as exc:
        logger.error("Self-heal health check crashed: %s", exc)
        health = {"healthy": False, "error": str(exc)}
        result["health"] = health

    try:
        widgets = await _check_widgets_status()
        result["widgets"] = widgets
    except Exception as exc:
        logger.warning("Self-heal widgets check failed: %s", exc)
        widgets = {"available": False}
        result["widgets"] = widgets

    try:
        deploy = await _check_railway_deploy_status()
        result["deploy"] = deploy
    except Exception as exc:
        logger.warning("Self-heal Railway deploy check failed: %s", exc)
        deploy = {"found": False, "error": str(exc)}
        result["deploy"] = deploy

    # ── Phase 1b: Fetch deploy logs ─────────────────────────────────────
    log_errors: list[dict[str, str]] = []
    try:
        log_data = await _get_railway_deploy_logs()
        log_errors = _scan_logs_for_errors(log_data.get("logs", []))
        result["log_scan"] = {
            "logs_fetched": len(log_data.get("logs", [])),
            "errors_found": len(log_errors),
        }
    except Exception as exc:
        logger.warning("Self-heal log scan failed: %s", exc)
        result["log_scan"] = {"error": str(exc)}

    # ── Phase 2: Error detection ────────────────────────────────────────
    try:
        error_summary = _build_error_summary(health, deploy, log_errors)
    except Exception as exc:
        logger.error("Self-heal error detection crashed: %s", exc)
        error_summary = None

    if error_summary:
        result["healthy"] = False
        result["error_count"] = len(log_errors) + (0 if health.get("healthy") else 1)
        result["error_summary"] = error_summary[:1000]

        # ── Phase 2b: Anti-spam check ───────────────────────────────────
        error_key = _hash_error(error_summary)
        already_tried = await _already_attempted_fix(error_key)

        if already_tried:
            logger.info(
                "Self-heal: already attempted fix for this error within cooldown — skipping"
            )
            result["status"] = "error_known"
            result["skipped_reason"] = "fix_already_attempted_recently"
            await _store_result(result)
            return result

        # ── Phase 3: Auto-fix ───────────────────────────────────────────
        try:
            fix_result = await _attempt_auto_fix(error_summary)
            result["fix"] = fix_result
            result["fix_attempted"] = fix_result.get("attempted", False)
            result["fix_success"] = fix_result.get("success", False)

            # Mark this error as attempted
            await _mark_fix_attempted(error_key)
        except Exception as exc:
            logger.exception("Self-heal auto-fix crashed: %s", exc)
            fix_result = {"attempted": False, "output": f"Auto-fix crashed: {exc}"}
            result["fix"] = fix_result

        # ── Phase 4: Notify owner ───────────────────────────────────────
        try:
            notification = await _notify_owner(error_summary, fix_result)
            result["notification"] = notification
        except Exception as exc:
            logger.warning("Self-heal notification failed: %s", exc)
            result["notification"] = {"sent": False, "error": str(exc)}

        result["status"] = "fixed" if result["fix_success"] else "error_detected"
    else:
        logger.info("Self-heal: all systems nominal")
        result["status"] = "healthy"

    # ── Persist results ─────────────────────────────────────────────────
    await _store_result(result)

    logger.info(
        "Self-heal cycle complete: status=%s healthy=%s errors=%d fix=%s",
        result["status"],
        result["healthy"],
        result["error_count"],
        result["fix_success"],
    )
    return result


# ═════════════════════════════════════════════════════════════════════════════
# On-demand system health check (used by the JARVIS tool)
# ═════════════════════════════════════════════════════════════════════════════

async def get_system_health() -> dict[str, Any]:
    """Return a snapshot of system health without triggering auto-fix.

    Used by the SystemHealthTool so JARVIS can report status on demand.
    """
    report: dict[str, Any] = {
        "timestamp": datetime.now(tz=_MTN).isoformat(),
    }

    # Backend health
    try:
        report["backend"] = await _check_backend_health()
    except Exception as exc:
        report["backend"] = {"healthy": False, "error": str(exc)}

    # Railway deploy status
    try:
        report["railway_deploy"] = await _check_railway_deploy_status()
    except Exception as exc:
        report["railway_deploy"] = {"found": False, "error": str(exc)}

    # Mac Mini health
    try:
        from app.integrations.mac_mini import health_check as mini_health
        report["mac_mini"] = {"reachable": await mini_health()}
    except Exception as exc:
        report["mac_mini"] = {"reachable": False, "error": str(exc)}

    # Last self-heal result
    try:
        from app.db.redis import get_redis_client
        redis = await get_redis_client()
        last_raw = await redis.cache_get("jarvis:self_heal:last_result")
        if last_raw:
            last = json.loads(last_raw)
            report["last_self_heal"] = {
                "timestamp": last.get("timestamp"),
                "status": last.get("status"),
                "healthy": last.get("healthy"),
                "error_count": last.get("error_count", 0),
            }
        else:
            report["last_self_heal"] = None
    except Exception:
        report["last_self_heal"] = None

    # Last heartbeat result
    try:
        last_hb_raw = await redis.cache_get("jarvis:heartbeat:last_result")
        if last_hb_raw:
            last_hb = json.loads(last_hb_raw)
            report["last_heartbeat"] = {
                "timestamp": last_hb.get("timestamp"),
                "status": last_hb.get("status"),
                "noteworthy": last_hb.get("noteworthy"),
            }
        else:
            report["last_heartbeat"] = None
    except Exception:
        report["last_heartbeat"] = None

    # Overall verdict
    backend_ok = report.get("backend", {}).get("healthy", False)
    deploy_ok = report.get("railway_deploy", {}).get("status", "").upper() in (
        "SUCCESS", "DEPLOYING", "BUILDING",
    )
    mini_ok = report.get("mac_mini", {}).get("reachable", False)

    report["overall"] = "nominal" if (backend_ok and deploy_ok) else "degraded"
    report["components"] = {
        "backend": "up" if backend_ok else "down",
        "railway_deploy": report.get("railway_deploy", {}).get("status", "unknown"),
        "mac_mini": "up" if mini_ok else "down",
    }

    return report
