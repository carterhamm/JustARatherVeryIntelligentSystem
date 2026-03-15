"""Pillar 1: Automated Code Management for JARVIS.

Reviews the codebase for health issues, identifies performance problems and
inefficiencies via log analysis + LLM reasoning, and creates GitHub PRs for
improvements using Claude Code on the Mac Mini.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, date
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.db.redis import get_redis_client
from app.integrations.llm.factory import get_llm_client
from app.services.self_heal import (
    _check_backend_health,
    _get_railway_deploy_logs,
    _scan_logs_for_errors,
)

logger = logging.getLogger("jarvis.autonomy.code_manager")

_MTN = ZoneInfo("America/Denver")
_REPO = "carterhamm/JustARatherVeryIntelligentSystem"
_REPO_PATH = "~/JustARatherVeryIntelligentSystem"

# Redis key prefixes
_KEY_LOCK = "jarvis:autonomy:code:lock"
_KEY_HEALTH = "jarvis:autonomy:code:health_metrics"
_KEY_LAST_REVIEW = "jarvis:autonomy:code:last_review"
_KEY_PR_COUNT = "jarvis:autonomy:code:pr_count"       # :{date}
_KEY_PR_COOLDOWN = "jarvis:autonomy:code:pr_cooldown"  # :{hash}

# Limits
_MAX_PRS_PER_DAY = 3
_LOCK_TTL = 600        # 10 minutes
_HEALTH_TTL = 86400 * 90  # 90 days
_REVIEW_TTL = 86400 * 7   # 7 days
_PR_COUNT_TTL = 86400 * 2  # 48 hours
_COOLDOWN_TTL = 86400      # 24 hours


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _issue_hash(title: str, description: str) -> str:
    """Stable hash for deduplication of an issue."""
    raw = f"{title}|{description}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _slugify(text: str) -> str:
    """Convert a title into a branch-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60]


async def _acquire_lock(redis: Any) -> bool:
    """Try to acquire the review-cycle lock. Returns True on success."""
    result = await redis.client.set(_KEY_LOCK, "1", ex=_LOCK_TTL, nx=True)
    return result is not None


async def _release_lock(redis: Any) -> None:
    """Release the review-cycle lock."""
    try:
        await redis.cache_delete(_KEY_LOCK)
    except Exception:
        pass


async def _get_pr_count_today(redis: Any) -> int:
    """Return the number of PRs created today."""
    key = f"{_KEY_PR_COUNT}:{date.today().isoformat()}"
    val = await redis.cache_get(key)
    return int(val) if val else 0


async def _increment_pr_count(redis: Any) -> None:
    """Bump today's PR count by one."""
    key = f"{_KEY_PR_COUNT}:{date.today().isoformat()}"
    val = await redis.cache_get(key)
    new_count = (int(val) if val else 0) + 1
    await redis.cache_set(key, str(new_count), ttl=_PR_COUNT_TTL)


async def _is_on_cooldown(redis: Any, issue_h: str) -> bool:
    """Check whether an issue hash is still within its 24h cooldown."""
    key = f"{_KEY_PR_COOLDOWN}:{issue_h}"
    val = await redis.cache_get(key)
    return val is not None


async def _set_cooldown(redis: Any, issue_h: str) -> None:
    """Mark an issue hash as recently addressed."""
    key = f"{_KEY_PR_COOLDOWN}:{issue_h}"
    await redis.cache_set(key, "1", ttl=_COOLDOWN_TTL)


