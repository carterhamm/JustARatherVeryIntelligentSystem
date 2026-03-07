"""Authentication — 4-layer CLI access control.

Layer 1: Gate Username (static, local)
Layer 2: Gate Password (static, local)
Layer 3: Secure Handshake Token (verified server-side against SETUP_TOKEN)
Layer 4: JARVIS Username (server account lookup → JWT tokens)

First `jarvis login` sets layers 1-3 and creates/links the JARVIS account.
Every subsequent access requires all 4 layers.
"""

from __future__ import annotations

import getpass
import hashlib
import sys
import time
from typing import Optional

import httpx

from stark_jarvis.config import config, DEFAULT_SERVER, _get_salt

# ANSI colours — JARVIS blue palette
_BLUE = "\x1b[38;2;0;212;255m"
_RED = "\x1b[38;2;239;68;68m"
_GREEN = "\x1b[38;2;52;211;153m"
_DIM = "\x1b[2m"
_BOLD = "\x1b[1m"
_RESET = "\x1b[0m"

# Lockout config
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 900  # 15 minutes


def _hash_value(value: str) -> str:
    """Hash a credential with PBKDF2 for local storage/verification."""
    salt = _get_salt()
    return hashlib.pbkdf2_hmac("sha256", value.encode(), salt, iterations=100_000).hex()


def _check_lockout() -> None:
    """Check if the CLI is locked out from too many failures."""
    lockout_until = config.get("lockout_until")
    if lockout_until and time.time() < lockout_until:
        remaining = int(lockout_until - time.time())
        minutes = remaining // 60
        seconds = remaining % 60
        print(f"  {_RED}Access locked. Try again in {minutes}m {seconds}s.{_RESET}")
        sys.exit(1)


def _record_failure() -> None:
    """Record a failed attempt and enforce lockout."""
    attempts = config.get("failed_attempts", 0) + 1
    config.set("failed_attempts", attempts)
    if attempts >= _MAX_ATTEMPTS:
        config.set("lockout_until", time.time() + _LOCKOUT_SECONDS)
        config.set("failed_attempts", 0)
        print(f"  {_RED}Too many failed attempts. Locked for 15 minutes.{_RESET}")
        sys.exit(1)
    remaining = _MAX_ATTEMPTS - attempts
    print(f"  {_RED}Incorrect. {remaining} attempt(s) remaining.{_RESET}")


def _clear_failures() -> None:
    """Clear failure counter on success."""
    config.set("failed_attempts", 0)
    config.set("lockout_until", None)


def _get_api_url(path: str) -> str:
    """Build full API URL."""
    base = config.server_url or DEFAULT_SERVER
    return f"{base}/api/v1{path}"


def _verify_gate(prompt_label: str, stored_hash_key: str) -> bool:
    """Prompt for a gate credential and verify against stored hash."""
    value = getpass.getpass(f"  {_BLUE}{prompt_label}: {_RESET}")
    if not value:
        return False
    return _hash_value(value) == config.get(stored_hash_key)


def _server_cli_auth(sht: str, username: str) -> Optional[dict]:
    """Authenticate with the server via SHT + username. Returns response data or None."""
    try:
        resp = httpx.post(
            _get_api_url("/auth/cli-login"),
            json={"sht": sht, "username": username},
            timeout=15.0,
        )
        if resp.status_code == 200:
            return resp.json()
        detail = resp.json().get("detail", f"HTTP {resp.status_code}")
        print(f"  {_RED}{detail}{_RESET}")
        return None
    except httpx.ConnectError:
        print(f"  {_RED}Cannot reach server.{_RESET}")
        return None
    except Exception as exc:
        print(f"  {_RED}Server error: {exc}{_RESET}")
        return None


# ══════════════════════════════════════════════════════════════════════════
# First-time setup: `jarvis login`
# ══════════════════════════════════════════════════════════════════════════


