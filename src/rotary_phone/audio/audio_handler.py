"""USB audio handler for bidirectional audio during VoIP calls.

This module provides the AudioHandler class which bridges USB audio devices
with pyVoIP's read_audio()/write_audio() methods for real-time call audio.

pyVoIP's read_audio() returns LINEAR audio (already decoded from μ-law internally)
and write_audio() expects LINEAR audio (encodes to μ-law internally).
The format is 8-bit unsigned PCM where 128 (0x80) is silence.
"""

import audioop  # pylint: disable=deprecated-module
import logging
import threading
import time
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Audio format constants
VOIP_SAMPLE_RATE = 8000  # 8 kHz for VoIP
VOIP_FRAME_SIZE = 160  # 160 samples = 20ms at 8kHz
CHANNELS = 1  # Mono

# Backward compatibility aliases
SAMPLE_RATE = VOIP_SAMPLE_RATE
FRAME_SIZE = VOIP_FRAME_SIZE

# pyVoIP returns 8-bit unsigned linear PCM (0x80 = silence)
# We need to convert to/from 16-bit signed for PyAudio
PYVOIP_SAMPLE_WIDTH = 1  # 8-bit
PYAUDIO_SAMPLE_WIDTH = 2  # 16-bit

# Common sample rates to try if device doesn't support 8kHz
# Prefer 48kHz (clean 6:1 ratio) over 44.1kHz (5.5125:1 causes artifacts)
FALLBACK_SAMPLE_RATES = [8000, 48000, 16000, 44100]


class AudioError(Exception):
    """Base exception for audio errors."""


class AudioDeviceNotFoundError(AudioError):
    """No suitable audio device found."""


