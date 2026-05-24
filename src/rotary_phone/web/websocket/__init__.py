"""WebSocket support for real-time updates."""

from .events import (
    CallAnsweredEvent,
    CallEndedEvent,
    CallLogUpdatedEvent,
    CallRejectedEvent,
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
    "CallAnsweredEvent",
    "CallEndedEvent",
    "CallRejectedEvent",
    "DigitDialedEvent",
    "ConfigChangedEvent",
    "CallLogUpdatedEvent",
]
