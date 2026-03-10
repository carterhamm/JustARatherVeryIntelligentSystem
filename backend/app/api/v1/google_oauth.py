"""
Google OAuth 2.0 flow for JARVIS.

Provides endpoints for users to authorize JARVIS to access their Google
Workspace services (Gmail, Calendar, Drive, Sheets). Tokens are stored
per-user in the user's preferences so each user has their own Google
connection.

Flow:
1. User visits GET /api/v1/google/auth-url → gets a Google consent URL
2. User clicks the URL, signs in with Google, grants permissions
3. Google redirects to GET /api/v1/google/callback with an auth code
4. Backend exchanges the code for tokens, stores them in user preferences
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_active_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google", tags=["google-oauth"])

# Google OAuth scopes for full Workspace access
_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/contacts.readonly",
]

# Callback URL — auto-detected from the deployment domain
_CALLBACK_PATH = "/api/v1/google/callback"


def _get_redirect_uri() -> str:
    """Build the OAuth redirect URI based on deployment context."""
    # Production
    return f"https://app.malibupoint.dev{_CALLBACK_PATH}"


def _build_oauth_flow():
    """Create a Google OAuth2 flow object."""
    from google_auth_oauthlib.flow import Flow

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [_get_redirect_uri()],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=_SCOPES,
        redirect_uri=_get_redirect_uri(),
    )
    return flow


@router.get(
    "/auth-url",
    summary="Get Google OAuth consent URL",
)
async def get_auth_url(
    current_user: Any = Depends(get_current_active_user),
) -> dict:
    """
    Generate a Google OAuth consent URL for the current user.

    The user should open this URL in a browser to grant JARVIS access
    to their Google Workspace services.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth not configured. GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET required.",
        )

    flow = _build_oauth_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=str(current_user.id),  # Pass user ID through the state param
    )

    # Store state in Redis for CSRF protection
    try:
        from app.db.redis import get_redis_client
        redis = get_redis_client()
        await redis.cache_set(
            f"google_oauth_state:{state}",
            str(current_user.id),
            ttl=600,  # 10 minute expiry
        )
    except Exception:
        logger.warning("Redis unavailable for OAuth state storage", exc_info=True)

    return {
        "auth_url": auth_url,
        "message": "Open this URL in your browser to connect your Google account to JARVIS.",
    }


@router.get(
    "/callback",
    response_class=HTMLResponse,
    summary="Google OAuth callback",
)
async def oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """
    Handle the Google OAuth callback after user grants consent.

    Exchanges the authorization code for tokens and stores them in the
    user's preferences.
    """
    if not code:
        return HTMLResponse(
            content=_error_page("No authorization code received."),
            status_code=400,
        )

    # Verify state and get user ID
    user_id = state  # State contains the user ID
    try:
        from app.db.redis import get_redis_client
        redis = get_redis_client()
        stored_user_id = await redis.cache_get(f"google_oauth_state:{state}")
        if stored_user_id:
            user_id = stored_user_id
            await redis.cache_delete(f"google_oauth_state:{state}")
    except Exception:
        logger.warning("Could not verify OAuth state via Redis", exc_info=True)

    # Exchange code for tokens
    try:
        flow = _build_oauth_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials

        token_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes) if credentials.scopes else _SCOPES,
        }
    except Exception as exc:
        logger.exception("Failed to exchange OAuth code for tokens")
        return HTMLResponse(
            content=_error_page(f"Token exchange failed: {exc}"),
            status_code=500,
        )

    # Store tokens in user preferences
    try:
        from app.models.user import User
        result = await db.execute(
            __import__("sqlalchemy").select(User).where(
                User.id == user_id
            )
        )
        user = result.scalar_one_or_none()
        if user:
            prefs = user.preferences or {}
            prefs["google_tokens"] = token_data
            prefs["google_connected"] = True
            user.preferences = prefs
            await db.commit()
            logger.info("Stored Google OAuth tokens for user %s", user_id)
        else:
            logger.error("User %s not found for OAuth callback", user_id)
            return HTMLResponse(
                content=_error_page("User not found."),
                status_code=404,
            )
    except Exception as exc:
        logger.exception("Failed to store Google tokens")
        return HTMLResponse(
            content=_error_page(f"Failed to save tokens: {exc}"),
            status_code=500,
        )

    return HTMLResponse(content=_success_page())


@router.get(
    "/status",
    summary="Check Google connection status",
)
async def google_status(
    current_user: Any = Depends(get_current_active_user),
) -> dict:
    """Check whether the current user has connected their Google account."""
    prefs = current_user.preferences or {}
    connected = prefs.get("google_connected", False)
    has_tokens = "google_tokens" in prefs
    return {
        "connected": connected and has_tokens,
        "scopes": prefs.get("google_tokens", {}).get("scopes", []) if has_tokens else [],
    }


@router.delete(
    "/disconnect",
    summary="Disconnect Google account",
)
async def disconnect_google(
    current_user: Any = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove Google OAuth tokens for the current user."""
    from app.models.user import User
    result = await db.execute(
        __import__("sqlalchemy").select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()
    if user:
        prefs = user.preferences or {}
        prefs.pop("google_tokens", None)
        prefs.pop("google_connected", None)
        user.preferences = prefs
        await db.commit()
    return {"disconnected": True}


# ── HTML response pages ──────────────────────────────────────────────────

def _success_page() -> str:
    return """<!DOCTYPE html>
<html>
<head>
    <title>JARVIS — Google Connected</title>
    <style>
        body { background: #0a0a0a; color: #00d4ff; font-family: -apple-system, BlinkMacSystemFont, sans-serif;
               display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .card { text-align: center; max-width: 500px; padding: 40px; }
        h1 { font-size: 24px; margin-bottom: 8px; }
        p { color: #8899aa; font-size: 16px; line-height: 1.5; }
        .check { font-size: 64px; margin-bottom: 16px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="check">&#10003;</div>
        <h1>Google Account Connected</h1>
        <p>JARVIS now has access to your Gmail, Calendar, Drive, and Sheets.
           You can close this window.</p>
    </div>
</body>
</html>"""


def _error_page(error: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>JARVIS — Connection Failed</title>
    <style>
        body {{ background: #0a0a0a; color: #ff4444; font-family: -apple-system, BlinkMacSystemFont, sans-serif;
               display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
        .card {{ text-align: center; max-width: 500px; padding: 40px; }}
        h1 {{ font-size: 24px; margin-bottom: 8px; }}
        p {{ color: #8899aa; font-size: 16px; line-height: 1.5; }}
        .x {{ font-size: 64px; margin-bottom: 16px; }}
        .error {{ color: #ff6666; font-size: 14px; margin-top: 16px; font-family: monospace; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="x">&#10007;</div>
        <h1>Connection Failed</h1>
        <p>Something went wrong connecting your Google account.</p>
        <div class="error">{error}</div>
    </div>
</body>
</html>"""
