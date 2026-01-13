"""USB audio handler for bidirectional audio during VoIP calls.

This module provides the AudioHandler class which bridges USB audio devices
with pyVoIP's read_audio()/write_audio() methods for real-time call audio.
"""

import audioop  # pylint: disable=deprecated-module
import logging
import threading
import time
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Audio format constants for G.711 μ-law (PCMU)
SAMPLE_RATE = 8000  # 8 kHz
FRAME_SIZE = 160  # 160 samples = 20ms at 8kHz
CHANNELS = 1  # Mono


class AudioError(Exception):
    """Base exception for audio errors."""


class AudioDeviceNotFoundError(AudioError):
    """No suitable audio device found."""


class AudioHandler:  # pylint: disable=too-many-instance-attributes
    """Handles bidirectional USB audio for VoIP calls.

    Captures microphone audio, converts to G.711 μ-law, and sends via
    VoIPCall.write_audio(). Receives audio via VoIPCall.read_audio(),
    converts from μ-law, and plays to speaker.

    The handler auto-detects USB audio devices by looking for "USB" in
    the device name. An explicit device name can be specified to override
    auto-detection.

    Pattern follows DialTone/Ringer: threaded background operation with stop_event.
    """

    def __init__(
        self,
        device_name: Optional[str] = None,
        input_gain: float = 1.0,
        output_volume: float = 1.0,
    ) -> None:
        """Initialize the audio handler.

        Args:
            device_name: Explicit device name to use (auto-detect if None)
            input_gain: Microphone gain multiplier (0.0-2.0, 1.0 = no change)
            output_volume: Speaker volume multiplier (0.0-2.0, 1.0 = no change)

        Raises:
            ValueError: If gain or volume is out of range
        """
        if not 0.0 <= input_gain <= 2.0:
            raise ValueError(f"input_gain must be between 0.0 and 2.0, got {input_gain}")
        if not 0.0 <= output_volume <= 2.0:
            raise ValueError(f"output_volume must be between 0.0 and 2.0, got {output_volume}")

        self._device_name = device_name
        self._input_gain = input_gain
        self._output_volume = output_volume

        self._pyaudio: Any = None
        self._input_device_index: Optional[int] = None
        self._output_device_index: Optional[int] = None
        self._voip_call: Any = None

        self._capture_thread: Optional[threading.Thread] = None
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._is_running = False

        logger.debug(
            "AudioHandler initialized (device=%s, gain=%.2f, volume=%.2f)",
            device_name or "auto",
            input_gain,
            output_volume,
        )

    def start(self, voip_call: Any) -> None:
        """Start audio capture and playback for a VoIP call.

        Args:
            voip_call: The VoIPCall object with read_audio()/write_audio() methods

        Raises:
            AudioDeviceNotFoundError: If no suitable audio device found
            RuntimeError: If already running
        """
        with self._lock:
            if self._is_running:
                logger.warning("AudioHandler already running")
                return

            logger.info("Starting audio handler")
            self._voip_call = voip_call
            self._stop_event.clear()

            # Initialize PyAudio
            try:
                import pyaudio  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

                self._pyaudio = pyaudio.PyAudio()
            except ImportError as e:
                logger.error("PyAudio not installed: %s", e)
                raise AudioError("PyAudio not installed") from e
            except Exception as e:
                logger.error("Failed to initialize PyAudio: %s", e)
                raise AudioError(f"Failed to initialize PyAudio: {e}") from e

            # Find audio devices
            try:
                self._input_device_index, self._output_device_index = self._find_audio_devices()
            except AudioDeviceNotFoundError:
                self._cleanup_pyaudio()
                raise

            # Start capture thread
            self._capture_thread = threading.Thread(
                target=self._capture_loop, daemon=True, name="AudioCapture"
            )
            self._capture_thread.start()

            # Start playback thread
            self._playback_thread = threading.Thread(
                target=self._playback_loop, daemon=True, name="AudioPlayback"
            )
            self._playback_thread.start()

            self._is_running = True
            logger.info("Audio handler started")

    def stop(self) -> None:
        """Stop audio capture and playback."""
        with self._lock:
            if not self._is_running:
                return

            logger.info("Stopping audio handler")
            self._is_running = False
            self._stop_event.set()

        # Wait for threads to finish (outside lock to avoid deadlock)
        if self._capture_thread:
            self._capture_thread.join(timeout=1.0)
            if self._capture_thread.is_alive():
                logger.warning("Capture thread did not stop in time")
            self._capture_thread = None

        if self._playback_thread:
            self._playback_thread.join(timeout=1.0)
            if self._playback_thread.is_alive():
                logger.warning("Playback thread did not stop in time")
            self._playback_thread = None

        # Cleanup
        with self._lock:
            self._voip_call = None
            self._cleanup_pyaudio()

        logger.info("Audio handler stopped")

    def is_running(self) -> bool:
        """Check if audio handler is currently running.

        Returns:
            True if running, False otherwise
        """
        with self._lock:
            return self._is_running

    def _cleanup_pyaudio(self) -> None:
        """Clean up PyAudio resources."""
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception as e:
                logger.warning("Error terminating PyAudio: %s", e)
            self._pyaudio = None

    def _find_audio_devices(  # pylint: disable=too-many-branches
        self,
    ) -> Tuple[Optional[int], Optional[int]]:
        """Find audio device indices for input and output.

        First looks for devices matching explicit device_name if set,
        otherwise auto-detects USB devices.

        Returns:
            Tuple of (input_device_index, output_device_index)

        Raises:
            AudioDeviceNotFoundError: If no suitable devices found
        """
        if not self._pyaudio:
            raise AudioError("PyAudio not initialized")

        input_idx: Optional[int] = None
        output_idx: Optional[int] = None

        device_count = self._pyaudio.get_device_count()
        logger.debug("Found %d audio devices", device_count)

        for i in range(device_count):
            try:
                info = self._pyaudio.get_device_info_by_index(i)
                name = info.get("name", "")
                max_input = info.get("maxInputChannels", 0)
                max_output = info.get("maxOutputChannels", 0)

                logger.debug("Device %d: %s (in=%d, out=%d)", i, name, max_input, max_output)

                # Check if device matches criteria
                matches = False
                if self._device_name:
                    # Explicit device name match (case-insensitive)
                    matches = self._device_name.lower() in name.lower()
                else:
                    # Auto-detect USB devices
                    matches = "usb" in name.lower()

                if matches:
                    if max_input > 0 and input_idx is None:
                        input_idx = i
                        logger.info("Selected input device: %s (index %d)", name, i)
                    if max_output > 0 and output_idx is None:
                        output_idx = i
                        logger.info("Selected output device: %s (index %d)", name, i)

            except Exception as e:
                logger.warning("Error getting device %d info: %s", i, e)

        # Fallback to default devices if USB not found
        if input_idx is None or output_idx is None:
            if self._device_name:
                # Explicit device requested but not found
                raise AudioDeviceNotFoundError(f"Audio device '{self._device_name}' not found")

            logger.warning("USB audio device not found, using system defaults")
            try:
                default_input = self._pyaudio.get_default_input_device_info()
                default_output = self._pyaudio.get_default_output_device_info()

                if input_idx is None:
                    input_idx = default_input.get("index")
                    logger.info(
                        "Using default input: %s (index %d)",
                        default_input.get("name"),
                        input_idx,
                    )
                if output_idx is None:
                    output_idx = default_output.get("index")
                    logger.info(
                        "Using default output: %s (index %d)",
                        default_output.get("name"),
                        output_idx,
                    )
            except Exception as e:
                raise AudioDeviceNotFoundError(f"No audio devices available: {e}") from e

        return input_idx, output_idx

    def _capture_loop(self) -> None:
        """Background thread: capture microphone audio and send to VoIP.

        Flow:
        1. Open PyAudio input stream (16-bit PCM at 8kHz)
        2. Read 160 samples (20ms frame)
        3. Apply input gain
        4. Convert 16-bit linear PCM to 8-bit μ-law
        5. Send to VoIPCall.write_audio()
        """
        import pyaudio  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

        stream = None
        try:
            stream = self._pyaudio.open(
                format=pyaudio.paInt16,  # 16-bit for capture
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=self._input_device_index,
                frames_per_buffer=FRAME_SIZE,
            )
            logger.debug("Capture stream opened")

            while not self._stop_event.is_set():
                try:
                    # Read 160 samples of 16-bit audio (320 bytes)
                    pcm_data = stream.read(FRAME_SIZE, exception_on_overflow=False)

                    # Apply input gain if not 1.0
                    if self._input_gain != 1.0:
                        pcm_data = audioop.mul(pcm_data, 2, self._input_gain)

                    # Convert 16-bit linear PCM to 8-bit μ-law (160 bytes output)
                    ulaw_data = audioop.lin2ulaw(pcm_data, 2)

                    # Send to VoIP call
                    if self._voip_call:
                        try:
                            self._voip_call.write_audio(ulaw_data)
                        except Exception as e:
                            # Call may have ended
                            logger.debug("Error writing audio: %s", e)
                            break

                except IOError as e:
                    # Handle buffer overflow gracefully
                    logger.debug("Capture buffer overflow: %s", e)

        except Exception as e:
            logger.error("Capture thread error: %s", e)

        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception as e:
                    logger.warning("Error closing capture stream: %s", e)
            logger.debug("Capture thread ended")

    def _process_playback_frame(self, stream: Any) -> None:
        """Process a single playback frame from the VoIP call.

        Args:
            stream: PyAudio output stream to write to
        """
        # Read μ-law audio from VoIP call
        if not self._voip_call:
            # No active call, brief sleep
            time.sleep(0.02)
            return

        try:
            # read_audio returns μ-law encoded bytes
            ulaw_data = self._voip_call.read_audio(FRAME_SIZE, blocking=True)
        except Exception as e:
            logger.debug("Error reading audio: %s", e)
            # Brief sleep to avoid busy loop on error
            time.sleep(0.02)
            return

        if not ulaw_data:
            return

        # Convert 8-bit μ-law to 16-bit linear PCM
        pcm_data = audioop.ulaw2lin(ulaw_data, 2)

        # Apply output volume if not 1.0
        if self._output_volume != 1.0:
            pcm_data = audioop.mul(pcm_data, 2, self._output_volume)

        # Play to speaker
        stream.write(pcm_data)

    def _playback_loop(self) -> None:
        """Background thread: receive audio from VoIP and play to speaker.

        Flow:
        1. Open PyAudio output stream (16-bit PCM at 8kHz)
        2. Call VoIPCall.read_audio(160) to get μ-law audio
        3. Convert 8-bit μ-law to 16-bit linear PCM
        4. Apply output volume
        5. Write to speaker
        """
        import pyaudio  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

        stream = None
        try:
            stream = self._pyaudio.open(
                format=pyaudio.paInt16,  # 16-bit for playback
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                output=True,
                output_device_index=self._output_device_index,
                frames_per_buffer=FRAME_SIZE,
            )
            logger.debug("Playback stream opened")

            while not self._stop_event.is_set():
                try:
                    self._process_playback_frame(stream)
                except IOError as e:
                    # Handle buffer underflow gracefully
                    logger.debug("Playback buffer underflow: %s", e)

        except Exception as e:
            logger.error("Playback thread error: %s", e)

        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception as e:
                    logger.warning("Error closing playback stream: %s", e)
            logger.debug("Playback thread ended")