async def _get_perf_data(redis: Any) -> dict[str, Any]:
    """Gather response-time and error-rate metrics from Redis."""
    perf: dict[str, Any] = {}
    try:
        # Heartbeat stores response-time snapshots
        raw = await redis.cache_get("jarvis:heartbeat:last_result")
        if raw:
            hb = json.loads(raw)
            perf["last_heartbeat"] = {
                "timestamp": hb.get("timestamp"),
                "status": hb.get("status"),
            }

        # Self-heal stores recent error counts
        raw = await redis.cache_get("jarvis:self_heal:last_result")
        if raw:
            sh = json.loads(raw)
            perf["last_self_heal"] = {
                "timestamp": sh.get("timestamp"),
                "healthy": sh.get("healthy"),
                "error_count": sh.get("error_count", 0),
            }

        # Health endpoint latency (if tracked)
        raw = await redis.cache_get("jarvis:metrics:response_times")
        if raw:
            perf["response_times"] = json.loads(raw)

    except Exception as exc:
        logger.debug("Perf data collection partial failure: %s", exc)

    return perf


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: LLM Analysis
# ═══════════════════════════════════════════════════════════════════════════

async def _analyze_code_health(
    log_errors: list[dict[str, str]],
    perf_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Use Gemini to analyze log errors + performance data.

    Returns a list of issues, each with:
        severity     — "critical" | "improvement" | "suggestion"
        title        — short summary
        description  — detailed explanation
        file_hint    — likely file path involved
        fix_suggestion — proposed fix
    """
    if not log_errors and not perf_data:
        return []

    errors_text = "\n".join(
        f"- [{e['pattern']}] {e['line'][:300]}" for e in log_errors[:20]
    )
    perf_text = json.dumps(perf_data, indent=2, default=str)[:2000]

    prompt = (
        "You are a senior Python/FastAPI engineer reviewing a production backend.\n\n"
        "## Recent Log Errors\n"
        f"{errors_text or '(none)'}\n\n"
        "## Performance / Health Data\n"
        f"{perf_text or '(none)'}\n\n"
        "Analyze the above and identify concrete issues. For each issue, categorize "
        "its severity as one of: critical, improvement, suggestion.\n\n"
        "Return a JSON array (no markdown fences) of objects with these exact keys:\n"
        '  severity, title, description, file_hint, fix_suggestion\n\n'
        "Only include issues you are confident about. If nothing is wrong, return []."
    )

    try:
        llm = get_llm_client("gemini")
        resp = await llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2048,
        )
        content = resp.get("content", "").strip()

        # Strip markdown fences if the model wraps them anyway
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        issues = json.loads(content)
        if not isinstance(issues, list):
            logger.warning("LLM returned non-list for code health: %s", type(issues))
            return []

        valid = []
        for item in issues:
            if isinstance(item, dict) and "severity" in item and "title" in item:
                valid.append({
                    "severity": str(item.get("severity", "suggestion")).lower(),
                    "title": str(item.get("title", "")),
                    "description": str(item.get("description", "")),
                    "file_hint": str(item.get("file_hint", "")),
                    "fix_suggestion": str(item.get("fix_suggestion", "")),
                })
        return valid

    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse LLM code-health response as JSON: %s", exc)
        return []
    except Exception as exc:
        logger.exception("LLM code-health analysis failed: %s", exc)
        return []


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: Create Improvement PR via Mac Mini + GitHub API
# ═══════════════════════════════════════════════════════════════════════════

async def _create_improvement_pr(issue: dict[str, Any]) -> dict[str, Any]:
    """Create a GitHub PR for a single issue.

    1. Check 24h cooldown for this issue hash.
    2. Dispatch Claude Code on the Mac Mini to create a branch, apply fix, push.
    3. Open a PR via the GitHub REST API.
    4. Set cooldown.
    """
    from app.integrations.mac_mini import run_claude_code, is_configured

    title = issue.get("title", "Untitled improvement")
    description = issue.get("description", "")
    file_hint = issue.get("file_hint", "")
    fix_suggestion = issue.get("fix_suggestion", "")

    issue_h = _issue_hash(title, description)
    redis = await get_redis_client()

    # Cooldown check
    if await _is_on_cooldown(redis, issue_h):
        logger.info("PR cooldown active for issue '%s' — skipping", title)
        return {"success": False, "reason": "cooldown", "title": title}

    if not is_configured():
        logger.warning("Mac Mini not configured — cannot create PR")
        return {"success": False, "reason": "mac_mini_not_configured", "title": title}

    if not settings.GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not set — cannot create PR")
        return {"success": False, "reason": "no_github_token", "title": title}

    slug = _slugify(title)
    branch_name = f"jarvis/auto/{slug}"

    # Build the Claude Code prompt
    cc_prompt = (
        f"You are JARVIS's automated code manager. Apply this improvement:\n\n"
        f"**Title**: {title}\n"
        f"**Description**: {description}\n"
        f"**File hint**: {file_hint}\n"
        f"**Suggested fix**: {fix_suggestion}\n\n"
        f"Instructions:\n"
        f"1. git fetch origin && git checkout -b {branch_name} origin/master\n"
        f"2. Apply the fix described above. Be surgical — change only what is needed.\n"
        f"3. For every Python file you modify, run:\n"
        f'   python -c "import ast; ast.parse(open(\'<file>\').read())"\n'
        f"4. git add the changed files (specific files only, never git add .)\n"
        f"5. git commit -m \"auto: {title}\"\n"
        f"6. git push origin {branch_name}\n"
        f"7. Report what you changed.\n\n"
        f"Do NOT deploy. Do NOT push to master. Only push the feature branch."
    )

    logger.info("Dispatching Claude Code for PR: %s", title)

    try:
        cc_result = await run_claude_code(
            prompt=cc_prompt,
            working_dir=_REPO_PATH,
            timeout=300,
        )
    except Exception as exc:
        logger.exception("Claude Code dispatch failed for PR '%s'", title)
        return {"success": False, "reason": f"claude_code_error: {exc}", "title": title}

    if not cc_result.get("success"):
        logger.warning(
            "Claude Code did not succeed for '%s': %s",
            title,
            cc_result.get("output", "")[:300],
        )
        # Still set cooldown to avoid hammering on the same failure
        await _set_cooldown(redis, issue_h)
        return {
            "success": False,
            "reason": "claude_code_failed",
            "title": title,
            "output": cc_result.get("output", "")[:500],
        }

    # Create the PR via GitHub API
    pr_body = (
        f"## Automated Improvement\n\n"
        f"**Severity**: {issue.get('severity', 'unknown')}\n\n"
        f"**Description**: {description}\n\n"
        f"**File hint**: {file_hint}\n\n"
        f"**Suggested fix**: {fix_suggestion}\n\n"
        f"---\n"
        f"*Created automatically by JARVIS code manager.*"
    )

    pr_result: dict[str, Any] = {
        "success": False,
        "title": title,
        "branch": branch_name,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"https://api.github.com/repos/{_REPO}/pulls",
                headers={
                    "Authorization": f"token {settings.GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "JARVIS/1.0",
                },
                json={
                    "title": f"auto: {title}",
                    "body": pr_body,
                    "head": branch_name,
                    "base": "master",
                },
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                pr_result["success"] = True
                pr_result["pr_url"] = data.get("html_url", "")
                pr_result["pr_number"] = data.get("number")
                logger.info("PR created: %s", pr_result["pr_url"])
            else:
                pr_result["reason"] = f"github_api_{resp.status_code}"
                pr_result["github_error"] = resp.text[:500]
                logger.warning(
                    "GitHub PR creation failed (%d): %s",
                    resp.status_code,
                    resp.text[:300],
                )
    except Exception as exc:
        logger.exception("GitHub API call failed for PR '%s'", title)
        pr_result["reason"] = f"github_api_error: {exc}"

    # Set cooldown regardless of PR creation outcome
    await _set_cooldown(redis, issue_h)

    if pr_result["success"]:
        await _increment_pr_count(redis)

    return pr_result


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5: Health Metrics Persistence
# ═══════════════════════════════════════════════════════════════════════════

async def _update_health_metrics(
    redis: Any,
    log_error_count: int,
    issues: list[dict[str, Any]],
    pr_results: list[dict[str, Any]],
) -> None:
    """Accumulate code health metrics in Redis."""
    now = datetime.now(tz=_MTN)

    existing_raw = await redis.cache_get(_KEY_HEALTH)
    metrics: dict[str, Any] = json.loads(existing_raw) if existing_raw else {
        "total_reviews": 0,
        "total_issues_found": 0,
        "total_prs_created": 0,
        "total_prs_failed": 0,
        "severity_counts": {"critical": 0, "improvement": 0, "suggestion": 0},
        "first_review": now.isoformat(),
        "history": [],
    }

    metrics["total_reviews"] += 1
    metrics["total_issues_found"] += len(issues)
    metrics["last_review"] = now.isoformat()

    for issue in issues:
        sev = issue.get("severity", "suggestion")
        if sev in metrics["severity_counts"]:
            metrics["severity_counts"][sev] += 1

    prs_ok = sum(1 for p in pr_results if p.get("success"))
    prs_fail = len(pr_results) - prs_ok
    metrics["total_prs_created"] += prs_ok
    metrics["total_prs_failed"] += prs_fail

    # Keep a rolling window of the last 50 review entries
    entry = {
        "timestamp": now.isoformat(),
        "log_errors": log_error_count,
        "issues": len(issues),
        "prs_created": prs_ok,
        "prs_failed": prs_fail,
    }
    history = metrics.get("history", [])
    history.append(entry)
    metrics["history"] = history[-50:]

    await redis.cache_set(_KEY_HEALTH, json.dumps(metrics, default=str), ttl=_HEALTH_TTL)


# ═══════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════

async def run_code_review_cycle() -> dict[str, Any]:
    """Execute one automated code-review cycle.

    Phases:
        1. Scan Railway logs for errors (reuse self_heal functions).
        2. Analyse response-time patterns from Redis metrics.
        3. Send logs + patterns to Gemini for analysis.
        4. For issues rated "improvement" or "critical", create GitHub PRs.
        5. Track code health metrics in Redis.

    Anti-spam: max 3 PRs/day, 24h cooldown per issue hash.
    """
    logger.info("Code review cycle starting")
    now = datetime.now(tz=_MTN)
    redis = await get_redis_client()

    result: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "status": "ok",
        "phases": {},
        "issues": [],
        "prs": [],
    }

    # ── Acquire lock ─────────────────────────────────────────────────────
    if not await _acquire_lock(redis):
        logger.info("Code review cycle already running — skipping")
        return {"timestamp": now.isoformat(), "status": "skipped", "reason": "lock_held"}

    try:
        # ── Phase 1: Scan Railway logs ───────────────────────────────────
        log_errors: list[dict[str, str]] = []
        try:
            log_data = await _get_railway_deploy_logs()
            log_errors = _scan_logs_for_errors(log_data.get("logs", []))
            result["phases"]["log_scan"] = {
                "logs_fetched": len(log_data.get("logs", [])),
                "errors_found": len(log_errors),
            }
        except Exception as exc:
            logger.warning("Phase 1 log scan failed: %s", exc)
            result["phases"]["log_scan"] = {"error": str(exc)}

        # ── Phase 2: Response time patterns ──────────────────────────────
        perf_data: dict[str, Any] = {}
        try:
            perf_data = await _get_perf_data(redis)
            result["phases"]["perf_analysis"] = {
                "metrics_collected": len(perf_data),
            }
        except Exception as exc:
            logger.warning("Phase 2 perf data collection failed: %s", exc)
            result["phases"]["perf_analysis"] = {"error": str(exc)}

        # ── Phase 3: LLM analysis ────────────────────────────────────────
        issues: list[dict[str, Any]] = []
        try:
            issues = await _analyze_code_health(log_errors, perf_data)
            result["phases"]["llm_analysis"] = {
                "issues_found": len(issues),
                "severities": {
                    s: sum(1 for i in issues if i.get("severity") == s)
                    for s in ("critical", "improvement", "suggestion")
                },
            }
            result["issues"] = issues
        except Exception as exc:
            logger.warning("Phase 3 LLM analysis failed: %s", exc)
            result["phases"]["llm_analysis"] = {"error": str(exc)}

        # ── Phase 4: Create PRs for actionable issues ────────────────────
        pr_results: list[dict[str, Any]] = []
        actionable = [
            i for i in issues if i.get("severity") in ("critical", "improvement")
        ]

        if actionable:
            pr_count_today = await _get_pr_count_today(redis)
            remaining_budget = max(0, _MAX_PRS_PER_DAY - pr_count_today)

            if remaining_budget == 0:
                logger.info("PR daily limit reached (%d) — skipping PR creation", _MAX_PRS_PER_DAY)
                result["phases"]["pr_creation"] = {"skipped": "daily_limit_reached"}
            else:
                to_process = actionable[:remaining_budget]
                for issue in to_process:
                    try:
                        pr = await _create_improvement_pr(issue)
                        pr_results.append(pr)
                    except Exception as exc:
                        logger.exception("PR creation failed for '%s'", issue.get("title"))
                        pr_results.append({
                            "success": False,
                            "title": issue.get("title", ""),
                            "reason": f"exception: {exc}",
                        })

                result["phases"]["pr_creation"] = {
                    "actionable_issues": len(actionable),
                    "budget_remaining": remaining_budget,
                    "attempted": len(to_process),
                    "succeeded": sum(1 for p in pr_results if p.get("success")),
                }
        else:
            result["phases"]["pr_creation"] = {"actionable_issues": 0}

        result["prs"] = pr_results

        # ── Phase 5: Update health metrics ───────────────────────────────
        try:
            await _update_health_metrics(redis, len(log_errors), issues, pr_results)
            result["phases"]["metrics"] = {"updated": True}
        except Exception as exc:
            logger.warning("Phase 5 metrics update failed: %s", exc)
            result["phases"]["metrics"] = {"error": str(exc)}

        # Store last review timestamp
        try:
            await redis.cache_set(
                _KEY_LAST_REVIEW,
                json.dumps({"timestamp": now.isoformat(), "status": result["status"]}, default=str),
                ttl=_REVIEW_TTL,
            )
        except Exception:
            pass

        logger.info(
            "Code review cycle complete: %d issues found, %d PRs created",
            len(issues),
            sum(1 for p in pr_results if p.get("success")),
        )

    except Exception as exc:
        logger.exception("Code review cycle crashed: %s", exc)
        result["status"] = "error"
        result["error"] = str(exc)

    finally:
        await _release_lock(redis)

    return result


# ═══════════════════════════════════════════════════════════════════════════
# On-demand health report
# ═══════════════════════════════════════════════════════════════════════════

async def get_code_health_report() -> dict[str, Any]:
    """Return the latest code health metrics from Redis."""
    redis = await get_redis_client()
    report: dict[str, Any] = {
        "timestamp": datetime.now(tz=_MTN).isoformat(),
    }

    # Cumulative health metrics
    raw = await redis.cache_get(_KEY_HEALTH)
    if raw:
        report["metrics"] = json.loads(raw)
    else:
        report["metrics"] = None

    # Last review info
    raw = await redis.cache_get(_KEY_LAST_REVIEW)
    if raw:
        report["last_review"] = json.loads(raw)
    else:
        report["last_review"] = None

    # Today's PR count
    report["prs_today"] = await _get_pr_count_today(redis)
    report["pr_budget_remaining"] = max(0, _MAX_PRS_PER_DAY - report["prs_today"])

    return report
