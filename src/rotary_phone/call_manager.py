"""Call manager that coordinates all phone components with a state machine.

This module provides the CallManager class which acts as the "brain" of the
phone system, coordinating the hardware components (dial reader, hook monitor,
ringer) with the SIP client to handle phone calls.
"""

import logging
import threading
from enum import Enum
from typing import Optional

from rotary_phone.call_logger import CallLogger
from rotary_phone.config.config_manager import ConfigManager
from rotary_phone.hardware.dial_reader import DialReader
from rotary_phone.hardware.dial_tone import DialTone
from rotary_phone.hardware.hook_monitor import HookMonitor, HookState
from rotary_phone.hardware.ringer import Ringer
from rotary_phone.sip.sip_client import SIPClient

logger = logging.getLogger(__name__)


class PhoneState(Enum):
    """Overall phone system states."""

    IDLE = "idle"  # Phone on hook, no activity
    OFF_HOOK_WAITING = "off_hook_waiting"  # Phone picked up, waiting for first digit
    DIALING = "dialing"  # User is dialing digits
    VALIDATING = "validating"  # Checking speed dial and allowlist
    CALLING = "calling"  # Outbound call in progress
    RINGING = "ringing"  # Incoming call, phone is ringing
    CONNECTED = "connected"  # Active call
    ERROR = "error"  # Error state (blocked number, call failed, etc.)


