"""Session tracking API — list, view, and revoke active sessions."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_active_user, get_db
from app.models.session import Session
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Sessions"])


# -- Schemas ----------------------------------------------------------------

class SessionResponse(BaseModel):
    id: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_type: Optional[str] = None
    location_city: Optional[str] = None
    location_country: Optional[str] = None
    signed_in_at: str
    last_active_at: str
    expires_at: str
    is_active: bool
    login_method: Optional[str] = None
    is_current: bool = False


# -- Helpers ----------------------------------------------------------------

def _get_client_ip(request: Request) -> str:
    """Extract real client IP from X-Forwarded-For or request.client."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _parse_device_type(user_agent: str) -> str:
    """Simple device type detection from user-agent string."""
    ua = user_agent.lower()
    if "jarvis-ios" in ua or "cfnetwork" in ua:
        return "ios"
    if "jarvis-watch" in ua:
        return "watch"
    if "malibupoint" in ua or "python" in ua:
        return "cli"
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        return "mobile"
    if any(b in ua for b in ("chrome", "firefox", "safari", "edge")):
        return "web"
    return "unknown"


async def create_session_record(
    db: AsyncSession,
    user: User,
    request: Request,
    login_method: str,
) -> Session:
    """Create a new session record for a login event."""
    ip = _get_client_ip(request)
    ua = request.headers.get("user-agent", "")[:512]
    device = _parse_device_type(ua)
    now = datetime.now(timezone.utc)

    # Use user's current location if available
    prefs = user.preferences or {}
    loc = prefs.get("current_location", {})

    plain_token = secrets.token_hex(32)
    token_hash = hashlib.sha256(plain_token.encode()).hexdigest()

    session = Session(
        user_id=user.id,
        session_token=plain_token,
        token_hash=token_hash,
        ip_address=ip,
        user_agent=ua,
        device_type=device,
        location_city=loc.get("city"),
        location_country=loc.get("country"),
        signed_in_at=now,
        last_active_at=now,
        expires_at=now + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES),
        is_active=True,
        login_method=login_method,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(
        "Session created: user=%s device=%s ip=%s method=%s",
        user.username, device, ip, login_method,
    )
    return session


def _session_to_response(session: Session, current_token: str | None = None) -> SessionResponse:
    # Compare using token_hash (SHA-256) when available, fall back to plain token
    is_current = False
    if current_token:
        incoming_hash = hashlib.sha256(current_token.encode()).hexdigest()
        if session.token_hash:
            is_current = session.token_hash == incoming_hash
        else:
            # Legacy session without token_hash — compare plain tokens
            is_current = session.session_token == current_token

    return SessionResponse(
        id=str(session.id),
        ip_address=session.ip_address,
        user_agent=session.user_agent,
        device_type=session.device_type,
        location_city=session.location_city,
        location_country=session.location_country,
        signed_in_at=session.signed_in_at.isoformat(),
        last_active_at=session.last_active_at.isoformat(),
        expires_at=session.expires_at.isoformat(),
        is_active=session.is_active and session.expires_at > datetime.now(timezone.utc),
        login_method=session.login_method,
        is_current=is_current,
    )


# -- Endpoints --------------------------------------------------------------

@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sessions for the current user, newest first."""
    # Mark expired sessions as inactive
    now = datetime.now(timezone.utc)
    await db.execute(
        update(Session)
        .where(
            Session.user_id == current_user.id,
            Session.is_active == True,
            Session.expires_at < now,
        )
        .values(is_active=False)
    )
    await db.commit()

    result = await db.execute(
        select(Session)
        .where(Session.user_id == current_user.id)
        .order_by(Session.signed_in_at.desc())
        .limit(50)
    )
    sessions = result.scalars().all()
    return [_session_to_response(s) for s in sessions]


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke (sign out) a specific session."""
    import uuid as _uuid
    try:
        sid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    result = await db.execute(
        select(Session).where(
            Session.id == sid,
            Session.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.is_active = False
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info("Session revoked: user=%s session=%s", current_user.username, session_id)
    return None


@router.delete("", status_code=status.HTTP_200_OK)
async def revoke_all_sessions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Revoke all active sessions (sign out everywhere)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(Session)
        .where(
            Session.user_id == current_user.id,
            Session.is_active == True,
        )
        .values(is_active=False, revoked_at=now)
    )
    await db.commit()

    count = result.rowcount  # type: ignore
    logger.info("All sessions revoked: user=%s count=%s", current_user.username, count)
    return {"revoked": count}
