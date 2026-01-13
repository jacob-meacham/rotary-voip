"""WebSocket event models and types."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """WebSocket event types."""

    PHONE_STATE_CHANGED = "phone_state_changed"
    CALL_STARTED = "call_started"
    CALL_ENDED = "call_ended"
    DIGIT_DIALED = "digit_dialed"
    CONFIG_CHANGED = "config_changed"
    CALL_LOG_UPDATED = "call_log_updated"


class WebSocketEvent(BaseModel):
    """Base WebSocket event."""

    type: EventType
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    data: Dict[str, Any] = Field(default_factory=dict)


class PhoneStateChangedEvent(WebSocketEvent):
    """Phone state changed event."""

    type: EventType = EventType.PHONE_STATE_CHANGED

    def __init__(
        self,
        old_state: str,
        new_state: str,
        current_number: Optional[str] = None,
        **kwargs: Any,
    ):
        """Initialize phone state changed event.

        Args:
            old_state: Previous phone state
            new_state: New phone state
            current_number: Current number being dialed/called
            **kwargs: Additional fields
        """
        data = {
            "old_state": old_state,
            "new_state": new_state,
        }
        if current_number:
            data["current_number"] = current_number
        super().__init__(data=data, **kwargs)


class CallStartedEvent(WebSocketEvent):
    """Call started event."""

    type: EventType = EventType.CALL_STARTED

    def __init__(
        self,
        direction: str,
        number: str,
        **kwargs: Any,
    ):
        """Initialize call started event.

        Args:
            direction: Call direction (inbound/outbound)
            number: Phone number
            **kwargs: Additional fields
        """
        super().__init__(
            data={
                "direction": direction,
                "number": number,
            },
            **kwargs,
        )


class CallEndedEvent(WebSocketEvent):
    """Call ended event."""

    type: EventType = EventType.CALL_ENDED

    def __init__(
        self,
        direction: str,
        number: str,
        duration: float,
        status: str,
        **kwargs: Any,
    ):
        """Initialize call ended event.

        Args:
            direction: Call direction (inbound/outbound)
            number: Phone number
            duration: Call duration in seconds
            status: Call status (completed/missed/failed/rejected)
            **kwargs: Additional fields
        """
        super().__init__(
            data={
                "direction": direction,
                "number": number,
                "duration": duration,
                "status": status,
            },
            **kwargs,
        )


class DigitDialedEvent(WebSocketEvent):
    """Digit dialed event."""

    type: EventType = EventType.DIGIT_DIALED

    def __init__(
        self,
        digit: str,
        number_so_far: str,
        **kwargs: Any,
    ):
        """Initialize digit dialed event.

        Args:
            digit: Digit that was dialed
            number_so_far: Accumulated number so far
            **kwargs: Additional fields
        """
        super().__init__(
            data={
                "digit": digit,
                "number_so_far": number_so_far,
            },
            **kwargs,
        )


class ConfigChangedEvent(WebSocketEvent):
    """Config changed event."""

    type: EventType = EventType.CONFIG_CHANGED

    def __init__(
        self,
        section: str,
        **kwargs: Any,
    ):
        """Initialize config changed event.

        Args:
            section: Config section that changed (e.g., "speed_dial", "allowlist")
            **kwargs: Additional fields
        """
        super().__init__(
            data={
                "section": section,
            },
            **kwargs,
        )


class CallLogUpdatedEvent(WebSocketEvent):
    """Call log updated event (new call logged)."""

    type: EventType = EventType.CALL_LOG_UPDATED

    def __init__(
        self,
        call_id: int,
        **kwargs: Any,
    ):
        """Initialize call log updated event.

        Args:
            call_id: ID of the new call log entry
            **kwargs: Additional fields
        """
        super().__init__(
            data={
                "call_id": call_id,
            },
            **kwargs,
        )
