"""WebSocket support for real-time updates."""

from .events import (
    CallEndedEvent,
    CallLogUpdatedEvent,
    CallStartedEvent,
    ConfigChangedEvent,
    DigitDialedEvent,
    EventType,
    PhoneStateChangedEvent,
    WebSocketEvent,
)
from .manager import ConnectionManager

__all__ = [
    "ConnectionManager",
    "EventType",
    "WebSocketEvent",
    "PhoneStateChangedEvent",
    "CallStartedEvent",
    "CallEndedEvent",
    "DigitDialedEvent",
    "ConfigChangedEvent",
    "CallLogUpdatedEvent",
]
