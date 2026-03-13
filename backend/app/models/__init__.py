"""ORM models package — import every model so Alembic can discover them."""

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.models.reminder import Reminder
from app.models.passkey import PasskeyCredential
from app.models.contact import Contact
from app.models.health import HealthSample
from app.models.focus_session import FocusSession
from app.models.habit import Habit, HabitLog
from app.models.landmark import Landmark
from app.models.location_history import LocationHistory
from app.models.session import Session

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "User",
    "Conversation",
    "Message",
    "Reminder",
    "PasskeyCredential",
    "Contact",
    "HealthSample",
    "FocusSession",
    "Habit",
    "HabitLog",
    "Landmark",
    "LocationHistory",
    "Session",
]
