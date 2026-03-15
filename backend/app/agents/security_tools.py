"""
Ethical OSINT and security assessment tools for J.A.R.V.I.S.

ALL tools are for educational, consented purposes only. Every tool:
  - Requires explicit confirmation in the tool response
  - Logs all actions for transparency
  - Only works on user-owned systems/domains
  - Includes clear disclaimers

Uses the same BaseTool pattern from ``app.agents.tools``.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import shlex
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Optional

from app.agents.state import AgentState
from app.agents.tools import BaseTool

logger = logging.getLogger("jarvis.security_tools")


# ═════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════

def _is_private_ip(ip: str) -> bool:
    """Check if an IP address is in a private range (safe to scan)."""
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private
    except ValueError:
        # Could be a CIDR range
        try:
            network = ipaddress.ip_network(ip, strict=False)
            return network.is_private
        except ValueError:
            return False


_KALI_WHITELIST = frozenset({
    "nmap", "whois", "dig", "nslookup", "traceroute", "ping", "curl", "wget",
    "nikto", "gobuster", "dirb", "sqlmap", "wpscan", "enum4linux",
    "hydra", "john", "hashcat", "aircrack-ng",  # only in isolated lab mode
})


def _validate_kali_command(command: str) -> tuple[bool, str]:
    """Validate a command against the whitelist. Returns (allowed, reason)."""
    if not command or not command.strip():
        return False, "Empty command provided."

    # Parse the first token as the tool name
    try:
        parts = shlex.split(command)
    except ValueError:
        return False, "Malformed command — unable to parse."

    if not parts:
        return False, "Empty command after parsing."

    tool_name = parts[0].split("/")[-1]  # handle /usr/bin/nmap etc.

    if tool_name not in _KALI_WHITELIST:
        return False, (
            f"Tool '{tool_name}' is not in the allowed whitelist. "
            f"Permitted tools: {', '.join(sorted(_KALI_WHITELIST))}"
        )

    # Block shell metacharacters that could enable command injection
    dangerous_chars = {";", "&&", "||", "|", "`", "$(", ">{", ">>"}
    for char in dangerous_chars:
        if char in command:
            return False, (
                f"Command contains disallowed shell metacharacter '{char}'. "
                "For security, only simple single-command invocations are permitted."
            )

    return True, "Command validated."


def _get_user_id(state: Optional[AgentState]) -> str:
    """Extract user_id from agent state for logging."""
    return (state or {}).get("user_id", "unknown")


# ═════════════════════════════════════════════════════════════════════════
# Tool 1: WHOIS Lookup
# ═════════════════════════════════════════════════════════════════════════

class WhoisLookupTool(BaseTool):
    """Look up public WHOIS registration data for a domain."""

    name = "whois_lookup"
    description = (
        "Look up publicly available WHOIS registration data for a domain. "
        "Returns registrar, creation/expiration dates, name servers, and "
        "registrant information. Params: domain (str)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        domain = params.get("domain", "").strip()
        if not domain:
            return "No domain provided. Please specify a domain (e.g. 'example.com')."

        user_id = _get_user_id(state)
        logger.info("SECURITY_AUDIT: whois_lookup on %s by user=%s", domain, user_id)

        try:
            import whois
        except ImportError:
            return (
                "The 'python-whois' library is not installed. "
                "Install it with: pip install python-whois"
            )

        try:
            w = whois.whois(domain)
        except Exception as exc:
            return f"WHOIS lookup failed for '{domain}': {exc}"

        # Build response
        lines: list[str] = [
            f"WHOIS Results for {domain}",
            "=" * 50,
        ]

        def _fmt(value: Any) -> str:
            if isinstance(value, list):
                return ", ".join(str(v) for v in value)
            if isinstance(value, datetime):
                return value.strftime("%Y-%m-%d %H:%M:%S UTC")
            return str(value) if value else "N/A"

        fields = [
            ("Registrar", w.registrar),
            ("Creation Date", w.creation_date),
            ("Expiration Date", w.expiration_date),
            ("Updated Date", w.updated_date),
            ("Name Servers", w.name_servers),
            ("Status", w.status),
            ("Registrant", w.get("name") if hasattr(w, "get") else getattr(w, "name", None)),
            ("Org", getattr(w, "org", None)),
            ("Country", getattr(w, "country", None)),
            ("State", getattr(w, "state", None)),
            ("DNSSEC", getattr(w, "dnssec", None)),
        ]

        for label, value in fields:
            if value is not None:
                lines.append(f"  {label}: {_fmt(value)}")

        lines.append("")
        lines.append(
            "Disclaimer: This information is publicly available via the WHOIS protocol. "
            "No private data was accessed."
        )

        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Tool 2: DNS Reconnaissance
# ═════════════════════════════════════════════════════════════════════════

_DNS_RECORD_DESCRIPTIONS: dict[str, str] = {
    "A": "IPv4 address — maps the domain to a server IP",
    "AAAA": "IPv6 address — maps the domain to an IPv6 server IP",
    "MX": "Mail Exchange — mail servers that handle email for this domain",
    "NS": "Name Server — authoritative DNS servers for this domain",
    "TXT": "Text records — often used for SPF, DKIM, domain verification",
    "CNAME": "Canonical Name — alias pointing to another domain",
    "SOA": "Start of Authority — primary NS, admin contact, serial number",
}


class DnsReconTool(BaseTool):
    """Enumerate DNS records for a domain with educational context."""

    name = "dns_recon"
    description = (
        "Enumerate DNS records for a domain. Returns A, AAAA, MX, NS, TXT, "
        "CNAME, and SOA records with educational explanations. "
        "Params: domain (str), record_types? (list of str)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        domain = params.get("domain", "").strip()
        if not domain:
            return "No domain provided. Please specify a domain (e.g. 'example.com')."

        record_types = params.get(
            "record_types",
            ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"],
        )

        user_id = _get_user_id(state)
        logger.info("SECURITY_AUDIT: dns_recon on %s by user=%s", domain, user_id)

        try:
            import dns.resolver
        except ImportError:
            return (
                "The 'dnspython' library is not installed. "
                "Install it with: pip install dnspython"
            )

        lines: list[str] = [
            f"DNS Reconnaissance for {domain}",
            "=" * 50,
        ]

        for rtype in record_types:
            rtype_upper = rtype.upper()
            desc = _DNS_RECORD_DESCRIPTIONS.get(rtype_upper, "DNS record")
            lines.append(f"\n--- {rtype_upper} Records ({desc}) ---")

            try:
                answers = dns.resolver.resolve(domain, rtype_upper)
                for rdata in answers:
                    lines.append(f"  {rdata.to_text()}")
            except dns.resolver.NoAnswer:
                lines.append("  (no records found)")
            except dns.resolver.NXDOMAIN:
                lines.append(f"  Domain '{domain}' does not exist (NXDOMAIN).")
                break
            except dns.resolver.NoNameservers:
                lines.append("  (no nameservers available)")
            except Exception as exc:
                lines.append(f"  Error querying {rtype_upper}: {exc}")

        lines.append("")
        lines.append(
            "Note: All DNS records are public information queryable by anyone. "
            "This is equivalent to running 'dig' or 'nslookup'."
        )

        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Tool 3: Web Reconnaissance (Passive)
# ═════════════════════════════════════════════════════════════════════════

_SECURITY_HEADERS = [
    "strict-transport-security",
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "x-xss-protection",
    "referrer-policy",
    "permissions-policy",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
]

_HEADER_RECOMMENDATIONS: dict[str, str] = {
    "strict-transport-security": (
        "HSTS — Forces HTTPS connections. Recommended: "
        "'max-age=31536000; includeSubDomains; preload'"
    ),
    "content-security-policy": (
        "CSP — Controls which resources can load. Essential for XSS prevention."
    ),
    "x-frame-options": (
        "Prevents clickjacking by controlling iframe embedding. "
        "Recommended: 'DENY' or 'SAMEORIGIN'"
    ),
    "x-content-type-options": (
        "Prevents MIME-type sniffing. Recommended: 'nosniff'"
    ),
    "x-xss-protection": (
        "Legacy XSS filter (modern browsers use CSP instead). "
        "Recommended: '0' (defer to CSP)"
    ),
    "referrer-policy": (
        "Controls referrer information sent with requests. "
        "Recommended: 'strict-origin-when-cross-origin'"
    ),
    "permissions-policy": (
        "Controls which browser features the site can use "
        "(camera, microphone, geolocation, etc.)."
    ),
    "cross-origin-opener-policy": (
        "Isolates browsing context for Spectre/Meltdown mitigation. "
        "Recommended: 'same-origin'"
    ),
    "cross-origin-resource-policy": (
        "Controls which origins can load this resource. "
        "Recommended: 'same-origin' or 'cross-origin' as needed."
    ),
}


class WebReconTool(BaseTool):
    """Passive web reconnaissance — analyse public HTTP responses."""

    name = "web_recon"
    description = (
        "Passively analyse a website's public HTTP response: security headers, "
        "server technology, SSL certificate info, robots.txt/sitemap.xml presence. "
        "No intrusive testing is performed. Params: url (str)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        import httpx

        url = params.get("url", "").strip()
        if not url:
            return "No URL provided. Please specify a URL (e.g. 'https://example.com')."

        # Ensure scheme
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        user_id = _get_user_id(state)
        logger.info("SECURITY_AUDIT: web_recon on %s by user=%s", url, user_id)

        lines: list[str] = [
            f"Web Reconnaissance for {url}",
            "=" * 50,
        ]

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=15.0,
                verify=True,
            ) as client:
                resp = await client.get(url)
        except httpx.ConnectError as exc:
            return f"Connection failed to {url}: {exc}"
        except httpx.TimeoutException:
            return f"Request to {url} timed out after 15 seconds."
        except Exception as exc:
            return f"Failed to fetch {url}: {exc}"

        # --- HTTP Status ---
        lines.append(f"\n--- HTTP Response ---")
        lines.append(f"  Status: {resp.status_code} {resp.reason_phrase}")
        lines.append(f"  Final URL: {resp.url}")

        # --- Server & Technology ---
        lines.append(f"\n--- Server & Technology ---")
        server = resp.headers.get("server", "Not disclosed")
        lines.append(f"  Server: {server}")
        powered_by = resp.headers.get("x-powered-by")
        if powered_by:
            lines.append(f"  X-Powered-By: {powered_by}")
        via = resp.headers.get("via")
        if via:
            lines.append(f"  Via: {via}")

        # --- Security Headers ---
        lines.append(f"\n--- Security Headers ---")
        present_count = 0
        missing: list[str] = []

        for header in _SECURITY_HEADERS:
            value = resp.headers.get(header)
            if value:
                present_count += 1
                lines.append(f"  [PRESENT] {header}: {value}")
            else:
                missing.append(header)
                lines.append(f"  [MISSING] {header}")

        total = len(_SECURITY_HEADERS)
        score_pct = (present_count / total) * 100 if total else 0
        lines.append(f"\n  Security Header Score: {present_count}/{total} ({score_pct:.0f}%)")

        # --- Recommendations for missing headers ---
        if missing:
            lines.append(f"\n--- Recommendations ---")
            for header in missing:
                rec = _HEADER_RECOMMENDATIONS.get(header, "Consider adding this header.")
                lines.append(f"  {header}: {rec}")

        # --- SSL Certificate Info ---
        lines.append(f"\n--- SSL/TLS ---")
        if str(resp.url).startswith("https"):
            try:
                from urllib.parse import urlparse
                parsed = urlparse(str(resp.url))
                hostname = parsed.hostname or ""
                port = parsed.port or 443

                import asyncio
                cert_info = await asyncio.to_thread(
                    _get_ssl_cert_info, hostname, port
                )
                for line in cert_info:
                    lines.append(f"  {line}")
            except Exception as exc:
                lines.append(f"  Could not retrieve SSL certificate: {exc}")
        else:
            lines.append("  WARNING: Site is not using HTTPS!")

        # --- robots.txt & sitemap.xml ---
        lines.append(f"\n--- Auxiliary Files ---")
        from urllib.parse import urljoin

        for path in ["/robots.txt", "/sitemap.xml"]:
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=10.0,
                ) as client:
                    check = await client.get(urljoin(url, path))
                if check.status_code == 200:
                    preview = check.text[:200].replace("\n", " ")
                    lines.append(f"  {path}: Found ({len(check.text)} bytes) — {preview}...")
                else:
                    lines.append(f"  {path}: Not found (HTTP {check.status_code})")
            except Exception:
                lines.append(f"  {path}: Could not check")

        lines.append("")
        lines.append(
            "Note: This analysis is purely passive — only publicly accessible "
            "responses were examined. No intrusive testing was performed."
        )

        return "\n".join(lines)


def _get_ssl_cert_info(hostname: str, port: int = 443) -> list[str]:
    """Retrieve SSL certificate details (runs in a thread)."""
    import socket

    ctx = ssl.create_default_context()
    lines: list[str] = []

    try:
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    return ["No certificate returned."]

                subject = dict(x[0] for x in cert.get("subject", ()))
                issuer = dict(x[0] for x in cert.get("issuer", ()))

                lines.append(f"Subject: {subject.get('commonName', 'N/A')}")
                lines.append(f"Issuer: {issuer.get('organizationName', 'N/A')} ({issuer.get('commonName', '')})")
                lines.append(f"Not Before: {cert.get('notBefore', 'N/A')}")
                lines.append(f"Not After: {cert.get('notAfter', 'N/A')}")

                # SANs
                sans = cert.get("subjectAltName", ())
                if sans:
                    san_list = [v for _, v in sans[:10]]
                    lines.append(f"SANs: {', '.join(san_list)}")
                    if len(sans) > 10:
                        lines.append(f"  ... and {len(sans) - 10} more")

                lines.append(f"Serial: {cert.get('serialNumber', 'N/A')}")
                lines.append(f"Version: {cert.get('version', 'N/A')}")
    except Exception as exc:
        lines.append(f"SSL connection error: {exc}")

    return lines


# ═════════════════════════════════════════════════════════════════════════
# Tool 4: Password Strength Checker
# ═════════════════════════════════════════════════════════════════════════

class PasswordStrengthTool(BaseTool):
    """Evaluate password strength without storing or logging the password."""

    name = "password_strength"
    description = (
        "Evaluate the strength of a password. Returns a score (0-4), "
        "estimated crack time, and improvement suggestions. "
        "The password is NEVER stored or logged. Params: password (str)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        password = params.get("password", "")
        if not password:
            return "No password provided for strength evaluation."

        user_id = _get_user_id(state)
        # NEVER log the actual password — only that the tool was invoked
        logger.info(
            "SECURITY_AUDIT: password_strength check by user=%s (password NOT logged)",
            user_id,
        )

        # Try zxcvbn first, fall back to basic analysis
        try:
            import zxcvbn
            result = zxcvbn.zxcvbn(password)
            return self._format_zxcvbn_result(result)
        except ImportError:
            return self._basic_strength_check(password)

    @staticmethod
    def _format_zxcvbn_result(result: dict[str, Any]) -> str:
        """Format a zxcvbn result into a readable report."""
        score = result.get("score", 0)
        crack_times = result.get("crack_times_display", {})
        feedback = result.get("feedback", {})

        score_labels = ["Very Weak", "Weak", "Fair", "Strong", "Very Strong"]
        label = score_labels[score] if score < len(score_labels) else "Unknown"

        lines: list[str] = [
            "Password Strength Analysis",
            "=" * 50,
            f"  Score: {score}/4 — {label}",
            "",
            "--- Crack Time Estimates ---",
            f"  Online (throttled): {crack_times.get('online_throttling_100_per_hour', 'N/A')}",
            f"  Online (unthrottled): {crack_times.get('online_no_throttling_10_per_second', 'N/A')}",
            f"  Offline (slow hash): {crack_times.get('offline_slow_hashing_1e4_per_second', 'N/A')}",
            f"  Offline (fast hash): {crack_times.get('offline_fast_hashing_1e10_per_second', 'N/A')}",
        ]

        warning = feedback.get("warning", "")
        suggestions = feedback.get("suggestions", [])

        if warning:
            lines.append(f"\n  Warning: {warning}")

        if suggestions:
            lines.append("\n--- Suggestions ---")
            for s in suggestions:
                lines.append(f"  - {s}")

        # Patterns detected
        sequence = result.get("sequence", [])
        if sequence:
            lines.append("\n--- Patterns Detected ---")
            for match in sequence:
                pattern = match.get("pattern", "unknown")
                token = match.get("token", "")
                # Mask the token for privacy
                masked = token[0] + "*" * (len(token) - 2) + token[-1] if len(token) > 2 else "**"
                lines.append(f"  Pattern: {pattern} — '{masked}'")

        lines.append("")
        lines.append(
            "Note: Your password was analysed locally and was NOT stored or logged."
        )

        return "\n".join(lines)

    @staticmethod
    def _basic_strength_check(password: str) -> str:
        """Fallback strength checker when zxcvbn is not installed."""
        import re
        import string

        length = len(password)
        has_upper = bool(re.search(r"[A-Z]", password))
        has_lower = bool(re.search(r"[a-z]", password))
        has_digit = bool(re.search(r"\d", password))
        has_special = bool(re.search(r"[^A-Za-z0-9]", password))

        # Calculate score (0-4)
        score = 0
        if length >= 8:
            score += 1
        if length >= 12:
            score += 1
        if has_upper and has_lower:
            score += 0.5
        if has_digit:
            score += 0.5
        if has_special:
            score += 0.5
        if length >= 16:
            score += 0.5

        score = min(4, int(score))
        score_labels = ["Very Weak", "Weak", "Fair", "Strong", "Very Strong"]
        label = score_labels[score]

        # Estimate crack time (very rough)
        charset_size = 0
        if has_lower:
            charset_size += 26
        if has_upper:
            charset_size += 26
        if has_digit:
            charset_size += 10
        if has_special:
            charset_size += 32
        charset_size = max(charset_size, 26)

        combinations = charset_size ** length
        # Assume 10 billion guesses/sec for offline fast hash
        seconds = combinations / 1e10
        if seconds < 60:
            crack_time = f"{seconds:.1f} seconds"
        elif seconds < 3600:
            crack_time = f"{seconds / 60:.1f} minutes"
        elif seconds < 86400:
            crack_time = f"{seconds / 3600:.1f} hours"
        elif seconds < 31536000:
            crack_time = f"{seconds / 86400:.1f} days"
        else:
            crack_time = f"{seconds / 31536000:.1f} years"

        suggestions: list[str] = []
        if length < 12:
            suggestions.append("Use at least 12 characters.")
        if not has_upper:
            suggestions.append("Add uppercase letters.")
        if not has_lower:
            suggestions.append("Add lowercase letters.")
        if not has_digit:
            suggestions.append("Add numbers.")
        if not has_special:
            suggestions.append("Add special characters (!@#$%^&*).")
        if length < 16:
            suggestions.append("Consider a passphrase of 16+ characters for maximum security.")

        lines: list[str] = [
            "Password Strength Analysis (basic mode — install 'zxcvbn' for deeper analysis)",
            "=" * 50,
            f"  Score: {score}/4 — {label}",
            f"  Length: {length} characters",
            f"  Character types: "
            f"{'upper ' if has_upper else ''}"
            f"{'lower ' if has_lower else ''}"
            f"{'digits ' if has_digit else ''}"
            f"{'special' if has_special else ''}",
            f"  Estimated crack time (offline fast hash): {crack_time}",
        ]

        if suggestions:
            lines.append("\n--- Suggestions ---")
            for s in suggestions:
                lines.append(f"  - {s}")

        lines.append("")
        lines.append(
            "Note: Your password was analysed locally and was NOT stored or logged."
        )

        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Tool 5: Network Scanner (Private Networks Only)
# ═════════════════════════════════════════════════════════════════════════

class NetworkScanTool(BaseTool):
    """Scan local/private network devices using nmap via Mac Mini."""

    name = "network_scan"
    description = (
        "Scan network devices on a private/local network using nmap. "
        "ONLY works on private IP ranges (10.x, 172.16-31.x, 192.168.x). "
        "Requires Mac Mini connectivity. "
        "Params: target (str — IP or CIDR), scan_type? (str — 'quick' or 'detailed')."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        target = params.get("target", "").strip()
        scan_type = params.get("scan_type", "quick").strip().lower()

        if not target:
            return "No target provided. Specify an IP or CIDR range (e.g. '192.168.1.0/24')."

        user_id = _get_user_id(state)
        logger.info(
            "SECURITY_AUDIT: network_scan (%s) on %s by user=%s",
            scan_type, target, user_id,
        )

        # Validate private IP range
        # Extract the base IP from CIDR notation for validation
        base_ip = target.split("/")[0].strip()
        if not _is_private_ip(base_ip):
            return (
                f"REJECTED: '{target}' is not a private IP range. "
                "For safety, network scanning is restricted to private networks only:\n"
                "  - 10.0.0.0/8\n"
                "  - 172.16.0.0/12\n"
                "  - 192.168.0.0/16\n\n"
                "This tool must only be used on networks you own."
            )

        if scan_type not in ("quick", "detailed"):
            return "Invalid scan_type. Use 'quick' (host discovery) or 'detailed' (service detection)."

        # Check Mac Mini availability
        try:
            from app.integrations.mac_mini import remote_exec, is_configured
        except ImportError:
            return (
                "Mac Mini integration module not available. "
                "Network scanning requires the Mac Mini agent for local network access."
            )

        if not is_configured():
            return (
                "Mac Mini agent is not configured. Network scanning requires "
                "local network access via the Mac Mini. Please configure "
                "MAC_MINI_AGENT_URL and MAC_MINI_AGENT_KEY."
            )

        # Build nmap command
        if scan_type == "quick":
            command = f"nmap -sn {target}"
            description = "Host discovery scan (ping sweep)"
        else:
            command = f"nmap -sV -sC {target}"
            description = "Service version detection and default scripts"

        lines: list[str] = [
            f"Network Scan — {target}",
            "=" * 50,
            f"Consent Notice: This tool scans network devices. Only use on "
            f"networks you own. Proceeding with scan of {target}...",
            f"Scan Type: {scan_type} — {description}",
            f"Command: {command}",
            "",
        ]

        try:
            result = await remote_exec(command, timeout=120)
        except Exception as exc:
            return f"Network scan failed: {exc}"

        if result.get("success"):
            stdout = result.get("stdout", "").strip()
            lines.append("--- Scan Results ---")
            lines.append(stdout if stdout else "(no output)")
        else:
            stderr = result.get("stderr", "Unknown error")
            lines.append(f"Scan failed: {stderr}")
            lines.append(
                "Ensure nmap is installed on the Mac Mini: brew install nmap"
            )

        duration_ms = result.get("duration_ms", 0)
        lines.append(f"\nScan completed in {duration_ms}ms.")

        lines.append("")
        lines.append(
            "Educational context: nmap is the industry-standard network "
            "discovery tool used by security professionals. A 'quick' scan "
            "(-sn) performs host discovery only. A 'detailed' scan (-sV -sC) "
            "also detects running services and their versions."
        )

        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Tool 6: Kali Linux Tool Runner
# ═════════════════════════════════════════════════════════════════════════

class KaliToolTool(BaseTool):
    """Execute whitelisted security tools in an isolated Kali container."""

    name = "kali_tool"
    description = (
        "Execute a whitelisted security tool in an isolated Kali Linux Docker "
        "container on the Mac Mini. Allowed tools: nmap, whois, dig, nslookup, "
        "traceroute, ping, curl, wget, nikto, gobuster, and others. "
        "Params: command (str — full command), tool_name (str — tool being used)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        command = params.get("command", "").strip()
        tool_name = params.get("tool_name", "").strip()

        if not command:
            return "No command provided."
        if not tool_name:
            return "No tool_name provided. Specify which tool is being used."

        user_id = _get_user_id(state)
        logger.info(
            "SECURITY_AUDIT: kali_tool '%s' command='%s' by user=%s",
            tool_name, command, user_id,
        )

        # Validate command against whitelist
        allowed, reason = _validate_kali_command(command)
        if not allowed:
            return f"REJECTED: {reason}"

        # Check Mac Mini availability
        try:
            from app.integrations.mac_mini import remote_exec, is_configured
        except ImportError:
            return (
                "Mac Mini integration module not available. "
                "Kali tools require the Mac Mini agent with Docker."
            )

        if not is_configured():
            return (
                "Mac Mini agent is not configured. Kali tools require Docker "
                "running on the Mac Mini with a 'jarvis-kali' container.\n\n"
                "Setup instructions:\n"
                "  1. Install Docker on Mac Mini\n"
                "  2. docker pull kalilinux/kali-rolling\n"
                "  3. docker run -d --name jarvis-kali kalilinux/kali-rolling tail -f /dev/null\n"
                "  4. docker exec jarvis-kali apt update && apt install -y kali-tools-top10"
            )

        docker_command = f"docker exec jarvis-kali {command}"

        lines: list[str] = [
            f"Kali Tool Execution — {tool_name}",
            "=" * 50,
            f"Consent: Executing {tool_name} in isolated Kali container. "
            f"This is for educational purposes only.",
            f"Command: {command}",
            "",
        ]

        try:
            result = await remote_exec(docker_command, timeout=180)
        except Exception as exc:
            return f"Kali tool execution failed: {exc}"

        if result.get("success"):
            stdout = result.get("stdout", "").strip()
            lines.append("--- Output ---")
            # Truncate very long output
            if len(stdout) > 5000:
                lines.append(stdout[:5000])
                lines.append(f"\n... (output truncated, {len(stdout)} total bytes)")
            else:
                lines.append(stdout if stdout else "(no output)")
        else:
            stderr = result.get("stderr", "Unknown error")
            lines.append(f"Execution failed: {stderr}")
            if "No such container" in stderr:
                lines.append(
                    "\nThe 'jarvis-kali' Docker container is not running. "
                    "Start it with: docker start jarvis-kali"
                )
            elif "not found" in stderr.lower():
                lines.append(
                    f"\n'{tool_name}' may not be installed in the Kali container. "
                    f"Install it with: docker exec jarvis-kali apt install -y {tool_name}"
                )

        duration_ms = result.get("duration_ms", 0)
        lines.append(f"\nCompleted in {duration_ms}ms.")

        # Educational context per tool
        edu_context = _KALI_TOOL_EDUCATION.get(tool_name, "")
        if edu_context:
            lines.append(f"\n--- Educational Context ---")
            lines.append(edu_context)

        return "\n".join(lines)


_KALI_TOOL_EDUCATION: dict[str, str] = {
    "nmap": (
        "nmap (Network Mapper) is the most widely used network scanner. "
        "It discovers hosts, open ports, running services, and OS versions."
    ),
    "whois": (
        "WHOIS queries public domain registration databases to find "
        "registrar, owner, and nameserver information."
    ),
    "dig": (
        "dig (Domain Information Groper) queries DNS servers for records. "
        "More detailed than nslookup, it shows the full DNS response."
    ),
    "nslookup": (
        "nslookup queries DNS to resolve domain names to IP addresses "
        "and vice versa. Simpler than dig."
    ),
    "traceroute": (
        "traceroute maps the network path (hops) between you and a target, "
        "showing each router along the way and latency."
    ),
    "nikto": (
        "nikto is a web server scanner that checks for dangerous files, "
        "outdated versions, and configuration issues. Use only on servers you own."
    ),
    "gobuster": (
        "gobuster brute-forces directories, files, and subdomains on web servers. "
        "Use only on targets you have explicit permission to test."
    ),
    "curl": (
        "curl transfers data from or to a server using various protocols. "
        "In security contexts, it's used for testing APIs and web endpoints."
    ),
    "ping": (
        "ping sends ICMP echo requests to test host reachability and measure "
        "round-trip time."
    ),
}


# ═════════════════════════════════════════════════════════════════════════
# Tool 7: Security Audit (Orchestrator)
# ═════════════════════════════════════════════════════════════════════════

class SecurityAuditTool(BaseTool):
    """Orchestrate a comprehensive security audit using multiple tools."""

    name = "security_audit"
    description = (
        "Run a comprehensive security audit combining multiple tools. "
        "Types: 'website' (web_recon + dns_recon + whois), "
        "'network' (network_scan + port analysis), "
        "'password_policy' (evaluate a set of password rules). "
        "Params: target_type (str: 'website'|'network'|'password_policy'), target (str)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        target_type = params.get("target_type", "").strip().lower()
        target = params.get("target", "").strip()

        if not target_type:
            return "No target_type provided. Use 'website', 'network', or 'password_policy'."
        if not target:
            return "No target provided."

        user_id = _get_user_id(state)
        logger.info(
            "SECURITY_AUDIT: security_audit type=%s target=%s by user=%s",
            target_type, target, user_id,
        )

        if target_type == "website":
            return await self._audit_website(target, state)
        elif target_type == "network":
            return await self._audit_network(target, state)
        elif target_type == "password_policy":
            return await self._audit_password_policy(target, state)
        else:
            return (
                f"Unknown target_type '{target_type}'. "
                "Use 'website', 'network', or 'password_policy'."
            )

    async def _audit_website(
        self, target: str, state: Optional[AgentState]
    ) -> str:
        """Run a full website security audit."""
        lines: list[str] = [
            f"Comprehensive Website Security Audit",
            f"Target: {target}",
            "=" * 60,
            "This audit combines WHOIS, DNS, and web reconnaissance.",
            "All checks are passive and use only publicly available data.",
            "",
        ]

        # Determine domain from target
        domain = target
        for prefix in ("https://", "http://", "www."):
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
        domain = domain.rstrip("/").split("/")[0]

        findings: list[dict[str, str]] = []

        # 1. WHOIS
        lines.append("=" * 60)
        lines.append("PHASE 1: WHOIS Lookup")
        lines.append("=" * 60)
        whois_tool = WhoisLookupTool()
        whois_result = await whois_tool.execute(
            {"domain": domain}, state=state
        )
        lines.append(whois_result)
        lines.append("")

        # 2. DNS
        lines.append("=" * 60)
        lines.append("PHASE 2: DNS Reconnaissance")
        lines.append("=" * 60)
        dns_tool = DnsReconTool()
        dns_result = await dns_tool.execute(
            {"domain": domain}, state=state
        )
        lines.append(dns_result)
        lines.append("")

        # 3. Web Recon
        lines.append("=" * 60)
        lines.append("PHASE 3: Web Reconnaissance")
        lines.append("=" * 60)
        url = target if target.startswith(("http://", "https://")) else f"https://{target}"
        web_tool = WebReconTool()
        web_result = await web_tool.execute(
            {"url": url}, state=state
        )
        lines.append(web_result)
        lines.append("")

        # Summary
        lines.append("=" * 60)
        lines.append("AUDIT SUMMARY")
        lines.append("=" * 60)

        # Analyse results for severity
        severity_findings = self._extract_website_findings(
            whois_result, dns_result, web_result
        )
        for finding in severity_findings:
            severity = finding["severity"]
            tag = {"high": "[HIGH]", "medium": "[MEDIUM]", "low": "[LOW]", "info": "[INFO]"}.get(
                severity, "[INFO]"
            )
            lines.append(f"  {tag} {finding['message']}")

        if not severity_findings:
            lines.append("  No significant findings.")

        lines.append("")
        lines.append(
            "Disclaimer: This audit used only passive, non-intrusive techniques. "
            "All data gathered is publicly available. For a complete security "
            "assessment, consider professional penetration testing."
        )

        return "\n".join(lines)

    @staticmethod
    def _extract_website_findings(
        whois_result: str, dns_result: str, web_result: str
    ) -> list[dict[str, str]]:
        """Extract actionable findings from audit results."""
        findings: list[dict[str, str]] = []

        # Check for missing security headers
        if "[MISSING] strict-transport-security" in web_result:
            findings.append({
                "severity": "high",
                "message": "HSTS header missing — site vulnerable to SSL stripping attacks.",
            })
        if "[MISSING] content-security-policy" in web_result:
            findings.append({
                "severity": "high",
                "message": "CSP header missing — increased XSS risk.",
            })
        if "[MISSING] x-frame-options" in web_result:
            findings.append({
                "severity": "medium",
                "message": "X-Frame-Options missing — potential clickjacking vulnerability.",
            })
        if "[MISSING] x-content-type-options" in web_result:
            findings.append({
                "severity": "medium",
                "message": "X-Content-Type-Options missing — MIME sniffing possible.",
            })

        # Check for exposed server info
        if "X-Powered-By:" in web_result:
            findings.append({
                "severity": "low",
                "message": "X-Powered-By header exposes backend technology — consider removing.",
            })

        # Check HTTP vs HTTPS
        if "not using HTTPS" in web_result.lower():
            findings.append({
                "severity": "high",
                "message": "Site is not using HTTPS — all traffic is unencrypted.",
            })

        # Check WHOIS expiration
        if "Expiration Date:" in whois_result:
            # Simple check — more sophisticated parsing could be added
            findings.append({
                "severity": "info",
                "message": "Domain registration found — verify expiration date is well in the future.",
            })

        return findings

    async def _audit_network(
        self, target: str, state: Optional[AgentState]
    ) -> str:
        """Run a network security audit."""
        lines: list[str] = [
            f"Comprehensive Network Security Audit",
            f"Target: {target}",
            "=" * 60,
            "This audit scans the local network for active hosts and services.",
            "Only use on networks you own.",
            "",
        ]

        # Quick scan first
        lines.append("=" * 60)
        lines.append("PHASE 1: Host Discovery")
        lines.append("=" * 60)
        scan_tool = NetworkScanTool()
        quick_result = await scan_tool.execute(
            {"target": target, "scan_type": "quick"}, state=state
        )
        lines.append(quick_result)
        lines.append("")

        # Summary
        lines.append("=" * 60)
        lines.append("AUDIT SUMMARY")
        lines.append("=" * 60)

        if "REJECTED" in quick_result:
            lines.append("  Scan was rejected — target is not a private IP range.")
        elif "not configured" in quick_result.lower():
            lines.append("  Mac Mini agent not available — cannot scan local network.")
        else:
            lines.append(
                "  Host discovery complete. To perform deeper analysis "
                "(service detection, version scanning), run a 'detailed' scan "
                "on specific hosts of interest."
            )

        lines.append("")
        lines.append(
            "Disclaimer: Network scanning should only be performed on networks "
            "you own or have explicit written permission to test."
        )

        return "\n".join(lines)

    async def _audit_password_policy(
        self, target: str, state: Optional[AgentState]
    ) -> str:
        """Evaluate a password policy described in the target string."""
        lines: list[str] = [
            "Password Policy Security Audit",
            "=" * 60,
            f"Policy Description: {target}",
            "",
        ]

        # Parse common policy attributes from the target description
        target_lower = target.lower()

        findings: list[dict[str, str]] = []

        # Check minimum length
        import re

        length_match = re.search(r"(\d+)\s*(?:char|character|min)", target_lower)
        if length_match:
            min_len = int(length_match.group(1))
            if min_len < 8:
                findings.append({
                    "severity": "high",
                    "message": f"Minimum length {min_len} is too short. NIST recommends at least 8, ideally 12+.",
                })
            elif min_len < 12:
                findings.append({
                    "severity": "medium",
                    "message": f"Minimum length {min_len} is acceptable but 12+ is recommended.",
                })
            else:
                findings.append({
                    "severity": "info",
                    "message": f"Minimum length {min_len} meets modern security standards.",
                })
        else:
            findings.append({
                "severity": "medium",
                "message": "No minimum length requirement detected — ensure one is enforced.",
            })

        # Check for complexity requirements
        if "special" in target_lower or "symbol" in target_lower:
            findings.append({
                "severity": "info",
                "message": "Special character requirement found. Modern guidance (NIST SP 800-63B) "
                           "suggests LENGTH over complexity, but special characters help.",
            })

        if "uppercase" in target_lower and "lowercase" in target_lower:
            findings.append({
                "severity": "info",
                "message": "Mixed case requirement found.",
            })

        # Check for bad practices
        if "rotate" in target_lower or "expir" in target_lower or "90 day" in target_lower:
            findings.append({
                "severity": "medium",
                "message": "Forced password rotation detected. NIST SP 800-63B recommends "
                           "AGAINST periodic rotation — it leads to weaker passwords. "
                           "Only require changes when compromise is suspected.",
            })

        if "mfa" in target_lower or "2fa" in target_lower or "multi-factor" in target_lower:
            findings.append({
                "severity": "info",
                "message": "MFA/2FA requirement found — excellent. This is the single most "
                           "impactful security measure for authentication.",
            })
        else:
            findings.append({
                "severity": "high",
                "message": "No MFA/2FA requirement detected. Multi-factor authentication "
                           "is strongly recommended for all accounts.",
            })

        # Check for breach checking
        if "breach" in target_lower or "hibp" in target_lower or "compromised" in target_lower:
            findings.append({
                "severity": "info",
                "message": "Password breach checking detected — good practice.",
            })
        else:
            findings.append({
                "severity": "low",
                "message": "Consider checking passwords against known breach databases "
                           "(e.g. HaveIBeenPwned) to prevent use of compromised passwords.",
            })

        # Output findings
        lines.append("--- Findings ---")
        for finding in findings:
            severity = finding["severity"]
            tag = {"high": "[HIGH]", "medium": "[MEDIUM]", "low": "[LOW]", "info": "[INFO]"}.get(
                severity, "[INFO]"
            )
            lines.append(f"  {tag} {finding['message']}")

        lines.append("")
        lines.append("--- NIST SP 800-63B Key Recommendations ---")
        lines.append("  - Minimum 8 characters (12+ recommended)")
        lines.append("  - Maximum at least 64 characters")
        lines.append("  - No composition rules (uppercase/special required)")
        lines.append("  - No periodic rotation (only on suspected compromise)")
        lines.append("  - Check against breach databases")
        lines.append("  - Require MFA for all users")
        lines.append("  - Allow paste in password fields")
        lines.append("  - Use a password strength meter")

        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Registry
# ═════════════════════════════════════════════════════════════════════════

def get_security_tools() -> dict[str, BaseTool]:
    """Return a name -> tool mapping for all security tools."""
    tools = [
        WhoisLookupTool(),
        DnsReconTool(),
        WebReconTool(),
        PasswordStrengthTool(),
        NetworkScanTool(),
        KaliToolTool(),
        SecurityAuditTool(),
    ]
    return {t.name: t for t in tools}
