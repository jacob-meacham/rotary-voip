"""Call logger that tracks and persists phone call activity."""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from rotary_phone.database.database import Database
from rotary_phone.database.models import CallLog

logger = logging.getLogger(__name__)


@dataclass
class PendingCall:
    """Tracks an in-progress call before it's saved to the database."""

    timestamp: datetime
    direction: str
    caller_id: Optional[str] = None
    dialed_number: Optional[str] = None
    destination: Optional[str] = None
    speed_dial_code: Optional[str] = None
    answered_at: Optional[datetime] = None


class CallLogger:
    """Tracks calls and logs them to the database.

    This class integrates with CallManager to record all call activity.
    It tracks calls in memory while they're in progress and writes
    completed call records to the database.

    Thread-safe: all operations use a lock since CallManager callbacks
    can come from different threads.
    """

    def __init__(self, database: Database) -> None:
        """Initialize the call logger.

        Args:
            database: Database instance for persistence
        """
        self._db = database
        self._current_call: Optional[PendingCall] = None
        self._lock = threading.Lock()
        logger.debug("CallLogger initialized")

    def on_outbound_call_started(
        self,
        dialed_number: str,
        destination: str,
        speed_dial_code: Optional[str] = None,
    ) -> None:
        """Start tracking an outbound call.

        Called when user finishes dialing and call is being placed.

        Args:
            dialed_number: Original number dialed (before speed dial expansion)
            destination: Final destination number (after speed dial expansion)
            speed_dial_code: Speed dial code used, or None if direct dial
        """
        with self._lock:
            if self._current_call is not None:
                logger.warning("Starting new call while previous call still tracked, discarding")

            self._current_call = PendingCall(
                timestamp=datetime.utcnow(),
                direction="outbound",
                dialed_number=dialed_number,
                destination=destination,
                speed_dial_code=speed_dial_code,
            )
            logger.debug(
                "Tracking outbound call to %s (dialed: %s, speed_dial: %s)",
                destination,
                dialed_number,
                speed_dial_code,
            )

    def on_inbound_call_started(self, caller_id: str) -> None:
        """Start tracking an inbound call.

        Called when an incoming call is received.

        Args:
            caller_id: Caller ID of the incoming call
        """
        with self._lock:
            if self._current_call is not None:
                logger.warning("Starting new call while previous call still tracked, discarding")

            self._current_call = PendingCall(
                timestamp=datetime.utcnow(),
                direction="inbound",
                caller_id=caller_id,
            )
            logger.debug("Tracking inbound call from %s", caller_id)

    def on_call_answered(self) -> None:
        """Mark the current call as answered.

        Called when a call is answered (either direction).
        """
        with self._lock:
            if self._current_call is None:
                logger.warning("Call answered but no call being tracked")
                return

            self._current_call.answered_at = datetime.utcnow()
            logger.debug("Call answered at %s", self._current_call.answered_at)

    def on_call_ended(self, status: str, error_message: Optional[str] = None) -> None:
        """Finalize and save the call record.

        Called when a call ends (for any reason).

        Args:
            status: Final call status ("completed", "missed", "failed", "rejected")
            error_message: Error description if call failed
        """
        with self._lock:
            if self._current_call is None:
                logger.warning("Call ended but no call being tracked")
                return

            ended_at = datetime.utcnow()
            pending = self._current_call
            self._current_call = None

        # Calculate duration
        duration = 0
        if pending.answered_at:
            duration = int((ended_at - pending.answered_at).total_seconds())

        # Create the call log record
        call_log = CallLog(
            timestamp=pending.timestamp,
            direction=pending.direction,
            caller_id=pending.caller_id,
            dialed_number=pending.dialed_number,
            destination=pending.destination,
            speed_dial_code=pending.speed_dial_code,
            status=status,
            duration_seconds=duration,
            answered_at=pending.answered_at,
            ended_at=ended_at,
            error_message=error_message,
        )

        # Save to database (outside lock to avoid blocking)
        try:
            call_id = self._db.add_call(call_log)
            logger.info(
                "Logged %s %s call (id=%d, duration=%ds, status=%s)",
                pending.direction,
                (
                    "to " + (pending.destination or "unknown")
                    if pending.direction == "outbound"
                    else "from " + (pending.caller_id or "unknown")
                ),
                call_id,
                duration,
                status,
            )
        except Exception as e:
            # Database errors should not crash the phone
            logger.error("Failed to save call log: %s", e)

    def on_call_rejected(self, dialed_number: str, reason: str) -> None:
        """Log a call that was rejected (e.g., not in allowlist).

        This is for calls that never started because validation failed.

        Args:
            dialed_number: Number that was dialed
            reason: Why the call was rejected
        """
        call_log = CallLog(
            timestamp=datetime.utcnow(),
            direction="outbound",
            dialed_number=dialed_number,
            destination=dialed_number,  # Same as dialed since it was rejected
            status="rejected",
            error_message=reason,
        )

        try:
            call_id = self._db.add_call(call_log)
            logger.info("Logged rejected call to %s (id=%d): %s", dialed_number, call_id, reason)
        except Exception as e:
            logger.error("Failed to save rejected call log: %s", e)

    def cancel_current_call(self) -> None:
        """Cancel tracking of the current call without logging it.

        Used when user hangs up before a call is actually placed
        (e.g., during dialing).
        """
        with self._lock:
            if self._current_call is not None:
                logger.debug("Cancelled tracking of pending call")
                self._current_call = None

    def has_pending_call(self) -> bool:
        """Check if there's a call currently being tracked.

        Returns:
            True if a call is in progress
        """
        with self._lock:
            return self._current_call is not None
