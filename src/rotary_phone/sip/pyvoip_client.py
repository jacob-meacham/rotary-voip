"""PyVoIP-based SIP client implementation for real VoIP calling.

This module provides a SIP client implementation using the pyVoIP library
for making real VoIP calls.
"""

import logging
import threading
import time
from typing import Callable, Optional

from pyVoIP.VoIP import CallState as PyVoIPCallState
from pyVoIP.VoIP import PhoneStatus as PyVoIPPhoneStatus
from pyVoIP.VoIP import VoIPCall, VoIPPhone

from rotary_phone.sip.sip_client import CallState, SIPClient

logger = logging.getLogger(__name__)


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
    ) -> None:
        """Initialize the PyVoIP SIP client.

        Args:
            on_incoming_call: Callback when incoming call arrives
            on_call_answered: Callback when call is answered
            on_call_ended: Callback when call ends
        """
        super().__init__(on_incoming_call, on_call_answered, on_call_ended)
        self._phone: Optional[VoIPPhone] = None
        self._current_call: Optional[VoIPCall] = None
        self._lock = threading.RLock()

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

            except Exception as e:
                logger.error("Registration failed: %s", e)
                self._phone = None
                self._set_call_state(CallState.IDLE)
                raise

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
        for _ in range(50):  # Wait up to 5 seconds
            status = self._phone.get_status()
            if status == PyVoIPPhoneStatus.REGISTERED:
                self._set_call_state(CallState.REGISTERED)
                logger.info("Registration successful")
                return
            if status == PyVoIPPhoneStatus.FAILED:
                logger.error("Registration failed")
                self._set_call_state(CallState.IDLE)
                return
            time.sleep(0.1)

        # Timeout
        logger.warning("Registration timeout")

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

            except Exception as e:
                logger.error("Error making call: %s", e)
                self._current_call = None
                self._set_call_state(CallState.REGISTERED)
                raise

    def _monitor_call_state(self) -> None:
        """Monitor call state in background thread."""
        # Start a background thread to monitor call state changes
        thread = threading.Thread(target=self._call_state_monitor, daemon=True)
        thread.start()

    def _call_state_monitor(self) -> None:
        """Background thread to monitor call state."""
        while self._current_call is not None:
            try:
                # Check call state
                call_state = self._current_call.state
                current_state = self._call_state

                # Map pyVoIP call state to our state
                if call_state == PyVoIPCallState.ANSWERED and current_state != CallState.CONNECTED:
                    logger.info("Call answered")
                    self._set_call_state(CallState.CONNECTED)
                    if self._on_call_answered:
                        self._on_call_answered()

                elif call_state == PyVoIPCallState.ENDED:
                    logger.info("Call ended")
                    self._set_call_state(CallState.DISCONNECTED)
                    self._set_call_state(CallState.REGISTERED)
                    if self._on_call_ended:
                        self._on_call_ended()
                    self._current_call = None
                    break

                time.sleep(0.1)  # Poll every 100ms

            except Exception as e:
                logger.error("Error in call state monitor: %s", e)
                break

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
            self._set_call_state(CallState.DISCONNECTED)
            self._set_call_state(CallState.REGISTERED)

            if self._on_call_ended:
                self._on_call_ended()

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
            # Try to get From header from SIP request
            if hasattr(call, "request") and hasattr(call.request, "headers"):
                from_header = str(call.request.headers.get("From", "Unknown"))
                # Parse SIP URI from From header (e.g., "Alice <sip:alice@example.com>")
                if "<" in from_header:
                    start = from_header.index("<") + 1
                    end = from_header.index(">")
                    return from_header[start:end]
                return from_header
        except Exception as e:
            logger.warning("Error extracting caller ID: %s", e)

        return "Unknown"

    def send_audio_file(self, file_path: str, stop_check: Optional[Callable[[], bool]] = None) -> bool:
        """Send audio from a WAV file through the current call.

        The WAV file should be 8kHz, 8-bit μ-law (PCMU) format for best quality.
        Other formats will be automatically converted.

        Args:
            file_path: Path to WAV file
            stop_check: Optional callback that returns True if audio should stop

        Returns:
            True if audio completed, False if interrupted

        Raises:
            RuntimeError: If no active call or file cannot be read
        """
        import audioop
        import wave

        with self._lock:
            if self._current_call is None or self._call_state != CallState.CONNECTED:
                raise RuntimeError(f"No connected call (state: {self._call_state.value})")

        logger.info("Sending audio file: %s", file_path)

        try:
            # Open and read WAV file
            with wave.open(file_path, "rb") as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                framerate = wav.getframerate()
                frames = wav.getnframes()

                logger.info(
                    "WAV format: %d Hz, %d-bit, %d channel(s), %d frames",
                    framerate,
                    sample_width * 8,
                    channels,
                    frames,
                )

                # Read all frames
                audio_data = wav.readframes(frames)

            # Convert to mono if stereo
            if channels == 2:
                logger.info("Converting stereo to mono")
                audio_data = audioop.tomono(audio_data, sample_width, 0.5, 0.5)
                channels = 1

            # Resample to 8kHz if needed
            if framerate != 8000:
                logger.info("Resampling from %d Hz to 8000 Hz", framerate)
                audio_data, _ = audioop.ratecv(audio_data, sample_width, 1, framerate, 8000, None)
                # Recalculate frames after resampling
                frames = len(audio_data) // sample_width
                framerate = 8000

            # Convert to 16-bit linear PCM if needed, then to μ-law
            if sample_width != 1:  # Not already 8-bit
                if sample_width != 2:
                    logger.info("Converting to 16-bit")
                    audio_data = audioop.lin2lin(audio_data, sample_width, 2)

                # Convert 16-bit linear PCM to 8-bit μ-law
                logger.info("Converting to G.711 μ-law (PCMU)")
                audio_data = audioop.lin2ulaw(audio_data, 2)
            else:
                # Assume it's already μ-law encoded
                logger.info("Audio appears to be 8-bit (assuming μ-law)")

            # Send all audio at once (pyVoIP will handle packetization)
            logger.info("Sending %d bytes of audio", len(audio_data))
            self._current_call.write_audio(audio_data)

            # Wait for the audio to finish playing (checking for interruption)
            # At 8kHz μ-law (8-bit), we have 8000 bytes per second
            duration = len(audio_data) / 8000.0
            logger.info("Waiting %.2f seconds for audio to play", duration)

            # Wait in small intervals so we can check for interruption
            elapsed = 0.0
            interval = 0.1  # Check every 100ms
            while elapsed < duration:
                if stop_check and stop_check():
                    logger.info("Audio playback interrupted after %.2f seconds", elapsed)
                    return False

                time.sleep(min(interval, duration - elapsed))
                elapsed += interval

            logger.info("Audio sent successfully")
            return True

        except FileNotFoundError:
            logger.error("Audio file not found: %s", file_path)
            raise RuntimeError(f"Audio file not found: {file_path}")
        except Exception as e:
            logger.error("Error sending audio: %s", e)
            raise RuntimeError(f"Error sending audio: {e}")
