"""Authentication — 4-layer CLI access control.

First-time setup (`jarvis login`):
  1. Set gate username + password (static, local)
  2. Enter Setup Token (one-time, proves ownership)
  3. Enter JARVIS Username (verified against server)
  4. Choose SHT (Secure Handshake Token — user-chosen, stored on server)

Every subsequent access:
  Layer 1: Gate Username (local)
  Layer 2: Gate Password (local)
  Layer 3: SHT (server-verified)
  Layer 4: JARVIS Username (server account lookup → JWT tokens)
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


def _api_url(path: str) -> str:
    """Build full API URL."""
    base = config.server_url or DEFAULT_SERVER
    return f"{base}/api/v1{path}"


# ══════════════════════════════════════════════════════════════════════════
# First-time setup: `jarvis login`
# ══════════════════════════════════════════════════════════════════════════


def login(server_url: str) -> None:
    """Login to JARVIS. First-time: full setup. Already configured: re-authenticate."""
    config.server_url = server_url

    # If already set up, just re-authenticate to get fresh tokens
    if config.is_setup():
        print(f"\n  {_BLUE}{_BOLD}Stark Secure Server Login{_RESET}")
        print(f"  {_DIM}Reconnecting to {server_url}{_RESET}\n")
        access_token, refresh_token = unlock()
        config.save_session(access_token, refresh_token)
        return

    # ── First-time setup ──
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

    if not setup_complete:
        print(f"  {_RED}No owner account exists yet.{_RESET}")
        print(f"  {_DIM}Create your account at {server_url} first, then run this again.{_RESET}")
        sys.exit(1)

    # ── Step 1: Set gate credentials ──
    print(f"  {_BLUE}{_BOLD}Step 1:{_RESET} Set your CLI gate credentials")
    print(f"  {_DIM}Static credentials that guard CLI access.{_RESET}\n")

    gate_user = input(f"  {_BLUE}Gate Username: {_RESET}").strip()
    if not gate_user:
        print(f"  {_RED}Cannot be empty.{_RESET}")
        sys.exit(1)

    gate_pass = getpass.getpass(f"  {_BLUE}Gate Password: {_RESET}")
    if not gate_pass:
        print(f"  {_RED}Cannot be empty.{_RESET}")
        sys.exit(1)
    gate_pass2 = getpass.getpass(f"  {_BLUE}Confirm Gate Password: {_RESET}")
    if gate_pass != gate_pass2:
        print(f"  {_RED}Passwords do not match.{_RESET}")
        sys.exit(1)

    config.set("gate_username_hash", _hash_value(gate_user))
    config.set("gate_password_hash", _hash_value(gate_pass))
    print(f"  {_GREEN}Gate credentials set.{_RESET}\n")

    # ── Step 2: Setup Token ──
    print(f"  {_BLUE}{_BOLD}Step 2:{_RESET} Enter the Setup Token")
    print(f"  {_DIM}One-time token to prove ownership.{_RESET}\n")

    setup_token = getpass.getpass(f"  {_BLUE}Setup Token: {_RESET}")
    if not setup_token:
        print(f"  {_RED}Cannot be empty.{_RESET}")
        sys.exit(1)

    # ── Step 3: JARVIS Username ──
    print(f"\n  {_BLUE}{_BOLD}Step 3:{_RESET} Enter your JARVIS username")
    print(f"  {_DIM}The username you registered with on the site.{_RESET}\n")

    username = input(f"  {_BLUE}JARVIS Username: {_RESET}").strip()
    if not username:
        print(f"  {_RED}Cannot be empty.{_RESET}")
        sys.exit(1)

    # ── Step 4: Choose SHT ──
    print(f"\n  {_BLUE}{_BOLD}Step 4:{_RESET} Set your Secure Handshake Token (SHT)")
    print(f"  {_DIM}This passphrase is required every time you access J.A.R.V.I.S.{_RESET}")
    print(f"  {_DIM}Same across CLI and website.{_RESET}\n")

    sht = getpass.getpass(f"  {_BLUE}SHT: {_RESET}")
    if not sht or len(sht) < 4:
        print(f"  {_RED}SHT must be at least 4 characters.{_RESET}")
        sys.exit(1)
    sht2 = getpass.getpass(f"  {_BLUE}Confirm SHT: {_RESET}")
    if sht != sht2:
        print(f"  {_RED}SHT does not match.{_RESET}")
        sys.exit(1)

    # ── Send to server (one call) ──
    try:
        resp = httpx.post(
            f"{server_url}/api/v1/auth/cli-setup",
            json={"setup_token": setup_token, "username": username, "sht": sht},
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json().get("detail", str(exc))
        print(f"  {_RED}{detail}{_RESET}")
        sys.exit(1)
    except httpx.ConnectError:
        print(f"  {_RED}Cannot reach server.{_RESET}")
        sys.exit(1)
    except Exception as exc:
        print(f"  {_RED}Setup failed: {exc}{_RESET}")
        sys.exit(1)

    config.set("jarvis_username", username)
    config.set("sht_hash", _hash_value(sht))
    _clear_failures()

    print(f"\n  {_GREEN}{_BOLD}Stark Secure Server — connection established.{_RESET}")
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

    # Layer 3: SHT — local pre-check then server verification
    sht = getpass.getpass(f"  {_BLUE}Secure Handshake Token: {_RESET}")
    if not sht or _hash_value(sht) != config.get("sht_hash"):
        _record_failure()
        sys.exit(1)

    # Layer 4: JARVIS Username — server verifies SHT + username, returns tokens
    jarvis_user = input(f"  {_BLUE}JARVIS Username: {_RESET}").strip()
    if not jarvis_user:
        _record_failure()
        sys.exit(1)

    try:
        resp = httpx.post(
            _api_url("/auth/cli-login"),
            json={"sht": sht, "username": jarvis_user},
            timeout=15.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            _clear_failures()
            access_token = data["access_token"]
            refresh_token = data["refresh_token"]
            config.save_session(access_token, refresh_token)
            username = data.get("user", {}).get("username", jarvis_user)
            print(f"\n  {_GREEN}Authenticated as {username}.{_RESET}")
            print(f"  {_GREEN}Stark Secure Server — session active.{_RESET}\n")
            return access_token, refresh_token
        else:
            _record_failure()
            sys.exit(1)
    except httpx.ConnectError:
        print(f"  {_RED}Cannot reach server.{_RESET}")
        sys.exit(1)
    except Exception:
        _record_failure()
        sys.exit(1)

    # Unreachable but satisfies type checker
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════
# Token refresh & logout
# ══════════════════════════════════════════════════════════════════════════


def refresh_access_token(refresh_token: str) -> tuple[str, str]:
    """Use refresh token to get a new access token pair."""
    try:
        resp = httpx.post(
            _api_url("/auth/refresh"),
            json={"refresh_token": refresh_token},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"], data["refresh_token"]
    except Exception:
        return "", ""


def logout() -> None:
    """Clear all stored credentials and config."""
    config.clear_all()
    print(f"  {_GREEN}Logged out. Stark Secure Server session terminated.{_RESET}")
