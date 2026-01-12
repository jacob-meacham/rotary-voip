"""Abstract SIP client interface for VoIP calling.

This module provides an abstract base class for SIP clients, allowing
for different implementations (real PJSUA2, mock/in-memory, etc.).
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class CallState(Enum):
    """SIP call states."""

    IDLE = "idle"  # No call activity
    REGISTERING = "registering"  # Registering with SIP server
    REGISTERED = "registered"  # Registered and ready for calls
    CALLING = "calling"  # Outgoing call in progress (dialing)
    RINGING = "ringing"  # Incoming call ringing
    CONNECTED = "connected"  # Call is active (connected)
    DISCONNECTED = "disconnected"  # Call ended/failed


class SIPClient(ABC):
    """Abstract base class for SIP client implementations.

    Provides a clean interface for SIP registration, making calls,
    and handling incoming calls.
    """

    def __init__(
        self,
        on_incoming_call: Optional[Callable[[str], None]] = None,
        on_call_answered: Optional[Callable[[], None]] = None,
        on_call_ended: Optional[Callable[[], None]] = None,
    ) -> None:
        """Initialize the SIP client.

        Args:
            on_incoming_call: Callback when incoming call arrives (receives caller ID)
            on_call_answered: Callback when call is answered (outgoing or incoming)
            on_call_ended: Callback when call ends
        """
        self._on_incoming_call = on_incoming_call
        self._on_call_answered = on_call_answered
        self._on_call_ended = on_call_ended
        self._call_state = CallState.IDLE

    @abstractmethod
    def register(self, account_uri: str, username: str, password: str) -> None:
        """Register with SIP server.

        Args:
            account_uri: SIP account URI (e.g., "sip:user@domain.com")
            username: SIP username
            password: SIP password
        """

    @abstractmethod
    def unregister(self) -> None:
        """Unregister from SIP server."""

    @abstractmethod
    def make_call(self, destination: str) -> None:
        """Initiate an outgoing call.

        Args:
            destination: Destination phone number or SIP URI
        """

    @abstractmethod
    def answer_call(self) -> None:
        """Answer an incoming call."""

    @abstractmethod
    def hangup(self) -> None:
        """Hang up the current call."""

    @abstractmethod
    def reject_call(self) -> None:
        """Reject an incoming call without answering."""

    def get_call_state(self) -> CallState:
        """Get the current call state.

        Returns:
            Current call state
        """
        return self._call_state

    def set_callbacks(
        self,
        on_incoming_call: Optional[Callable[[str], None]] = None,
        on_call_answered: Optional[Callable[[], None]] = None,
        on_call_ended: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set callbacks for call events.

        Args:
            on_incoming_call: Callback when incoming call arrives (receives caller ID)
            on_call_answered: Callback when call is answered
            on_call_ended: Callback when call ends
        """
        if on_incoming_call is not None:
            self._on_incoming_call = on_incoming_call
        if on_call_answered is not None:
            self._on_call_answered = on_call_answered
        if on_call_ended is not None:
            self._on_call_ended = on_call_ended

    def _set_call_state(self, state: CallState) -> None:
        """Set the call state (for use by subclasses).

        Args:
            state: New call state
        """
        old_state = self._call_state
        self._call_state = state
        logger.debug("Call state changed: %s -> %s", old_state.value, state.value)