class AudioHandler:  # pylint: disable=too-many-instance-attributes
    """Handles bidirectional USB audio for VoIP calls.

    Captures microphone audio, converts format, and sends via VoIPCall.write_audio().
    Receives audio via VoIPCall.read_audio(), converts format, and plays to speaker.

    pyVoIP uses 8-bit unsigned linear PCM (0x80 = silence).
    PyAudio uses 16-bit signed linear PCM (0 = silence).

    The handler auto-detects USB audio devices by looking for "USB" in
    the device name. An explicit device name can be specified to override
    auto-detection.
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

        # Device sample rate (may differ from VoIP rate, requiring resampling)
        self._device_sample_rate: int = VOIP_SAMPLE_RATE
        self._device_frame_size: int = VOIP_FRAME_SIZE

        # Resampling state for audioop.ratecv()
        self._capture_resample_state: Any = None
        self._playback_resample_state: Any = None

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

            # Find a supported sample rate
            self._device_sample_rate = self._find_supported_sample_rate()
            if self._device_sample_rate != VOIP_SAMPLE_RATE:
                # Calculate frame size for device rate (maintain 20ms frames)
                self._device_frame_size = int(self._device_sample_rate * 0.02)
                logger.info(
                    "Using device sample rate %d Hz (will resample to/from %d Hz)",
                    self._device_sample_rate,
                    VOIP_SAMPLE_RATE,
                )
            else:
                self._device_frame_size = VOIP_FRAME_SIZE
                logger.info("Using native VoIP sample rate %d Hz", VOIP_SAMPLE_RATE)

            # Reset resampling state
            self._capture_resample_state = None
            self._playback_resample_state = None

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

    def _find_supported_sample_rate(self) -> int:
        """Find a sample rate supported by both input and output devices.

        Tries VOIP_SAMPLE_RATE (8kHz) first, then falls back to common rates.

        Returns:
            Supported sample rate in Hz
        """
        import pyaudio  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

        for rate in FALLBACK_SAMPLE_RATES:
            try:
                # Test if input device supports this rate
                if self._input_device_index is not None:
                    input_supported = self._pyaudio.is_format_supported(
                        rate,
                        input_device=self._input_device_index,
                        input_channels=CHANNELS,
                        input_format=pyaudio.paInt16,
                    )
                else:
                    input_supported = True

                # Test if output device supports this rate
                if self._output_device_index is not None:
                    output_supported = self._pyaudio.is_format_supported(
                        rate,
                        output_device=self._output_device_index,
                        output_channels=CHANNELS,
                        output_format=pyaudio.paInt16,
                    )
                else:
                    output_supported = True

                if input_supported and output_supported:
                    logger.debug("Sample rate %d Hz is supported", rate)
                    return rate

            except ValueError:
                logger.debug("Sample rate %d Hz not supported", rate)
                continue

        # If nothing worked, return 8kHz and hope for the best
        logger.warning("Could not detect supported sample rate, defaulting to %d Hz", VOIP_SAMPLE_RATE)
        return VOIP_SAMPLE_RATE

    def _capture_loop(self) -> None:
        """Background thread: capture microphone audio and send to VoIP.

        Flow:
        1. Open PyAudio input stream (16-bit signed PCM at device sample rate)
        2. Read 20ms frame
        3. Apply input gain
        4. Resample to 8kHz if needed
        5. Convert 16-bit signed -> 8-bit unsigned for pyVoIP
        6. Send to VoIPCall.write_audio()
        """
        import pyaudio  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

        stream = None
        resample_state = None
        try:
            stream = self._pyaudio.open(
                format=pyaudio.paInt16,  # 16-bit signed for PyAudio
                channels=CHANNELS,
                rate=self._device_sample_rate,
                input=True,
                input_device_index=self._input_device_index,
                frames_per_buffer=self._device_frame_size,
            )
            logger.debug("Capture stream opened at %d Hz", self._device_sample_rate)

            while not self._stop_event.is_set():
                try:
                    # Read 16-bit signed PCM from microphone
                    pcm_data = stream.read(self._device_frame_size, exception_on_overflow=False)

                    # Apply input gain if not 1.0
                    if self._input_gain != 1.0:
                        pcm_data = audioop.mul(pcm_data, 2, self._input_gain)

                    # Resample to VoIP rate (8kHz) if needed
                    if self._device_sample_rate != VOIP_SAMPLE_RATE:
                        pcm_data, resample_state = audioop.ratecv(
                            pcm_data,
                            2,  # sample width (16-bit = 2 bytes)
                            CHANNELS,
                            self._device_sample_rate,
                            VOIP_SAMPLE_RATE,
                            resample_state,
                        )

                    # Convert 16-bit signed -> 8-bit unsigned for pyVoIP
                    # pyVoIP expects 8-bit unsigned where 128 = silence
                    linear_8bit = audioop.lin2lin(pcm_data, 2, 1)  # 16-bit to 8-bit signed
                    # Convert signed to unsigned by adding 128 (XOR with 0x80)
                    unsigned_8bit = audioop.bias(linear_8bit, 1, 128)

                    # Send to VoIP call
                    if self._voip_call:
                        try:
                            self._voip_call.write_audio(unsigned_8bit)
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

    def _process_playback_frame(self, stream: Any, resample_state: Any) -> Any:
        """Process a single playback frame from the VoIP call.

        Args:
            stream: PyAudio output stream to write to
            resample_state: Current resampling state (for audioop.ratecv)

        Returns:
            Updated resample_state
        """
        # Read linear audio from VoIP call
        if not self._voip_call:
            # No active call, brief sleep
            time.sleep(0.02)
            return resample_state

        try:
            # read_audio returns 8-bit unsigned linear PCM (128 = silence)
            unsigned_8bit = self._voip_call.read_audio(VOIP_FRAME_SIZE, blocking=True)
        except Exception as e:
            logger.debug("Error reading audio: %s", e)
            # Brief sleep to avoid busy loop on error
            time.sleep(0.02)
            return resample_state

        if not unsigned_8bit:
            return resample_state

        # Convert 8-bit unsigned -> 16-bit signed for PyAudio
        # First convert unsigned to signed by subtracting 128 (bias)
        signed_8bit = audioop.bias(unsigned_8bit, 1, -128)
        # Then convert 8-bit to 16-bit
        pcm_data = audioop.lin2lin(signed_8bit, 1, 2)

        # Apply output volume if not 1.0
        if self._output_volume != 1.0:
            pcm_data = audioop.mul(pcm_data, 2, self._output_volume)

        # Resample from VoIP rate (8kHz) to device rate if needed
        if self._device_sample_rate != VOIP_SAMPLE_RATE:
            pcm_data, resample_state = audioop.ratecv(
                pcm_data,
                2,  # sample width (16-bit = 2 bytes)
                CHANNELS,
                VOIP_SAMPLE_RATE,
                self._device_sample_rate,
                resample_state,
            )

        # Play to speaker
        stream.write(pcm_data)
        return resample_state

    def _playback_loop(self) -> None:
        """Background thread: receive audio from VoIP and play to speaker.

        Flow:
        1. Open PyAudio output stream (16-bit signed PCM at device sample rate)
        2. Call VoIPCall.read_audio() to get 8-bit unsigned linear PCM
        3. Convert 8-bit unsigned -> 16-bit signed
        4. Apply output volume
        5. Resample to device rate if needed
        6. Write to speaker
        """
        import pyaudio  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

        stream = None
        resample_state = None
        try:
            stream = self._pyaudio.open(
                format=pyaudio.paInt16,  # 16-bit signed for PyAudio
                channels=CHANNELS,
                rate=self._device_sample_rate,
                output=True,
                output_device_index=self._output_device_index,
                frames_per_buffer=self._device_frame_size,
            )
            logger.debug("Playback stream opened at %d Hz", self._device_sample_rate)

            while not self._stop_event.is_set():
                try:
                    resample_state = self._process_playback_frame(stream, resample_state)
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
