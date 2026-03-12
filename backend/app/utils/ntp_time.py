"""NTP time synchronization with time.apple.com.

Provides accurate timestamps by querying Apple's NTP server,
with a cached offset to avoid hitting the server on every call.
"""

import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger("jarvis.ntp")

_ntp_offset: float | None = None
_last_sync: float = 0.0
_SYNC_INTERVAL = 3600  # Re-sync every hour


def _sync_ntp() -> float:
    """Query time.apple.com and return the offset in seconds."""
    try:
        import ntplib
        client = ntplib.NTPClient()
        response = client.request("time.apple.com", version=3, timeout=5)
        offset = response.offset
        logger.info("NTP sync to time.apple.com: offset=%.4fs", offset)
        return offset
    except Exception as exc:
        logger.warning("NTP sync failed: %s", exc)
        return 0.0


def get_ntp_offset() -> float:
    """Get the cached NTP offset, re-syncing if stale."""
    global _ntp_offset, _last_sync
    now = time.monotonic()
    if _ntp_offset is None or (now - _last_sync) > _SYNC_INTERVAL:
        _ntp_offset = _sync_ntp()
        _last_sync = now
    return _ntp_offset


def ntp_now() -> datetime:
    """Return the current UTC time corrected by NTP offset from time.apple.com."""
    offset = get_ntp_offset()
    return datetime.fromtimestamp(time.time() + offset, tz=timezone.utc)


def ntp_timestamp() -> float:
    """Return a corrected UNIX timestamp."""
    return time.time() + get_ntp_offset()
