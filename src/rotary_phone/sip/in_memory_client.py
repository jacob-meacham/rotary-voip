"""In-memory SIP client implementation for testing.

This module provides a mock SIP client that simulates SIP behavior
without requiring a real SIP server.
"""

import logging
import threading
from typing import Any, Callable, Optional

from rotary_phone.sip.sip_client import CallState, SIPClient

logger = logging.getLogger(__name__)


class InMemorySIPClient(SIPClient):
    """In-memory SIP client for testing without a real SIP server.

    This client simulates SIP behavior in memory, allowing testing of
    call flows without network dependencies.
    """

    def __init__(
        self,
        on_incoming_call: Optional[Callable[[str], None]] = None,
        on_call_answered: Optional[Callable[[], None]] = None,
        on_call_ended: Optional[Callable[[], None]] = None,
        *,
        registration_delay: float = 0.0,
        call_connect_delay: float = 0.0,
    ) -> None:
        """Initialize the in-memory SIP client.

        Args:
            on_incoming_call: Callback when incoming call arrives
            on_call_answered: Callback when call is answered
            on_call_ended: Callback when call ends
            registration_delay: Simulated delay for registration (seconds)
            call_connect_delay: Simulated delay for call connection (seconds)
        """
        super().__init__(on_incoming_call, on_call_answered, on_call_ended)
        self._registration_delay = registration_delay
        self._call_connect_delay = call_connect_delay
        self._account_uri: Optional[str] = None
        self._username: Optional[str] = None
        self._current_call_destination: Optional[str] = None
        self._current_call_caller: Optional[str] = None
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.RLock()  # Reentrant lock for nested calls

    def register(self, account_uri: str, username: str, password: str) -> None:
        """Register with SIP server (simulated).

        Args:
            account_uri: SIP account URI
            username: SIP username
            password: SIP password (ignored in mock)
        """
        with self._lock:
            if self._call_state != CallState.IDLE:
                logger.warning("Cannot register while in state: %s", self._call_state.value)
                return

            self._account_uri = account_uri
            self._username = username
            self._set_call_state(CallState.REGISTERING)
            logger.info("Registering: %s (user: %s)", account_uri, username)

            if self._registration_delay > 0:
                # Simulate async registration
                self._timer = threading.Timer(self._registration_delay, self._complete_registration)
                self._timer.daemon = True
                self._timer.start()
            else:
                # Immediate registration
                self._complete_registration()

    def _complete_registration(self) -> None:
        """Complete the registration process."""
        with self._lock:
            if self._call_state == CallState.REGISTERING:
                self._set_call_state(CallState.REGISTERED)
                logger.info("Registration complete: %s", self._account_uri)
                self._timer = None

    def unregister(self) -> None:
        """Unregister from SIP server (simulated)."""
        with self._lock:
            if self._call_state == CallState.IDLE:
                logger.debug("Already unregistered")
                return

            # Cancel any pending timer
            if self._timer:
                self._timer.cancel()
                self._timer = None

            logger.info("Unregistering: %s", self._account_uri)
            self._account_uri = None
            self._username = None
            self._current_call_destination = None
            self._current_call_caller = None
            self._set_call_state(CallState.IDLE)

    def make_call(self, destination: str) -> None:
        """Initiate an outgoing call (simulated).

        Args:
            destination: Destination phone number or SIP URI
        """
        with self._lock:
            if self._call_state != CallState.REGISTERED:
                logger.warning(
                    "Cannot make call in state: %s (must be REGISTERED)",
                    self._call_state.value,
                )
                return

            self._current_call_destination = destination
            self._set_call_state(CallState.CALLING)
            logger.info("Making call to: %s", destination)

            if self._call_connect_delay > 0:
                # Simulate async call connection
                self._timer = threading.Timer(
                    self._call_connect_delay, self._complete_outgoing_call
                )
                self._timer.daemon = True
                self._timer.start()
            else:
                # Immediate connection
                self._complete_outgoing_call()

    def _complete_outgoing_call(self) -> None:
        """Complete outgoing call connection (simulate remote party answering)."""
        with self._lock:
            if self._call_state != CallState.CALLING:
                return

            self._set_call_state(CallState.CONNECTED)
            logger.info("Call connected: %s", self._current_call_destination)
            self._timer = None

        # Trigger callback outside lock
        if self._on_call_answered:
            self._on_call_answered()

    def answer_call(self) -> None:
        """Answer an incoming call (simulated)."""
        with self._lock:
            if self._call_state != CallState.RINGING:
                logger.warning(
                    "Cannot answer call in state: %s (must be RINGING)",
                    self._call_state.value,
                )
                return

            self._set_call_state(CallState.CONNECTED)
            logger.info("Call answered from: %s", self._current_call_caller)

        # Trigger callback outside lock
        if self._on_call_answered:
            self._on_call_answered()

    def hangup(self) -> None:
        """Hang up the current call (simulated)."""
        with self._lock:
            if self._call_state not in (
                CallState.CALLING,
                CallState.RINGING,
                CallState.CONNECTED,
            ):
                logger.debug("No active call to hang up")
                return

            logger.info("Hanging up call")
            self._current_call_destination = None
            self._current_call_caller = None

            # Cancel any pending timer
            if self._timer:
                self._timer.cancel()
                self._timer = None

            # Transition through DISCONNECTED to REGISTERED
            self._set_call_state(CallState.DISCONNECTED)
            self._set_call_state(CallState.REGISTERED)

        # Trigger callback outside lock
        if self._on_call_ended:
            self._on_call_ended()

    def reject_call(self) -> None:
        """Reject an incoming call without answering (simulated)."""
        with self._lock:
            if self._call_state != CallState.RINGING:
                logger.debug("No incoming call to reject")
                return

            logger.info("Rejecting incoming call from: %s", self._current_call_caller)
            self._current_call_caller = None

            # Transition through DISCONNECTED to REGISTERED
            self._set_call_state(CallState.DISCONNECTED)
            self._set_call_state(CallState.REGISTERED)

        # Trigger callback outside lock
        if self._on_call_ended:
            self._on_call_ended()

    def get_current_call(self) -> Optional[Any]:
        """Get the current call object for audio handling.

        In-memory client does not have a real call object, so this
        always returns None. Audio handling is not supported in mock mode.

        Returns:
            None (mock client has no real call object)
        """
        return None

    def simulate_incoming_call(self, caller_id: str) -> None:
        """Simulate an incoming call (for testing).

        Args:
            caller_id: Caller ID to simulate
        """
        with self._lock:
            if self._call_state != CallState.REGISTERED:
                logger.warning(
                    "Cannot receive call in state: %s (must be REGISTERED)",
                    self._call_state.value,
                )
                return

            self._current_call_caller = caller_id
            self._set_call_state(CallState.RINGING)
            logger.info("Incoming call from: %s", caller_id)

        # Trigger callback outside lock
        if self._on_incoming_call:
            self._on_incoming_call(caller_id)

    def get_current_call_info(self) -> Optional[str]:
        """Get information about the current call.

        Returns:
            Destination (for outgoing) or caller ID (for incoming), or None if no call
        """
        with self._lock:
            if self._current_call_destination:
                return self._current_call_destination
            if self._current_call_caller:
                return self._current_call_caller
            return None

    def simulate_call_answered(self) -> None:
        """Simulate the remote party answering the call (for testing)."""
        with self._lock:
            if self._call_state != CallState.CALLING:
                logger.warning(
                    "Cannot answer call in state: %s (must be CALLING)",
                    self._call_state.value,
                )
                return

            self._set_call_state(CallState.CONNECTED)
            logger.info("Call answered (simulated)")

        # Trigger callback outside lock
        if self._on_call_answered:
            self._on_call_answered()

    def simulate_call_ended(self) -> None:
        """Simulate the call ending from remote side (for testing)."""
        with self._lock:
            if self._call_state not in (CallState.RINGING, CallState.CONNECTED):
                logger.warning(
                    "No active call to end in state: %s",
                    self._call_state.value,
                )
                return

            logger.info("Call ended (simulated)")
            self._current_call_destination = None
            self._current_call_caller = None

            # Transition through DISCONNECTED to REGISTERED
            self._set_call_state(CallState.DISCONNECTED)
            self._set_call_state(CallState.REGISTERED)

        # Trigger callback outside lock
        if self._on_call_ended:
            self._on_call_ended()