class CallManager:  # pylint: disable=too-many-instance-attributes
    """Coordinates all phone components with a state machine.

    The CallManager is the main orchestrator that:
    - Monitors hook state (on/off hook)
    - Collects dialed digits
    - Validates numbers against speed dial and allowlist
    - Initiates and manages SIP calls
    - Controls the ringer for incoming calls
    - Enforces the phone state machine
    """

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(
        self,
        config: ConfigManager,
        hook_monitor: HookMonitor,
        dial_reader: DialReader,
        ringer: Ringer,
        sip_client: SIPClient,
        dial_tone: Optional[DialTone] = None,
        call_logger: Optional[CallLogger] = None,
    ) -> None:
        """Initialize the call manager.

        Args:
            config: Configuration manager
            hook_monitor: Hook switch monitor
            dial_reader: Rotary dial reader
            ringer: Ringer control
            sip_client: SIP client for VoIP calls
            dial_tone: Optional dial tone player
            call_logger: Optional call logger for persistence
        """
        self._config = config
        self._hook_monitor = hook_monitor
        self._dial_reader = dial_reader
        self._ringer = ringer
        self._sip_client = sip_client
        self._dial_tone = dial_tone
        self._call_logger = call_logger

        self._state = PhoneState.IDLE
        self._dialed_number = ""
        self._inter_digit_timeout = config.get("timing.inter_digit_timeout", 5.0)
        self._call_attempt_timeout = config.get("timing.call_attempt_timeout", 60.0)
        self._digit_timer: Optional[threading.Timer] = None
        self._call_attempt_timer: Optional[threading.Timer] = None
        self._error_message = ""
        self._lock = threading.RLock()
        self._running = False
        self._current_caller_id = ""  # Track caller ID for logging

        logger.debug("CallManager initialized")

    def start(self) -> None:
        """Start the call manager and all components."""
        if self._running:
            logger.warning("CallManager already running")
            return

        self._running = True
        logger.info("Starting CallManager")

        # Wire up callbacks using proper setter methods
        self._hook_monitor.set_callbacks(
            on_off_hook=self._on_off_hook,
            on_on_hook=self._on_on_hook,
        )
        self._dial_reader.set_on_digit_callback(self._on_digit)
        self._sip_client.set_callbacks(
            on_incoming_call=self._on_incoming_call,
            on_call_answered=self._on_call_answered,
            on_call_ended=self._on_call_ended,
        )

        # Start components
        self._hook_monitor.start()
        self._dial_reader.start()

        # Register SIP client
        sip_config = self._config.get_sip_config()
        if sip_config.get("server") and sip_config.get("username"):
            try:
                account_uri = f"{sip_config['server']}:{sip_config.get('port', 5060)}"
                self._sip_client.register(
                    account_uri=account_uri,
                    username=sip_config["username"],
                    password=sip_config.get("password", ""),
                )
                logger.info("SIP registration initiated")
            except Exception as e:
                logger.error("Failed to register SIP client: %s", e)

        logger.info("CallManager started in state: %s", self._state.value)

    def stop(self) -> None:
        """Stop the call manager and all components."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping CallManager")

        # Cancel any pending timers
        with self._lock:
            if self._digit_timer:
                self._digit_timer.cancel()
                self._digit_timer = None
            if self._call_attempt_timer:
                self._call_attempt_timer.cancel()
                self._call_attempt_timer = None

        # Stop components
        self._dial_reader.stop()
        self._hook_monitor.stop()
        self._ringer.stop_ringing()

        # Unregister SIP client
        try:
            self._sip_client.unregister()
        except Exception as e:
            logger.error("Failed to unregister SIP client: %s", e)

        logger.info("CallManager stopped")

    def get_state(self) -> PhoneState:
        """Get the current phone state.

        Returns:
            Current PhoneState
        """
        with self._lock:
            return self._state

    def get_dialed_number(self) -> str:
        """Get the currently dialed number.

        Returns:
            Dialed number string (empty if not dialing)
        """
        with self._lock:
            return self._dialed_number

    def get_error_message(self) -> str:
        """Get the current error message.

        Returns:
            Error message string (empty if no error)
        """
        with self._lock:
            return self._error_message

    def _transition_to(self, new_state: PhoneState, error_msg: str = "") -> None:
        """Transition to a new state.

        Args:
            new_state: State to transition to
            error_msg: Optional error message (for ERROR state)
        """
        with self._lock:
            old_state = self._state
            self._state = new_state
            if error_msg:
                self._error_message = error_msg
            else:
                self._error_message = ""

            logger.info("State transition: %s -> %s", old_state.value, new_state.value)
            if error_msg:
                logger.warning("Error: %s", error_msg)

    def _on_off_hook(self) -> None:
        """Handle phone going off-hook (picked up)."""
        with self._lock:
            logger.debug("Off-hook event in state: %s", self._state.value)

            if self._state == PhoneState.IDLE:
                # User picked up phone, wait for dialing
                self._dialed_number = ""
                self._transition_to(PhoneState.OFF_HOOK_WAITING)
                # Start dial tone
                if self._dial_tone:
                    self._dial_tone.start()

            elif self._state == PhoneState.RINGING:
                # User answered incoming call
                logger.info("Answering incoming call")
                self._ringer.stop_ringing()
                try:
                    self._sip_client.answer_call()
                    # Log call answered (for incoming calls)
                    if self._call_logger:
                        self._call_logger.on_call_answered()
                    self._transition_to(PhoneState.CONNECTED)
                except Exception as e:
                    logger.error("Failed to answer call: %s", e)
                    # Log failed answer attempt
                    if self._call_logger:
                        self._call_logger.on_call_ended(
                            status="failed", error_message=f"Failed to answer: {e}"
                        )
                    self._transition_to(PhoneState.ERROR, f"Failed to answer: {e}")

    def _on_on_hook(self) -> None:
        """Handle phone going on-hook (hung up)."""
        with self._lock:
            logger.debug("On-hook event in state: %s", self._state.value)

            # Cancel any pending timers
            if self._digit_timer:
                self._digit_timer.cancel()
                self._digit_timer = None
            if self._call_attempt_timer:
                self._call_attempt_timer.cancel()
                self._call_attempt_timer = None

            # Stop dial tone if playing
            if self._dial_tone:
                self._dial_tone.stop()

            # Cancel call logger tracking if user hung up while dialing
            if self._state in (PhoneState.OFF_HOOK_WAITING, PhoneState.DIALING):
                if self._call_logger:
                    self._call_logger.cancel_current_call()

            # Stop ringer if ringing (and log missed call)
            if self._state == PhoneState.RINGING:
                self._ringer.stop_ringing()
                # Log as missed call (user ignored incoming call)
                if self._call_logger:
                    self._call_logger.on_call_ended(status="missed")
                self._current_caller_id = ""

            # Hangup if in a call
            if self._state in (PhoneState.CALLING, PhoneState.CONNECTED):
                # Log call ended by user hanging up
                if self._call_logger:
                    status = "completed" if self._state == PhoneState.CONNECTED else "unanswered"
                    self._call_logger.on_call_ended(status=status)
                try:
                    self._sip_client.hangup()
                except Exception as e:
                    logger.error("Failed to hangup call: %s", e)

            # Reset to idle
            self._dialed_number = ""
            self._current_caller_id = ""
            self._transition_to(PhoneState.IDLE)

    def _on_digit(self, digit: str) -> None:
        """Handle a dialed digit.

        Args:
            digit: Digit that was dialed (0-9)
        """
        with self._lock:
            logger.debug("Digit '%s' in state: %s", digit, self._state.value)

            # Only accept digits in certain states
            if self._state not in (PhoneState.OFF_HOOK_WAITING, PhoneState.DIALING):
                logger.warning("Ignoring digit '%s' in state %s", digit, self._state.value)
                return

            # Transition to DIALING if this is the first digit
            if self._state == PhoneState.OFF_HOOK_WAITING:
                # Stop dial tone when user starts dialing
                if self._dial_tone:
                    self._dial_tone.stop()
                self._transition_to(PhoneState.DIALING)

            # Append digit
            self._dialed_number += digit
            logger.info("Dialed so far: %s", self._dialed_number)

            # Cancel existing timer
            if self._digit_timer:
                self._digit_timer.cancel()

            # Start new timer for inter-digit timeout
            self._digit_timer = threading.Timer(self._inter_digit_timeout, self._on_digit_timeout)
            self._digit_timer.daemon = True
            self._digit_timer.start()

    def _on_digit_timeout(self) -> None:
        """Handle inter-digit timeout - dialing is complete."""
        with self._lock:
            logger.info("Digit timeout, dialing complete: %s", self._dialed_number)

            self._digit_timer = None

            if self._state != PhoneState.DIALING:
                logger.warning("Digit timeout in unexpected state: %s", self._state.value)
                return

            # Validate and process the number
            self._validate_and_call()

    def _validate_and_call(self) -> None:
        """Validate the dialed number and initiate call (must be called with lock held)."""
        dialed = self._dialed_number

        # Transition to validating state
        self._transition_to(PhoneState.VALIDATING)

        # Check speed dial first
        speed_dial_code: Optional[str] = None
        destination = dialed
        speed_dial_number = self._config.get_speed_dial(dialed)
        if speed_dial_number:
            logger.info("Speed dial %s -> %s", dialed, speed_dial_number)
            speed_dial_code = dialed
            destination = speed_dial_number

        # Check allowlist
        if not self._config.is_allowed(destination):
            logger.warning("Number %s is not in allowlist", destination)
            # Log rejected call
            if self._call_logger:
                self._call_logger.on_call_rejected(dialed, f"Number {destination} is not allowed")
            self._transition_to(PhoneState.ERROR, f"Number {destination} is not allowed")
            return

        # Number is allowed, initiate call
        logger.info("Calling %s", destination)

        # Start tracking the call
        if self._call_logger:
            self._call_logger.on_outbound_call_started(
                dialed_number=dialed,
                destination=destination,
                speed_dial_code=speed_dial_code,
            )

        try:
            self._sip_client.make_call(destination)
            self._transition_to(PhoneState.CALLING)

            # Start call attempt timeout timer
            self._call_attempt_timer = threading.Timer(
                self._call_attempt_timeout, self._on_call_attempt_timeout
            )
            self._call_attempt_timer.daemon = True
            self._call_attempt_timer.start()
            logger.debug("Call attempt timeout set for %.1f seconds", self._call_attempt_timeout)
        except Exception as e:
            logger.error("Failed to make call: %s", e)
            # Log failed call
            if self._call_logger:
                self._call_logger.on_call_ended(status="failed", error_message=str(e))
            self._transition_to(PhoneState.ERROR, f"Call failed: {e}")

    def _on_incoming_call(self, caller_id: str) -> None:
        """Handle incoming call.

        Args:
            caller_id: Caller ID of incoming call
        """
        with self._lock:
            logger.info("Incoming call from: %s", caller_id)

            if self._state != PhoneState.IDLE:
                logger.warning(
                    "Ignoring incoming call, phone not idle (state: %s)", self._state.value
                )
                return

            # Check allowlist for incoming calls
            if not self._config.is_allowed(caller_id):
                logger.warning("Rejecting incoming call from %s (not in allowlist)", caller_id)
                # Reject the call first, then log if successful
                try:
                    self._sip_client.reject_call()
                    # Only log rejection after successful SIP rejection
                    if self._call_logger:
                        self._call_logger.on_inbound_call_started(caller_id)
                        self._call_logger.on_call_rejected(
                            caller_id, f"Caller {caller_id} is not in allowlist"
                        )
                except Exception as e:
                    logger.error("Failed to reject call: %s", e)
                return

            # Track caller ID for logging
            self._current_caller_id = caller_id

            # Start tracking the incoming call
            if self._call_logger:
                self._call_logger.on_inbound_call_started(caller_id)

            # Start ringing
            self._ringer.start_ringing()
            self._transition_to(PhoneState.RINGING)

    def _on_call_answered(self) -> None:
        """Handle outbound call being answered."""
        with self._lock:
            logger.info("Call answered")

            # Cancel call attempt timeout since call was answered
            if self._call_attempt_timer:
                self._call_attempt_timer.cancel()
                self._call_attempt_timer = None

            if self._state != PhoneState.CALLING:
                logger.warning("Call answered in unexpected state: %s", self._state.value)
                return

            # Log call answered
            if self._call_logger:
                self._call_logger.on_call_answered()

            self._transition_to(PhoneState.CONNECTED)

    def _on_call_ended(self) -> None:
        """Handle call ending."""
        with self._lock:
            logger.info("Call ended")

            # Cancel call attempt timeout if still running
            if self._call_attempt_timer:
                self._call_attempt_timer.cancel()
                self._call_attempt_timer = None

            # Determine call status for logging
            call_status = self._determine_call_status()

            # Log call ended
            if self._call_logger:
                self._call_logger.on_call_ended(status=call_status)

            # Stop ringer if it was ringing
            if self._state == PhoneState.RINGING:
                self._ringer.stop_ringing()

            # Clear caller ID tracking
            self._current_caller_id = ""

            # Return to idle if phone is on-hook, otherwise wait for user to hang up
            hook_state = self._hook_monitor.get_state()
            if hook_state == HookState.ON_HOOK:
                self._dialed_number = ""
                self._transition_to(PhoneState.IDLE)
            else:
                # Phone is still off-hook, wait for user to hang up
                logger.info("Call ended but phone still off-hook, waiting for hangup")
                self._dialed_number = ""
                self._transition_to(PhoneState.OFF_HOOK_WAITING)
                # Start dial tone again so user can make another call
                if self._dial_tone:
                    self._dial_tone.start()

    def _determine_call_status(self) -> str:
        """Determine the final status of a call based on current state.

        Returns:
            Status string: "completed", "missed", "unanswered", or "failed"
        """
        if self._state == PhoneState.RINGING:
            # Incoming call that was never answered
            return "missed"
        if self._state == PhoneState.CALLING:
            # Outbound call that was never answered
            return "unanswered"
        if self._state == PhoneState.CONNECTED:
            # Call was connected and ended normally
            return "completed"
        return "unknown"

    def _on_call_attempt_timeout(self) -> None:
        """Handle call attempt timeout - remote party never answered."""
        with self._lock:
            self._call_attempt_timer = None

            if self._state != PhoneState.CALLING:
                # Call already ended or was answered, ignore
                return

            logger.warning("Call attempt timed out after %.1f seconds", self._call_attempt_timeout)

            # Hang up the call attempt
            try:
                self._sip_client.hangup()
            except Exception as e:
                logger.error("Failed to hangup timed out call: %s", e)

            # Log as unanswered
            if self._call_logger:
                self._call_logger.on_call_ended(
                    status="unanswered",
                    error_message=f"Call attempt timed out after {self._call_attempt_timeout}s",
                )

            # Check if phone is still off-hook
            hook_state = self._hook_monitor.get_state()
            if hook_state == HookState.ON_HOOK:
                self._dialed_number = ""
                self._transition_to(PhoneState.IDLE)
            else:
                # Phone still off-hook, let user try again
                self._dialed_number = ""
                self._transition_to(PhoneState.OFF_HOOK_WAITING)
                if self._dial_tone:
                    self._dial_tone.start()
