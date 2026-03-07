"""Authentication — first-time setup, login, and session unlock via Secure Handshake Token."""

from __future__ import annotations

import getpass
import sys
from typing import Optional

import httpx

from stark_jarvis.config import config

# ANSI colours
_BLUE = "\x1b[36m"
_GOLD = "\x1b[33m"
_RED = "\x1b[31m"
_GREEN = "\x1b[32m"
_DIM = "\x1b[2m"
_BOLD = "\x1b[1m"
_RESET = "\x1b[0m"


def get_api_url(path: str) -> str:
    """Build full API URL from config."""
    base = config.server_url
    if not base:
        print(f"{_RED}Not connected to a server. Run: jarvis login{_RESET}")
        sys.exit(1)
    return f"{base}/api/v1{path}"


def _check_server(server_url: str) -> bool:
    """Check if the server needs first-time setup. Returns True if setup is needed."""
    try:
        resp = httpx.get(f"{server_url}/api/v1/auth/setup-status", timeout=10.0)
        resp.raise_for_status()
        return not resp.json().get("setup_complete", False)
    except httpx.ConnectError:
        print(f"{_RED}Cannot reach server at {server_url}{_RESET}")
        sys.exit(1)
    except Exception:
        return False


def prompt_sht(confirm: bool = False) -> str:
    """Prompt for the Secure Handshake Token."""
    token = getpass.getpass(f"{_BLUE}Secure Handshake Token: {_RESET}")
    if not token:
        print(f"{_RED}Token cannot be empty.{_RESET}")
        sys.exit(1)
    if confirm:
        token2 = getpass.getpass(f"{_BLUE}Confirm Secure Handshake Token: {_RESET}")
        if token != token2:
            print(f"{_RED}Tokens do not match.{_RESET}")
            sys.exit(1)
    return token


def _first_time_setup(server_url: str) -> None:
    """Run first-time owner account creation."""
    print(f"\n  {_GOLD}{_BOLD}J.A.R.V.I.S. — First Time Setup{_RESET}")
    print(f"  {_DIM}No owner account exists. Creating one now.{_RESET}\n")

    # Require the Secure Handshake Token first (must match server's SETUP_TOKEN)
    print(f"  {_GOLD}Enter the Secure Handshake Token configured on the server.{_RESET}")
    print(f"  {_DIM}This proves you are the owner.{_RESET}\n")
    sht = getpass.getpass(f"  {_BLUE}Secure Handshake Token: {_RESET}")
    if not sht:
        print(f"  {_RED}Token cannot be empty.{_RESET}")
        sys.exit(1)

    username = input(f"  {_BLUE}Username: {_RESET}").strip()
    if not username or len(username) < 3:
        print(f"  {_RED}Username must be at least 3 characters.{_RESET}")
        sys.exit(1)

    email = input(f"  {_BLUE}Email: {_RESET}").strip()
    if not email or "@" not in email:
        print(f"  {_RED}Invalid email.{_RESET}")
        sys.exit(1)

    password = getpass.getpass(f"  {_BLUE}Password: {_RESET}")
    if len(password) < 8:
        print(f"  {_RED}Password must be at least 8 characters.{_RESET}")
        sys.exit(1)
    password2 = getpass.getpass(f"  {_BLUE}Confirm password: {_RESET}")
    if password != password2:
        print(f"  {_RED}Passwords do not match.{_RESET}")
        sys.exit(1)

    # Register via API with the SHT as auth
    try:
        resp = httpx.post(
            f"{server_url}/api/v1/auth/register",
            json={
                "email": email,
                "username": username,
                "password": password,
            },
            headers={"X-Setup-Token": sht},
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json().get("detail", str(exc))
        print(f"  {_RED}Registration failed: {detail}{_RESET}")
        sys.exit(1)
    except httpx.ConnectError:
        print(f"  {_RED}Cannot reach server at {server_url}{_RESET}")
        sys.exit(1)

    data = resp.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    user = data.get("user", {})
    uname = user.get("username", username)

    print(f"\n  {_GREEN}Owner account created: {uname}{_RESET}")

    # Use the same SHT to encrypt local credentials
    config.save_auth(access_token, refresh_token, sht)
    print(f"  {_GREEN}J.A.R.V.I.S. is ready, Sir.{_RESET}\n")


def login(server_url: str, email: Optional[str] = None) -> None:
    """Authenticate with the JARVIS backend. Auto-detects first-time setup."""
    config.server_url = server_url

    # Check if this is first-time setup
    needs_setup = _check_server(server_url)
    if needs_setup:
        _first_time_setup(server_url)
        return

    # Normal login
    if not email:
        email = input(f"  {_BLUE}Email: {_RESET}").strip()
    password = getpass.getpass(f"  {_BLUE}Password: {_RESET}")

    try:
        resp = httpx.post(
            get_api_url("/auth/login"),
            json={"email": email, "password": password},
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        print(f"  {_RED}Cannot reach server at {server_url}{_RESET}")
        sys.exit(1)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            print(f"  {_RED}Invalid credentials.{_RESET}")
        elif exc.response.status_code == 429:
            print(f"  {_RED}Too many attempts. Account locked — try again in 15 minutes.{_RESET}")
        else:
            print(f"  {_RED}Login failed: {exc.response.status_code}{_RESET}")
        sys.exit(1)

    data = resp.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    user = data.get("user", {})
    username = user.get("username", "Sir")

    # Set the Secure Handshake Token for future CLI sessions
    print(f"\n  {_GOLD}Set your Secure Handshake Token.{_RESET}")
    print(f"  {_DIM}This unlocks J.A.R.V.I.S. each time you open the terminal.{_RESET}\n")
    sht = prompt_sht(confirm=True)

    config.save_auth(access_token, refresh_token, sht)
    print(f"\n  {_GREEN}Authenticated as {username}. J.A.R.V.I.S. is ready, Sir.{_RESET}\n")


def unlock() -> tuple[str, str]:
    """Unlock stored credentials with Secure Handshake Token."""
    if not config.has_auth():
        print(f"  {_RED}No stored session. Run: jarvis login{_RESET}")
        sys.exit(1)

    sht = prompt_sht()
    access, refresh = config.load_auth(sht)
    if access is None:
        print(f"  {_RED}Incorrect Secure Handshake Token.{_RESET}")
        sys.exit(1)
    return access, refresh


def refresh_access_token(refresh_token: str) -> tuple[str, str]:
    """Use refresh token to get a new access token pair."""
    try:
        resp = httpx.post(
            get_api_url("/auth/refresh"),
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
    print(f"  {_GREEN}Logged out. All local credentials removed.{_RESET}")
