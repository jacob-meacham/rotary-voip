"""PyVoIP-based SIP client implementation for real VoIP calling.

This module provides a SIP client implementation using the pyVoIP library
for making real VoIP calls.
"""

import audioop  # pylint: disable=deprecated-module
import logging
import threading
import time
import wave
from typing import Any, Callable, Optional

from pyVoIP.VoIP import CallState as PyVoIPCallState
from pyVoIP.VoIP import PhoneStatus as PyVoIPPhoneStatus
from pyVoIP.VoIP import VoIPCall, VoIPPhone

from rotary_phone.exceptions import (
    SIPCallError,
    SIPError,
    SIPRegistrationError,
)
from rotary_phone.sip.sip_client import CallState, SIPClient

logger = logging.getLogger(__name__)


# Default SIP registration timeout in seconds
DEFAULT_REGISTRATION_TIMEOUT = 10.0


class PyVoIPClient(SIPClient):
    """Real SIP client using pyVoIP library for VoIP calling.

    This client wraps the pyVoIP.VoIPPhone class to implement the
    SIPClient interface for making real VoIP calls.
    """

    def __init__(
        self,
        on_incoming_call: Optional[Callable[[str], None]] = None,
        on_call_answered: Optional[Callable[[], None]] = None,
        on_call_ended: Optional[Callable[[], None]] = None,
        registration_timeout: float = DEFAULT_REGISTRATION_TIMEOUT,
    ) -> None:
        """Initialize the PyVoIP SIP client.

        Args:
            on_incoming_call: Callback when incoming call arrives
            on_call_answered: Callback when call is answered
            on_call_ended: Callback when call ends
            registration_timeout: Seconds to wait for SIP registration
        """
        super().__init__(on_incoming_call, on_call_answered, on_call_ended)
        self._phone: Optional[VoIPPhone] = None
        self._current_call: Optional[VoIPCall] = None
        self._lock = threading.RLock()
        self._registration_timeout = registration_timeout

    def register(self, account_uri: str, username: str, password: str) -> None:
        """Register with SIP server.

        Args:
            account_uri: SIP server URI (e.g., "sip.example.com" or "192.168.1.1")
            username: SIP username
            password: SIP password
        """
        with self._lock:
            if self._phone is not None:
                logger.warning("Already registered, ignoring register request")
                return

            # Parse account_uri to extract server and port
            # Format can be: "sip.example.com" or "sip.example.com:5060"
            server, port = self._parse_server_uri(account_uri)

            self._set_call_state(CallState.REGISTERING)
            logger.info("Registering with SIP server: %s:%d (user: %s)", server, port, username)

            try:
                # Create VoIPPhone instance
                # Use sipPort=0 to let OS assign a random free port for the client
                self._phone = VoIPPhone(
                    server=server,
                    port=port,
                    username=username,
                    password=password,
                    callCallback=self._on_incoming_call_internal,
                    sipPort=0,
                )

                # Start the phone (begins registration)
                self._phone.start()

                # Monitor registration status
                self._monitor_registration()

            except SIPError:
                self._phone = None
                self._set_call_state(CallState.IDLE)
                raise
            except Exception as e:
                logger.error("Registration failed: %s", e)
                self._phone = None
                self._set_call_state(CallState.IDLE)
                raise SIPRegistrationError(str(e), server=server) from e

    def _parse_server_uri(self, uri: str) -> tuple[str, int]:
        """Parse SIP server URI to extract server and port.

        Args:
            uri: Server URI (e.g., "sip.example.com" or "192.168.1.1:5060")

        Returns:
            Tuple of (server, port)
        """
        # Remove sip: prefix if present
        if uri.startswith("sip:"):
            uri = uri[4:]

        # Split server and port
        if ":" in uri:
            parts = uri.split(":")
            server = parts[0]
            port = int(parts[1])
        else:
            server = uri
            port = 5060  # Default SIP port

        return server, port

    def _monitor_registration(self) -> None:
        """Monitor registration status and update state."""
        if self._phone is None:
            return

        # Wait for registration to complete
        # pyVoIP handles this automatically, we just check status
        poll_interval = 0.1
        max_iterations = int(self._registration_timeout / poll_interval)
        for _ in range(max_iterations):
            status = self._phone.get_status()
            if status == PyVoIPPhoneStatus.REGISTERED:
                self._set_call_state(CallState.REGISTERED)
                logger.info("Registration successful")
                return
            if status == PyVoIPPhoneStatus.FAILED:
                logger.error("Registration failed")
                self._set_call_state(CallState.IDLE)
                return
            time.sleep(poll_interval)

        # Timeout
        logger.warning("Registration timeout after %.1f seconds", self._registration_timeout)

    def unregister(self) -> None:
        """Unregister from SIP server."""
        with self._lock:
            if self._phone is None:
                logger.debug("Already unregistered")
                return

            logger.info("Unregistering from SIP server")

            # Hang up any active call
            if self._current_call is not None:
                try:
                    self._current_call.hangup()
                except Exception as e:
                    logger.warning("Error hanging up call during unregister: %s", e)
                self._current_call = None

            # Stop the phone
            try:
                self._phone.stop()
            except Exception as e:
                logger.warning("Error stopping phone: %s", e)

            self._phone = None
            self._set_call_state(CallState.IDLE)

    def make_call(self, destination: str) -> None:
        """Initiate an outgoing call.

        Args:
            destination: Destination phone number or SIP URI
        """
        with self._lock:
            if self._phone is None or self._call_state != CallState.REGISTERED:
                logger.warning(
                    "Cannot make call in state: %s (must be REGISTERED)", self._call_state.value
                )
                return

            if self._current_call is not None:
                logger.warning("Already in a call, ignoring make_call request")
                return

            self._set_call_state(CallState.CALLING)
            logger.info("Making call to: %s", destination)

            try:
                # Initiate call
                self._current_call = self._phone.call(destination)

                # Monitor call state
                self._monitor_call_state()

            except SIPError:
                self._current_call = None
                self._set_call_state(CallState.REGISTERED)
                raise
            except Exception as e:
                logger.error("Error making call: %s", e)
                self._current_call = None
                self._set_call_state(CallState.REGISTERED)
                raise SIPCallError(str(e), number=destination, direction="outbound") from e

    def _monitor_call_state(self) -> None:
        """Monitor call state in background thread."""
        # Start a background thread to monitor call state changes
        thread = threading.Thread(target=self._call_state_monitor, daemon=True)
        thread.start()

    def _call_state_monitor(self) -> None:
        """Background thread to monitor call state.

        Polls pyVoIP's call.state under _lock so reads and our own state
        transitions are atomic with hangup()/reject_call(). The transition that
        clears _current_call also fires the matching callback, so concurrent
        teardown can't double-fire on_call_ended.
        """
        while True:
            fire_answered = False
            fire_ended = False

            with self._lock:
                current_call = self._current_call
                if current_call is None:
                    # hangup()/reject_call() already cleared the call.
                    return

                try:
                    pyvoip_state = current_call.state
                except Exception as e:
                    logger.error("Error reading pyVoIP call state: %s", e)
                    return

                if (
                    pyvoip_state == PyVoIPCallState.ANSWERED
                    and self._call_state != CallState.CONNECTED
                ):
                    logger.info("Call answered")
                    self._set_call_state(CallState.CONNECTED)
                    fire_answered = True
                elif pyvoip_state == PyVoIPCallState.ENDED:
                    logger.info("Call ended")
                    # Skip intermediate DISCONNECTED state
                    self._set_call_state(CallState.REGISTERED)
                    self._current_call = None
                    fire_ended = True

            if fire_answered and self._on_call_answered:
                self._on_call_answered()
            if fire_ended:
                if self._on_call_ended:
                    self._on_call_ended()
                return

            time.sleep(0.1)

    def answer_call(self) -> None:
        """Answer an incoming call."""
        with self._lock:
            if self._current_call is None or self._call_state != CallState.RINGING:
                logger.warning(
                    "Cannot answer call in state: %s (must be RINGING)", self._call_state.value
                )
                return

            logger.info("Answering call")

            try:
                self._current_call.answer()
                self._set_call_state(CallState.CONNECTED)

                if self._on_call_answered:
                    self._on_call_answered()

            except Exception as e:
                logger.error("Error answering call: %s", e)
                raise

    def hangup(self) -> None:
        """Hang up the current call."""
        with self._lock:
            if self._current_call is None:
                logger.debug("No active call to hang up")
                return

            logger.info("Hanging up call")

            try:
                self._current_call.hangup()
            except Exception as e:
                logger.warning("Error hanging up call: %s", e)

            self._current_call = None
            # Go directly back to REGISTERED (skip intermediate DISCONNECTED state)
            self._set_call_state(CallState.REGISTERED)

            if self._on_call_ended:
                self._on_call_ended()

    def reject_call(self) -> None:
        """Reject an incoming call without answering."""
        with self._lock:
            if self._current_call is None or self._call_state != CallState.RINGING:
                logger.debug("No incoming call to reject")
                return

            logger.info("Rejecting incoming call")

            try:
                self._current_call.deny()
            except Exception as e:
                logger.warning("Error rejecting call: %s", e)

            self._current_call = None
            self._set_call_state(CallState.REGISTERED)

            if self._on_call_ended:
                self._on_call_ended()

    def get_current_call(self) -> Optional[Any]:
        """Get the current VoIPCall object for audio handling.

        Returns:
            VoIPCall if in a call, None otherwise
        """
        with self._lock:
            return self._current_call

    def _on_incoming_call_internal(self, call: VoIPCall) -> None:
        """Internal callback for incoming calls from pyVoIP.

        Args:
            call: Incoming VoIPCall object
        """
        with self._lock:
            if self._current_call is not None:
                logger.warning("Already in a call, denying incoming call")
                call.deny()
                return

            # Extract caller ID from call request
            caller_id = self._extract_caller_id(call)
            logger.info("Incoming call from: %s", caller_id)

            self._current_call = call
            self._set_call_state(CallState.RINGING)

            # Start monitoring this call
            self._monitor_call_state()

        # Trigger callback outside lock
        if self._on_incoming_call:
            self._on_incoming_call(caller_id)

    def _extract_caller_id(self, call: VoIPCall) -> str:
        """Extract caller ID from VoIPCall.

        Args:
            call: VoIPCall object

        Returns:
            Caller ID string
        """
        try:
            from_header = str(call.request.headers.get("From", "Unknown"))
        except AttributeError as e:
            logger.warning("pyVoIP call shape changed, caller ID unavailable: %s", e)
            return "Unknown"

        # Parse SIP URI from From header (e.g., "Alice <sip:alice@example.com>")
        if "<" in from_header and ">" in from_header:
            start = from_header.index("<") + 1
            end = from_header.index(">")
            return from_header[start:end]
        return from_header

    def send_audio_file(
        self, file_path: str, stop_check: Optional[Callable[[], bool]] = None
    ) -> bool:
        """Send audio from a WAV file through the current call.

        The WAV file can be any standard format - it will be automatically
        resampled to 8 kHz and encoded to μ-law for transmission. The pyVoIP
        patches in :mod:`rotary_phone.audio.pyvoip_patches` make write_audio()
        pass μ-law bytes through unmodified.

        Args:
            file_path: Path to WAV file
            stop_check: Optional callback that returns True if audio should stop

        Returns:
            True if audio completed, False if interrupted

        Raises:
            RuntimeError: If no active call or file cannot be read
        """
        with self._lock:
            if self._current_call is None or self._call_state != CallState.CONNECTED:
                raise RuntimeError(f"No connected call (state: {self._call_state.value})")
            call = self._current_call

        logger.info("Sending audio file: %s", file_path)

        try:
            ulaw_data = self._decode_wav_to_ulaw(file_path)
        except FileNotFoundError as exc:
            raise RuntimeError(f"Audio file not found: {file_path}") from exc

        logger.info("Sending %d bytes of audio", len(ulaw_data))
        call.write_audio(ulaw_data)

        # At 8kHz μ-law (8-bit), 1 byte = 1 sample = 125µs
        duration = len(ulaw_data) / 8000.0
        return self._wait_for_audio(duration, stop_check)

    @staticmethod
    def _decode_wav_to_ulaw(file_path: str) -> bytes:
        """Read a WAV file and return μ-law-encoded 8 kHz mono audio."""
        with wave.open(file_path, "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            framerate = wav.getframerate()
            frames = wav.getnframes()
            audio_data = wav.readframes(frames)

        logger.info(
            "WAV format: %d Hz, %d-bit, %d channel(s), %d frames",
            framerate,
            sample_width * 8,
            channels,
            frames,
        )

        if channels == 2:
            audio_data = audioop.tomono(audio_data, sample_width, 0.5, 0.5)

        if framerate != 8000:
            logger.info("Resampling from %d Hz to 8000 Hz", framerate)
            audio_data, _ = audioop.ratecv(audio_data, sample_width, 1, framerate, 8000, None)

        # WAV's 8-bit PCM is unsigned per spec; flip bias before widening to signed.
        if sample_width == 1:
            audio_data = audioop.bias(audio_data, 1, -128)
        if sample_width != 2:
            audio_data = audioop.lin2lin(audio_data, sample_width, 2)

        return audioop.lin2ulaw(audio_data, 2)

    @staticmethod
    def _wait_for_audio(duration: float, stop_check: Optional[Callable[[], bool]]) -> bool:
        """Sleep for `duration` seconds in short increments, polling stop_check.

        Returns True if the full duration elapsed, False if stop_check tripped.
        """
        logger.info("Waiting %.2f seconds for audio to play", duration)
        interval = 0.1
        deadline = time.monotonic() + duration
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.info("Audio sent successfully")
                return True
            if stop_check and stop_check():
                logger.info("Audio playback interrupted, %.2fs remaining", remaining)
                return False
            time.sleep(min(interval, remaining))
