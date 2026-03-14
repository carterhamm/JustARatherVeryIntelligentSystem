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

    # Store state + PKCE code_verifier in Redis (needed for token exchange)
    try:
        from app.db.redis import get_redis_client
        redis = await get_redis_client()
        state_data = json.dumps({
            "user_id": str(current_user.id),
            "code_verifier": getattr(flow, "code_verifier", None),
        })
        await redis.cache_set(
            f"google_oauth_state:{state}",
            state_data,
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

    # Verify state and restore PKCE code_verifier from Redis
    user_id = state  # Fallback: state contains user ID
    code_verifier = None
    try:
        from app.db.redis import get_redis_client
        redis = await get_redis_client()
        stored_raw = await redis.cache_get(f"google_oauth_state:{state}")
        if stored_raw:
            try:
                state_data = json.loads(stored_raw)
                user_id = state_data.get("user_id", state)
                code_verifier = state_data.get("code_verifier")
            except (json.JSONDecodeError, TypeError):
                # Legacy format: plain user_id string
                user_id = stored_raw
            await redis.cache_delete(f"google_oauth_state:{state}")
    except Exception:
        logger.warning("Could not verify OAuth state via Redis", exc_info=True)

    # Exchange code for tokens (restore PKCE code_verifier)
    try:
        flow = _build_oauth_flow()
        if code_verifier:
            flow.code_verifier = code_verifier
        flow.fetch_token(code=code)
        credentials = flow.credentials

        token_data = {
            "token": credentials.token,
            "access_token": credentials.token,  # alias — some code uses this key
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
    logger.warning("OAUTH STORAGE: Starting token storage. user_id=%s, has_token=%s, has_refresh=%s",
                    user_id, bool(token_data.get("token")), bool(token_data.get("refresh_token")))
    try:
        from app.models.user import User
        from sqlalchemy import select as _select
        from sqlalchemy.orm.attributes import flag_modified

        # Always use the owner (first active user) — single-owner system
        result = await db.execute(_select(User).where(User.is_active.is_(True)).limit(1))
        user = result.scalar_one_or_none()
        logger.warning("OAUTH STORAGE: Found user=%s", user.id if user else "NONE")

        if user:
            prefs = dict(user.preferences or {})
            prefs["google_tokens"] = token_data
            prefs["google_connected"] = True
            user.preferences = prefs
            flag_modified(user, "preferences")
            await db.commit()
            await db.refresh(user)
            # Verify it stuck
            has_tokens = "google_tokens" in (user.preferences or {})
            logger.warning("OAUTH STORAGE: Committed. Verified google_tokens in prefs: %s", has_tokens)
        else:
            logger.error("OAUTH STORAGE: No active user found!")
            return HTMLResponse(
                content=_error_page("User not found."),
                status_code=404,
            )
    except Exception as exc:
        logger.exception("OAUTH STORAGE: Failed to store Google tokens: %s", exc)
        return HTMLResponse(
            content=_error_page(f"Failed to save tokens: {exc}"),
            status_code=500,
        )

    return HTMLResponse(content=_success_redirect_page())


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

def _success_redirect_page() -> str:
    return """<!DOCTYPE html>
<html>
<head>
    <title>JARVIS — Google Connected</title>
    <meta http-equiv="refresh" content="2;url=https://app.malibupoint.dev/" />
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #0A0E17; font-family: 'SF Mono', 'Fira Code', monospace;
               display: flex; align-items: center; justify-content: center; height: 100vh; }
        .card { text-align: center; padding: 48px 40px;
                background: rgba(8, 14, 30, 0.9); border: 1px solid rgba(0, 212, 255, 0.15);
                clip-path: polygon(0 10px, 10px 0, calc(100% - 10px) 0, 100% 10px,
                                   100% calc(100% - 10px), calc(100% - 10px) 100%,
                                   10px 100%, 0 calc(100% - 10px)); }
        .icon { width: 48px; height: 48px; margin: 0 auto 20px;
                clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
                background: linear-gradient(135deg, rgba(57, 255, 20, 0.25), rgba(0, 212, 255, 0.15));
                display: flex; align-items: center; justify-content: center; }
        .icon span { color: #39ff14; font-size: 22px; }
        .label { font-size: 8px; letter-spacing: 3px; text-transform: uppercase;
                 color: rgba(0, 212, 255, 0.5); margin-bottom: 12px; }
        h1 { font-size: 16px; color: #39ff14; letter-spacing: 2px; margin-bottom: 8px;
             text-shadow: 0 0 20px rgba(57, 255, 20, 0.3); }
        p { color: rgba(255, 255, 255, 0.4); font-size: 11px; }
        .bar { width: 60px; height: 2px; margin: 16px auto 0;
               background: linear-gradient(90deg, transparent, rgba(0, 212, 255, 0.3), transparent); }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon"><span>&#10003;</span></div>
        <div class="label">System Link Established</div>
        <h1>GOOGLE CONNECTED</h1>
        <p>Redirecting to JARVIS...</p>
        <div class="bar"></div>
    </div>
    <script>setTimeout(function(){ window.location.href = 'https://app.malibupoint.dev/'; }, 1500);</script>
</body>
</html>"""


def _error_page(error: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>JARVIS — Connection Failed</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #0A0E17; font-family: 'SF Mono', 'Fira Code', monospace;
               display: flex; align-items: center; justify-content: center; height: 100vh; }}
        .card {{ text-align: center; padding: 48px 40px;
                background: rgba(8, 14, 30, 0.9); border: 1px solid rgba(255, 68, 68, 0.2);
                clip-path: polygon(0 10px, 10px 0, calc(100% - 10px) 0, 100% 10px,
                                   100% calc(100% - 10px), calc(100% - 10px) 100%,
                                   10px 100%, 0 calc(100% - 10px)); }}
        .icon {{ width: 48px; height: 48px; margin: 0 auto 20px;
                clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
                background: linear-gradient(135deg, rgba(255, 68, 68, 0.25), rgba(255, 100, 100, 0.1));
                display: flex; align-items: center; justify-content: center; }}
        .icon span {{ color: #ff4444; font-size: 22px; }}
        .label {{ font-size: 8px; letter-spacing: 3px; text-transform: uppercase;
                 color: rgba(255, 68, 68, 0.5); margin-bottom: 12px; }}
        h1 {{ font-size: 16px; color: #ff4444; letter-spacing: 2px; margin-bottom: 8px; }}
        p {{ color: rgba(255, 255, 255, 0.4); font-size: 11px; margin-bottom: 12px; }}
        .error {{ color: rgba(255, 100, 100, 0.7); font-size: 10px; padding: 8px 12px;
                 background: rgba(255, 68, 68, 0.06); border: 1px solid rgba(255, 68, 68, 0.1); }}
        .bar {{ width: 60px; height: 2px; margin: 16px auto 0;
               background: linear-gradient(90deg, transparent, rgba(255, 68, 68, 0.3), transparent); }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon"><span>&#10007;</span></div>
        <div class="label">Link Failed</div>
        <h1>CONNECTION ERROR</h1>
        <p>Could not establish Google link.</p>
        <div class="error">{error}</div>
        <div class="bar"></div>
    </div>
</body>
</html>"""
