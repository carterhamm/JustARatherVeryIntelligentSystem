"""
MCP Server Auto-Discovery for J.A.R.V.I.S.

Searches GitHub and curated lists for Model Context Protocol (MCP) servers,
evaluates them for capability, quality, and compatibility, and caches results
in Redis with a 24-hour TTL.

GitHub public API (unauthenticated): 10 req/min rate limit.
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("jarvis.mcp_discovery")

# ═══════════════════════════════════════════════════════════════════════════
# Redis key constants
# ═══════════════════════════════════════════════════════════════════════════

_KEY_SCAN_RESULTS = "jarvis:mcp:scan_results"
_KEY_LAST_SCAN = "jarvis:mcp:last_scan"
_KEY_EVAL_PREFIX = "jarvis:mcp:eval"

_ONE_DAY = 24 * 60 * 60        # 24 hours in seconds
_ONE_WEEK = 7 * _ONE_DAY

# ═══════════════════════════════════════════════════════════════════════════
# Known trusted organisations / authors
# ═══════════════════════════════════════════════════════════════════════════

_TRUSTED_ORGS = {
    "anthropics", "anthropic",
    "modelcontextprotocol",
    "microsoft", "google", "openai",
    "github", "aws", "cloudflare",
    "stripe", "twilio", "notion-community",
    "vercel", "supabase",
}

# ═══════════════════════════════════════════════════════════════════════════
# Capability keyword mapping
# ═══════════════════════════════════════════════════════════════════════════

_CAPABILITY_KEYWORDS: dict[str, list[str]] = {
    "browser": ["browser", "playwright", "puppeteer", "selenium", "chromium", "web-automation"],
    "database": ["database", "postgres", "postgresql", "mysql", "sqlite", "mongodb", "redis", "sql"],
    "files": ["filesystem", "file-system", "local-files", "file-access", "fs"],
    "slack": ["slack"],
    "notion": ["notion"],
    "github": ["github", "git"],
    "email": ["gmail", "email", "mail", "smtp", "imap"],
    "calendar": ["calendar", "gcal", "google-calendar"],
    "linear": ["linear"],
    "jira": ["jira", "atlassian"],
    "shopify": ["shopify"],
    "stripe": ["stripe", "payment"],
    "aws": ["aws", "amazon", "s3", "lambda", "ec2"],
    "docker": ["docker", "container", "kubernetes", "k8s"],
    "maps": ["maps", "location", "geocoding", "places"],
    "memory": ["memory", "knowledge-graph", "vector", "embeddings", "rag"],
    "crypto": ["crypto", "blockchain", "ethereum", "solana"],
    "weather": ["weather", "forecast"],
    "news": ["news", "rss", "headlines"],
    "code": ["code-execution", "sandbox", "repl", "eval"],
    "pdf": ["pdf", "document", "docx"],
    "image": ["image", "vision", "screenshot", "ocr"],
    "time": ["time", "timezone", "clock", "calendar"],
    "twilio": ["twilio", "sms", "phone"],
    "hubspot": ["hubspot", "crm"],
    "salesforce": ["salesforce"],
    "confluence": ["confluence"],
    "discord": ["discord"],
    "twitter": ["twitter", "x.com"],
    "youtube": ["youtube", "video"],
}


def _detect_capabilities(name: str, description: str, topics: list[str]) -> list[str]:
    """Return a list of capability labels detected from repo metadata."""
    combined = f"{name} {description} {' '.join(topics)}".lower()
    detected: list[str] = []
    for cap, keywords in _CAPABILITY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            detected.append(cap)
    return detected


def _score_repo(repo: dict[str, Any]) -> float:
    """Compute a quality score (0–100) for a GitHub repo."""
    score = 0.0

    # Stars (logarithmic, capped at 30 points)
    stars = repo.get("stargazers_count", 0)
    if stars > 0:
        import math
        score += min(30.0, math.log10(stars + 1) * 12)

    # Recent activity (pushed_at within last 90 days = 20 pts, 1 yr = 10 pts)
    pushed_at = repo.get("pushed_at", "")
    if pushed_at:
        try:
            pushed_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            days_ago = (datetime.now(tz=timezone.utc) - pushed_dt).days
            if days_ago <= 30:
                score += 20.0
            elif days_ago <= 90:
                score += 15.0
            elif days_ago <= 365:
                score += 10.0
            else:
                score += 2.0
        except Exception:
            pass

    # Has description (5 pts)
    if repo.get("description"):
        score += 5.0

    # Has README / topics (5 pts)
    if repo.get("topics"):
        score += 5.0

    # Not archived (10 pts)
    if not repo.get("archived", False):
        score += 10.0

    # Trusted org (15 pts)
    owner = repo.get("owner", {}).get("login", "").lower()
    if owner in _TRUSTED_ORGS:
        score += 15.0

    # Has license (5 pts)
    if repo.get("license"):
        score += 5.0

    # Fork penalty (-5 pts)
    if repo.get("fork", False):
        score -= 5.0

    # Language preference: Python or TypeScript/JavaScript (5 pts)
    lang = (repo.get("language") or "").lower()
    if lang in ("python", "typescript", "javascript"):
        score += 5.0

    return round(max(0.0, min(100.0, score)), 1)


def _format_repo_entry(repo: dict[str, Any]) -> dict[str, Any]:
    """Normalise a raw GitHub repo dict into a clean MCP server entry."""
    topics = repo.get("topics", [])
    name = repo.get("name", "")
    description = repo.get("description") or ""
    capabilities = _detect_capabilities(name, description, topics)

    return {
        "name": name,
        "full_name": repo.get("full_name", ""),
        "url": repo.get("html_url", ""),
        "description": description,
        "stars": repo.get("stargazers_count", 0),
        "language": repo.get("language") or "Unknown",
        "topics": topics,
        "capabilities": capabilities,
        "owner": repo.get("owner", {}).get("login", ""),
        "pushed_at": repo.get("pushed_at", ""),
        "archived": repo.get("archived", False),
        "license": (repo.get("license") or {}).get("spdx_id", ""),
        "score": _score_repo(repo),
        "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# GitHub API helpers
# ═══════════════════════════════════════════════════════════════════════════

_GH_BASE = "https://api.github.com"
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "JARVIS-MCP-Discovery/1.0",
}


async def _gh_search(query: str, per_page: int = 30) -> list[dict[str, Any]]:
    """Run a GitHub repository search and return raw items."""
    import httpx

    url = f"{_GH_BASE}/search/repositories"
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": per_page,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("items", [])
            elif resp.status_code == 403:
                # Rate limited
                logger.warning("GitHub API rate limited (403) for query: %s", query)
                return []
            else:
                logger.warning("GitHub API returned %s for query '%s': %s",
                               resp.status_code, query, resp.text[:200])
                return []
    except Exception as exc:
        logger.error("GitHub API request failed for query '%s': %s", query, exc)
        return []


async def _gh_get_readme(full_name: str) -> str:
    """Fetch and decode the README for a repo (max 4KB)."""
    import httpx
    import base64

    url = f"{_GH_BASE}/repos/{full_name}/readme"
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                encoded = data.get("content", "")
                raw = base64.b64decode(encoded).decode("utf-8", errors="ignore")
                return raw[:4000]
    except Exception as exc:
        logger.debug("Failed to fetch README for %s: %s", full_name, exc)
    return ""


async def _gh_get_repo(full_name: str) -> Optional[dict[str, Any]]:
    """Fetch metadata for a single repo by full_name (owner/repo)."""
    import httpx

    url = f"{_GH_BASE}/repos/{full_name}"
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("GitHub get repo %s returned %s", full_name, resp.status_code)
    except Exception as exc:
        logger.error("Failed to get repo %s: %s", full_name, exc)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Curated list of well-known MCP servers (always included in scans)
# ═══════════════════════════════════════════════════════════════════════════

_CURATED_REPOS = [
    "modelcontextprotocol/servers",
    "executeautomation/mcp-playwright",
    "cloudflare/mcp-server-cloudflare",
    "stripe/agent-toolkit",
    "github/github-mcp-server",
    "microsoft/markitdown",
    "anthropics/anthropic-quickstarts",
]

# ═══════════════════════════════════════════════════════════════════════════
# Core discovery functions
# ═══════════════════════════════════════════════════════════════════════════


async def search_mcp_servers(query: str = "", limit: int = 15) -> list[dict[str, Any]]:
    """Search GitHub for MCP servers matching *query*.

    Returns a ranked list of MCP server entries (score desc).
    Results are NOT cached here — the caller decides.
    """
    searches: list[str] = []

    if query:
        # Specific query: search by topic + keyword
        searches.append(f"topic:mcp-server {query}")
        searches.append(f"topic:model-context-protocol {query}")
        searches.append(f"mcp-server {query} in:name,description,topics")
    else:
        # Generic scan: top MCP repos by topic
        searches.append("topic:mcp-server")
        searches.append("topic:model-context-protocol")

    seen: dict[str, dict[str, Any]] = {}

    for search_q in searches:
        items = await _gh_search(search_q, per_page=min(limit * 2, 50))
        for item in items:
            full_name = item.get("full_name", "")
            if full_name and full_name not in seen:
                seen[full_name] = _format_repo_entry(item)

        # Respect rate limit: 10 req/min = 6s gap minimum
        # We do two searches so add a small delay
        import asyncio
        await asyncio.sleep(1.0)

    # Sort by score desc
    results = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
    return results[:limit]


async def evaluate_mcp_server(repo_url: str) -> dict[str, Any]:
    """Deep-evaluate a specific MCP server repo.

    Fetches repo metadata + README, extracts tool list hints, and returns
    a structured evaluation report.  Results cached in Redis for 24 hours.
    """
    from app.db.redis import get_redis_client

    # Normalise URL → owner/repo
    full_name = _url_to_full_name(repo_url)
    if not full_name:
        return {"error": f"Cannot parse repo URL: {repo_url}"}

    # Check Redis cache first
    redis = await get_redis_client()
    cache_key = f"{_KEY_EVAL_PREFIX}:{full_name.replace('/', ':')}"
    cached = await redis.cache_get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    # Fetch repo + README
    repo_raw = await _gh_get_repo(full_name)
    if not repo_raw:
        return {"error": f"Repository not found or API error: {full_name}"}

    entry = _format_repo_entry(repo_raw)
    readme = await _gh_get_readme(full_name)

    # Extract tools/capabilities hint from README
    tool_hints = _extract_tool_hints(readme)
    entry["tool_hints"] = tool_hints
    entry["readme_excerpt"] = readme[:800] if readme else ""

    # Compatibility assessment
    entry["compatibility"] = _assess_compatibility(repo_raw, readme)

    # Security assessment
    entry["security"] = _assess_security(repo_raw)

    # Installation hints
    entry["install_hints"] = _extract_install_hints(readme)

    # Cache for 24 hours
    await redis.cache_set(cache_key, json.dumps(entry), ttl=_ONE_DAY)
    logger.info("Evaluated MCP server: %s (score=%.1f)", full_name, entry["score"])

    return entry


async def run_mcp_scan() -> dict[str, Any]:
    """Full weekly scan — searches top MCP servers across multiple topics.

    Stores a curated ranked list in Redis.  Designed to be called by cron.
    """
    from app.db.redis import get_redis_client

    scan_start = _time.perf_counter()
    logger.info("═══════════════════════════════════════════════════════")
    logger.info("MCP DISCOVERY SCAN: starting")
    logger.info("═══════════════════════════════════════════════════════")

    redis = await get_redis_client()

    all_servers: dict[str, dict[str, Any]] = {}

    # Phase 1: Broad topic searches
    broad_queries = [
        "",              # topic:mcp-server (all)
        "python",        # Python MCP servers
        "typescript",    # TS MCP servers
    ]

    for q in broad_queries:
        logger.info("Scanning: query='%s'", q or "(broad)")
        try:
            results = await search_mcp_servers(q, limit=20)
            for r in results:
                fn = r.get("full_name", "")
                if fn and fn not in all_servers:
                    all_servers[fn] = r
        except Exception as exc:
            logger.error("Scan query '%s' failed: %s", q, exc)

        import asyncio
        await asyncio.sleep(6.0)  # respect rate limit

    # Phase 2: Capability-specific searches (most useful categories)
    capability_queries = [
        "browser automation",
        "database sql",
        "memory knowledge",
        "slack discord",
        "notion",
        "github",
    ]

    for cq in capability_queries:
        logger.info("Scanning capability: '%s'", cq)
        try:
            results = await search_mcp_servers(cq, limit=10)
            for r in results:
                fn = r.get("full_name", "")
                if fn and fn not in all_servers:
                    all_servers[fn] = r
        except Exception as exc:
            logger.error("Capability scan '%s' failed: %s", cq, exc)

        await asyncio.sleep(6.0)

    # Phase 3: Include curated repos (fetch any we don't have yet)
    for full_name in _CURATED_REPOS:
        if full_name not in all_servers:
            logger.info("Fetching curated repo: %s", full_name)
            try:
                repo_raw = await _gh_get_repo(full_name)
                if repo_raw:
                    all_servers[full_name] = _format_repo_entry(repo_raw)
            except Exception as exc:
                logger.warning("Failed to fetch curated repo %s: %s", full_name, exc)
            await asyncio.sleep(1.0)

    # Sort all findings by score
    ranked = sorted(all_servers.values(), key=lambda x: x["score"], reverse=True)

    elapsed = _time.perf_counter() - scan_start
    result = {
        "status": "ok",
        "total_found": len(ranked),
        "scanned_at": datetime.now(tz=timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "servers": ranked[:100],  # store top 100
    }

    # Store in Redis for 24 hours
    await redis.cache_set(_KEY_SCAN_RESULTS, json.dumps(result), ttl=_ONE_DAY)
    await redis.cache_set(_KEY_LAST_SCAN, datetime.now(tz=timezone.utc).isoformat(), ttl=_ONE_WEEK)

    logger.info(
        "MCP SCAN COMPLETE: %d servers found in %.1fs",
        len(ranked), elapsed,
    )
    return result


async def get_cached_scan() -> Optional[dict[str, Any]]:
    """Return the last cached scan result, or None if not available."""
    from app.db.redis import get_redis_client

    redis = await get_redis_client()
    raw = await redis.cache_get(_KEY_SCAN_RESULTS)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return None


async def get_recommendations(current_tools: Optional[list[str]] = None) -> str:
    """Return AI-recommended MCP servers based on JARVIS's current capabilities.

    Compares current tool set against available MCP servers to suggest
    new capabilities that would genuinely extend JARVIS.
    """
    # Default known JARVIS tool names
    if current_tools is None:
        current_tools = [
            "search_knowledge", "send_email", "read_email", "send_jarvis_email",
            "create_calendar_event", "list_calendar_events", "set_reminder",
            "smart_home_control", "web_search", "weather", "news", "spotify",
            "calculator", "date_time", "google_drive", "slack", "github",
            "wolfram_alpha", "perplexity_research", "financial_data",
            "flight_tracker", "google_maps", "nutrition_recipe", "set_wake_time",
            "send_imessage", "sports", "scripture_lookup", "navigate",
            "mac_mini_exec", "mac_mini_claude_code", "mac_mini_screenshot",
            "health_summary", "research_briefing", "mcp_discovery",
        ]

    # Check cache first
    cached = await get_cached_scan()

    if not cached:
        # No scan yet — recommend running one
        return (
            "No MCP discovery scan has been run yet. "
            "Run `mcp_discovery` with action='search' or ask me to run a full scan "
            "to discover available MCP servers."
        )

    servers = cached.get("servers", [])
    if not servers:
        return "MCP scan completed but returned no results."

    # Find servers with capabilities not yet in JARVIS
    current_lower = {t.lower() for t in current_tools}
    gaps: list[dict[str, Any]] = []

    for srv in servers[:50]:
        caps = srv.get("capabilities", [])
        new_caps = [c for c in caps if c not in current_lower]
        if new_caps and not srv.get("archived", False):
            gaps.append({
                "name": srv["name"],
                "full_name": srv["full_name"],
                "url": srv["url"],
                "stars": srv["stars"],
                "score": srv["score"],
                "new_capabilities": new_caps,
                "description": srv.get("description", ""),
                "language": srv.get("language", ""),
            })

    if not gaps:
        return (
            "Based on the latest scan, JARVIS already covers most of the "
            "commonly available MCP server capabilities."
        )

    # Sort by score and take top 10
    gaps.sort(key=lambda x: x["score"], reverse=True)
    top = gaps[:10]

    lines = [
        f"Top {len(top)} MCP servers that would add new capabilities to JARVIS:\n"
    ]
    for i, srv in enumerate(top, 1):
        caps_str = ", ".join(srv["new_capabilities"])
        lines.append(
            f"{i}. {srv['full_name']} ({srv['stars']:,} ⭐, score {srv['score']})\n"
            f"   New capabilities: {caps_str}\n"
            f"   {srv['description']}\n"
            f"   URL: {srv['url']}\n"
            f"   Language: {srv['language']}"
        )

    scanned_at = cached.get("scanned_at", "unknown")
    lines.append(f"\n(Scan from: {scanned_at}, {cached.get('total_found', 0)} total servers indexed)")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Helper utilities
# ═══════════════════════════════════════════════════════════════════════════

def _url_to_full_name(url: str) -> Optional[str]:
    """Convert a GitHub URL or 'owner/repo' string to 'owner/repo'."""
    url = url.strip().rstrip("/")
    if url.startswith("https://github.com/"):
        parts = url.replace("https://github.com/", "").split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    elif url.startswith("github.com/"):
        parts = url.replace("github.com/", "").split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    elif "/" in url and not url.startswith("http"):
        # Assume owner/repo format
        parts = url.split("/")
        if len(parts) == 2:
            return url
    return None


def _extract_tool_hints(readme: str) -> list[str]:
    """Heuristically extract tool/function names mentioned in a README."""
    import re

    hints: list[str] = []
    readme_lower = readme.lower()

    # Look for 'tools:' or '## tools' or '### tools' sections
    tool_section_patterns = [
        r"#+\s*tools?\s*\n((?:.+\n?){1,20})",
        r"tools?:((?:.+\n?){1,10})",
        r"available tools?:((?:.+\n?){1,10})",
        r"capabilities:((?:.+\n?){1,10})",
    ]
    for pat in tool_section_patterns:
        m = re.search(pat, readme_lower, re.MULTILINE)
        if m:
            section = m.group(1)
            # Extract bullet items or backtick-quoted names
            items = re.findall(r"[-*]\s*`?([a-z_][a-z0-9_/\-]+)`?", section)
            hints.extend(items[:15])

    # Look for backtick-quoted identifiers that look like tool names
    backtick_names = re.findall(r"`([a-z_][a-z0-9_]{3,30})`", readme_lower)
    for name in backtick_names:
        if "_" in name or name.startswith("get_") or name.startswith("create_"):
            hints.append(name)

    return list(dict.fromkeys(hints))[:20]  # deduplicate, keep order


def _assess_compatibility(repo: dict[str, Any], readme: str) -> dict[str, Any]:
    """Return a compatibility summary."""
    lang = (repo.get("language") or "").lower()
    readme_lower = readme.lower()

    return {
        "language": repo.get("language") or "Unknown",
        "python_compatible": lang == "python" or "pip install" in readme_lower or "python" in readme_lower,
        "node_required": lang in ("typescript", "javascript") or "npm install" in readme_lower or "npx" in readme_lower,
        "docker_available": "docker" in readme_lower or "dockerfile" in readme_lower,
        "pip_install": "pip install" in readme_lower,
        "npm_install": "npm install" in readme_lower or "npx" in readme_lower,
    }


def _assess_security(repo: dict[str, Any]) -> dict[str, Any]:
    """Return a security trust summary."""
    owner = repo.get("owner", {}).get("login", "").lower()
    stars = repo.get("stargazers_count", 0)
    is_trusted_org = owner in _TRUSTED_ORGS
    has_license = bool(repo.get("license"))

    trust_level = "low"
    if is_trusted_org:
        trust_level = "high"
    elif stars >= 500 and has_license:
        trust_level = "medium"
    elif stars >= 50:
        trust_level = "low-medium"

    return {
        "owner": owner,
        "is_trusted_org": is_trusted_org,
        "stars": stars,
        "has_license": has_license,
        "trust_level": trust_level,
    }


def _extract_install_hints(readme: str) -> list[str]:
    """Extract installation command snippets from README."""
    import re

    hints: list[str] = []
    # Code blocks
    code_blocks = re.findall(r"```(?:bash|sh|shell|zsh)?\n(.*?)```", readme, re.DOTALL)
    for block in code_blocks[:5]:
        for line in block.strip().split("\n"):
            line = line.strip()
            if any(line.startswith(p) for p in ("pip ", "npm ", "npx ", "docker ", "uv ", "pipx ")):
                hints.append(line[:120])

    return hints[:6]
