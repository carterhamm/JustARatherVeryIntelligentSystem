"""Smart notification delivery engine for JARVIS autonomy."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from app.config import settings
from app.db.redis import get_redis_client
from app.integrations.mac_mini import send_imessage, is_configured

logger = logging.getLogger("jarvis.autonomy.delivery")

_MTN = ZoneInfo("America/Denver")
_TTL_24H = 60 * 60 * 24
_TTL_30_DAYS = 60 * 60 * 24 * 30
_MAX_PROACTIVE_PER_DAY = 5


class DeliveryWindow(str, Enum):
    MORNING = "morning"    # 7-10 AM
    WORK = "work"          # 10 AM-6 PM
    EVENING = "evening"    # 6-11 PM
    NIGHT = "night"        # 11 PM-7 AM


def get_delivery_window(now: datetime | None = None) -> DeliveryWindow:
    """Determine the current delivery window based on Mountain Time."""
    if now is None:
        now = datetime.now(_MTN)
    else:
        now = now.astimezone(_MTN)

    hour = now.hour
    if 7 <= hour < 10:
        return DeliveryWindow.MORNING
    elif 10 <= hour < 18:
        return DeliveryWindow.WORK
    elif 18 <= hour < 23:
        return DeliveryWindow.EVENING
    else:
        return DeliveryWindow.NIGHT


async def should_deliver_now(
    priority: int,
    window: DeliveryWindow,
    focus_active: bool,
) -> bool:
    """Decide whether a notification should be delivered immediately.

    Rules:
        - Focus active: deliver ONLY if priority == 10
        - MORNING: priority >= 5
        - WORK: priority >= 7
        - EVENING: priority >= 8
        - NIGHT: ONLY priority == 10
    """
    if focus_active:
        return priority == 10

    if window == DeliveryWindow.MORNING:
        return priority >= 5
    elif window == DeliveryWindow.WORK:
        return priority >= 7
    elif window == DeliveryWindow.EVENING:
        return priority >= 8
    elif window == DeliveryWindow.NIGHT:
        return priority == 10

    return False


async def queue_for_morning(alert: dict[str, Any]) -> None:
    """Store an alert in the morning queue for later delivery.

    Alerts are stored in ``jarvis:autonomy:proactive:morning_queue``
    with a 24-hour TTL.
    """
    try:
        redis = await get_redis_client()
        rkey = "jarvis:autonomy:proactive:morning_queue"
        entry = {
            **alert,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }
        await redis.client.rpush(rkey, json.dumps(entry))
        await redis.client.expire(rkey, _TTL_24H)
        logger.info("Queued alert for morning delivery: %s", alert.get("message", "")[:80])
    except Exception:
        logger.warning("Failed to queue alert for morning", exc_info=True)


async def flush_morning_queue() -> list[dict]:
    """Pop all alerts from the morning queue and return them."""
    try:
        redis = await get_redis_client()
        rkey = "jarvis:autonomy:proactive:morning_queue"
        items: list[dict] = []

        while True:
            raw = await redis.client.lpop(rkey)
            if raw is None:
                break
            try:
                items.append(json.loads(raw))
            except (json.JSONDecodeError, ValueError):
                continue

        if items:
            logger.info("Flushed %d alerts from morning queue", len(items))
        return items
    except Exception:
        logger.warning("Failed to flush morning queue", exc_info=True)
        return []


async def _get_daily_delivery_count() -> int:
    """Get how many proactive messages have been sent today."""
    try:
        redis = await get_redis_client()
        today = datetime.now(_MTN).strftime("%Y-%m-%d")
        rkey = f"jarvis:autonomy:proactive:delivery_log:{today}"
        count = await redis.client.llen(rkey)
        return count or 0
    except Exception:
        logger.warning("Failed to get daily delivery count", exc_info=True)
        return 0


async def _log_delivery(message: str, priority: int, method: str) -> None:
    """Log a delivery event to the daily delivery log."""
    try:
        redis = await get_redis_client()
        today = datetime.now(_MTN).strftime("%Y-%m-%d")
        rkey = f"jarvis:autonomy:proactive:delivery_log:{today}"
        entry = {
            "message": message[:500],
            "priority": priority,
            "method": method,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await redis.client.rpush(rkey, json.dumps(entry))
        await redis.client.expire(rkey, _TTL_30_DAYS)
    except Exception:
        logger.warning("Failed to log delivery", exc_info=True)


async def deliver_alert(
    message: str,
    priority: int,
) -> dict[str, Any]:
    """Smart delivery: check window + focus, deliver via iMessage or queue.

    Enforces a maximum of 5 proactive messages per day. If the message
    shouldn't be delivered now (wrong window or daily limit reached), it
    is queued for the next morning flush.

    Returns a dict with ``delivered``, ``method``, and ``message`` keys.
    """
    window = get_delivery_window()

    # Check daily limit
    daily_count = await _get_daily_delivery_count()
    if daily_count >= _MAX_PROACTIVE_PER_DAY and priority < 10:
        await queue_for_morning({"message": message, "priority": priority})
        return {
            "delivered": False,
            "method": "queued_morning",
            "message": f"Daily limit ({_MAX_PROACTIVE_PER_DAY}) reached, queued for morning",
        }

    # Decide if we should deliver now (no focus detection yet — defaults False)
    deliver_now = await should_deliver_now(priority, window, focus_active=False)

    if not deliver_now:
        await queue_for_morning({"message": message, "priority": priority})
        return {
            "delivered": False,
            "method": "queued_morning",
            "message": f"Window={window.value}, priority={priority} — queued for morning",
        }

    # Attempt iMessage delivery
    if is_configured() and settings.OWNER_PHONE:
        result = await send_imessage(to=settings.OWNER_PHONE, text=message)
        if result.get("success"):
            await _log_delivery(message, priority, "imessage")
            logger.info("Delivered priority-%d alert via iMessage", priority)
            return {
                "delivered": True,
                "method": "imessage",
                "message": "Sent via iMessage",
            }
        else:
            logger.warning(
                "iMessage delivery failed: %s", result.get("message", "unknown")
            )
            # Fall through to queue
    else:
        logger.info("iMessage not configured, queuing alert for morning")

    # Fallback: queue for morning
    await queue_for_morning({"message": message, "priority": priority})
    return {
        "delivered": False,
        "method": "queued_morning",
        "message": "iMessage unavailable, queued for morning",
    }
