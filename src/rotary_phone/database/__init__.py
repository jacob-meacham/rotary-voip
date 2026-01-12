"""Database module for call logging."""

from rotary_phone.database.models import CallLog
from rotary_phone.database.database import Database

__all__ = ["CallLog", "Database"]