def login(server_url: str, email: Optional[str] = None) -> None:
    """First-time setup or re-login. Sets gate credentials + SHT + links account."""
    config.server_url = server_url

    print(f"\n  {_BLUE}{_BOLD}╔══════════════════════════════════════╗{_RESET}")
    print(f"  {_BLUE}{_BOLD}║   Stark Secure Server — CLI Setup    ║{_RESET}")
    print(f"  {_BLUE}{_BOLD}╚══════════════════════════════════════╝{_RESET}")
    print(f"  {_DIM}Connecting to {server_url}{_RESET}\n")

    # Verify server is reachable
    try:
        resp = httpx.get(f"{server_url}/api/v1/auth/setup-status", timeout=10.0)
        resp.raise_for_status()
        setup_complete = resp.json().get("setup_complete", False)
    except httpx.ConnectError:
        print(f"  {_RED}Cannot reach server at {server_url}{_RESET}")
        sys.exit(1)
    except Exception:
        print(f"  {_RED}Server error.{_RESET}")
        sys.exit(1)

    # ── Step 1: Set gate credentials ──
    print(f"  {_BLUE}{_BOLD}Step 1:{_RESET} Set your CLI gate credentials")
    print(f"  {_DIM}These are static credentials that guard CLI access.{_RESET}\n")

    gate_user = input(f"  {_BLUE}Gate Username: {_RESET}").strip()
    if not gate_user:
        print(f"  {_RED}Username cannot be empty.{_RESET}")
        sys.exit(1)

    gate_pass = getpass.getpass(f"  {_BLUE}Gate Password: {_RESET}")
    if not gate_pass:
        print(f"  {_RED}Password cannot be empty.{_RESET}")
        sys.exit(1)
    gate_pass2 = getpass.getpass(f"  {_BLUE}Confirm Gate Password: {_RESET}")
    if gate_pass != gate_pass2:
        print(f"  {_RED}Passwords do not match.{_RESET}")
        sys.exit(1)

    # Store hashes
    config.set("gate_username_hash", _hash_value(gate_user))
    config.set("gate_password_hash", _hash_value(gate_pass))
    print(f"  {_GREEN}Gate credentials set.{_RESET}\n")

    # ── Step 2: Enter SHT ──
    print(f"  {_BLUE}{_BOLD}Step 2:{_RESET} Enter the Secure Handshake Token")
    print(f"  {_DIM}This is the server's SETUP_TOKEN. Same across site and CLI.{_RESET}\n")

    sht = getpass.getpass(f"  {_BLUE}Secure Handshake Token: {_RESET}")
    if not sht:
        print(f"  {_RED}SHT cannot be empty.{_RESET}")
        sys.exit(1)

    # Store SHT hash for local verification on subsequent logins
    config.set("sht_hash", _hash_value(sht))
    print(f"  {_GREEN}SHT stored.{_RESET}\n")

    # ── Step 3: Link or create JARVIS account ──
    print(f"  {_BLUE}{_BOLD}Step 3:{_RESET} Link your JARVIS account\n")

    if not setup_complete:
        # No account exists — create one
        print(f"  {_DIM}No owner account exists. Creating one now.{_RESET}\n")

        username = input(f"  {_BLUE}JARVIS Username: {_RESET}").strip()
        if not username or len(username) < 3:
            print(f"  {_RED}Username must be at least 3 characters.{_RESET}")
            sys.exit(1)

        acct_email = input(f"  {_BLUE}Email: {_RESET}").strip()
        if not acct_email or "@" not in acct_email:
            print(f"  {_RED}Invalid email.{_RESET}")
            sys.exit(1)

        password = getpass.getpass(f"  {_BLUE}Account Password: {_RESET}")
        if len(password) < 8:
            print(f"  {_RED}Password must be at least 8 characters.{_RESET}")
            sys.exit(1)
        password2 = getpass.getpass(f"  {_BLUE}Confirm Password: {_RESET}")
        if password != password2:
            print(f"  {_RED}Passwords do not match.{_RESET}")
            sys.exit(1)

        # Register via API with SHT as setup token
        try:
            resp = httpx.post(
                f"{server_url}/api/v1/auth/register",
                json={"email": acct_email, "username": username, "password": password},
                headers={"X-Setup-Token": sht},
                timeout=15.0,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.json().get("detail", str(exc))
            print(f"  {_RED}Registration failed: {detail}{_RESET}")
            sys.exit(1)
        except httpx.ConnectError:
            print(f"  {_RED}Cannot reach server.{_RESET}")
            sys.exit(1)

        print(f"  {_GREEN}Owner account created: {username}{_RESET}\n")
    else:
        # Account exists — enter username to link
        username = input(f"  {_BLUE}JARVIS Username (as registered on the site): {_RESET}").strip()
        if not username:
            print(f"  {_RED}Username cannot be empty.{_RESET}")
            sys.exit(1)

        # Verify the account exists via cli-login
        data = _server_cli_auth(sht, username)
        if not data:
            print(f"  {_RED}Could not verify account. Check username and SHT.{_RESET}")
            sys.exit(1)

        print(f"  {_GREEN}Account verified: {username}{_RESET}\n")

    # Store the JARVIS username for display purposes (still required on each login)
    config.set("jarvis_username", username)
    _clear_failures()

    print(f"  {_GREEN}{_BOLD}Stark Secure Server — connection established.{_RESET}")
    print(f"  {_GREEN}J.A.R.V.I.S. is ready, Sir.{_RESET}\n")


# ══════════════════════════════════════════════════════════════════════════
# Unlock: every subsequent access
# ══════════════════════════════════════════════════════════════════════════


def unlock() -> tuple[str, str]:
    """Full 4-layer authentication. Returns (access_token, refresh_token)."""
    _check_lockout()

    if not config.is_setup():
        print(f"  {_RED}CLI not configured. Run: jarvis login{_RESET}")
        sys.exit(1)

    print(f"\n  {_BLUE}{_BOLD}Stark Secure Server Login{_RESET}\n")

    # Layer 1: Gate Username
    gate_user = input(f"  {_BLUE}Gate Username: {_RESET}").strip()
    if not gate_user or _hash_value(gate_user) != config.get("gate_username_hash"):
        _record_failure()
        sys.exit(1)

    # Layer 2: Gate Password
    gate_pass = getpass.getpass(f"  {_BLUE}Gate Password: {_RESET}")
    if not gate_pass or _hash_value(gate_pass) != config.get("gate_password_hash"):
        _record_failure()
        sys.exit(1)

    # Layer 3: Secure Handshake Token (local check first, then server)
    sht = getpass.getpass(f"  {_BLUE}Secure Handshake Token: {_RESET}")
    if not sht or _hash_value(sht) != config.get("sht_hash"):
        _record_failure()
        sys.exit(1)

    # Layer 4: JARVIS Username (server-verified)
    jarvis_user = input(f"  {_BLUE}JARVIS Username: {_RESET}").strip()
    if not jarvis_user:
        _record_failure()
        sys.exit(1)

    # Server authentication
    data = _server_cli_auth(sht, jarvis_user)
    if not data:
        _record_failure()
        sys.exit(1)

    _clear_failures()
    username = data.get("user", {}).get("username", jarvis_user)
    print(f"\n  {_GREEN}Authenticated as {username}.{_RESET}")
    print(f"  {_GREEN}Stark Secure Server — session active.{_RESET}\n")

    return data["access_token"], data["refresh_token"]


# ══════════════════════════════════════════════════════════════════════════
# Token refresh
# ══════════════════════════════════════════════════════════════════════════


def refresh_access_token(refresh_token: str) -> tuple[str, str]:
    """Use refresh token to get a new access token pair."""
    try:
        resp = httpx.post(
            _get_api_url("/auth/refresh"),
            json={"refresh_token": refresh_token},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"], data["refresh_token"]
    except Exception:
        return "", ""


# ══════════════════════════════════════════════════════════════════════════
# Logout
# ══════════════════════════════════════════════════════════════════════════


def logout() -> None:
    """Clear all stored credentials and config."""
    config.clear_all()
    print(f"  {_GREEN}Logged out. Stark Secure Server session terminated.{_RESET}")
