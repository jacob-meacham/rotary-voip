"""Ringer control for rotary phone hardware.

This module provides the Ringer class for controlling the phone's ringer
with configurable ring patterns. Works with speakers, buzzers, or mechanical
ringers via GPIO control of amplifier/transistor circuits.
"""

import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from rotary_phone.hardware import RINGER
from rotary_phone.hardware.gpio_abstraction import GPIO

logger = logging.getLogger(__name__)


class Ringer:
    """Controls the phone ringer/speaker with configurable ring patterns.

    The ringer can operate in two modes:
    1. Audio playback mode (sound_file provided): Plays a sound file through aplay
       while GPIO controls amplifier enable pin
    2. GPIO toggle mode (no sound_file): Just toggles GPIO HIGH/LOW for buzzers

    Standard North American ring pattern is 2 seconds on, 4 seconds off.
    """

    def __init__(
        self,
        gpio: GPIO,
        ring_on_duration: float = 2.0,
        ring_off_duration: float = 4.0,
        sound_file: Optional[str] = None,
    ) -> None:
        """Initialize the ringer.

        Args:
            gpio: GPIO abstraction instance
            ring_on_duration: Duration in seconds for ringer on state (default 2.0)
            ring_off_duration: Duration in seconds for ringer off state (default 4.0)
            sound_file: Optional path to WAV file to play when ringing
        """
        self._gpio = gpio
        self._ring_on_duration = ring_on_duration
        self._ring_off_duration = ring_off_duration
        self._sound_file = sound_file
        self._is_ringing = False
        self._ring_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()  # Reentrant lock for nested calls

        # Validate sound file if provided
        if self._sound_file and not Path(self._sound_file).exists():
            logger.warning("Sound file not found: %s (will use GPIO toggle mode)", self._sound_file)
            self._sound_file = None

        # Set up RINGER pin as output, initially LOW (ringer off)
        self._gpio.setup(RINGER, GPIO.OUT)
        self._gpio.output(RINGER, GPIO.LOW)

        mode = "audio playback" if self._sound_file else "GPIO toggle"
        logger.debug(
            "Ringer initialized (mode=%s, on=%.1fs, off=%.1fs)",
            mode,
            ring_on_duration,
            ring_off_duration,
        )

    def start_ringing(self) -> None:
        """Start the ring pattern.

        If already ringing, this method has no effect.
        """
        with self._lock:
            if self._is_ringing:
                logger.debug("Ringer already active, ignoring start request")
                return

            self._is_ringing = True
            logger.info("Starting ringer")

            # Start ring loop in background thread
            self._ring_thread = threading.Thread(target=self._ring_loop, daemon=True)
            self._ring_thread.start()

    def stop_ringing(self) -> None:
        """Stop the ring pattern.

        If not ringing, this method has no effect.
        """
        with self._lock:
            if not self._is_ringing:
                logger.debug("Ringer already stopped, ignoring stop request")
                return

            self._is_ringing = False
            logger.info("Stopping ringer")

            # Turn off ringer GPIO
            self._gpio.output(RINGER, GPIO.LOW)

        # Wait for ring thread to complete (outside lock to avoid deadlock)
        if self._ring_thread is not None:
            self._ring_thread.join(timeout=1.0)
            self._ring_thread = None

    def is_ringing(self) -> bool:
        """Check if the ringer is currently active.

        Returns:
            True if ringing, False otherwise
        """
        with self._lock:
            return self._is_ringing

    def _ring_loop(self) -> None:
        """Ring pattern loop - runs in background thread."""
        while True:
            with self._lock:
                if not self._is_ringing:
                    break

            # Enable amplifier and play ring
            if self._sound_file:
                self._play_audio_ring()
            else:
                self._gpio_toggle_ring()

            with self._lock:
                if not self._is_ringing:
                    break

            # Pause between rings
            logger.debug("Ring pause (%.1fs)", self._ring_off_duration)
            time.sleep(self._ring_off_duration)

    def _play_audio_ring(self) -> None:
        """Play ring sound through aplay with GPIO controlling amplifier."""
        # Type narrowing: this method is only called when _sound_file is not None
        assert self._sound_file is not None

        try:
            # Enable amplifier
            self._gpio.output(RINGER, GPIO.HIGH)
            logger.debug("Ring on (playing %s)", self._sound_file)

            # Play sound file
            # Use timeout slightly longer than ring duration to prevent hanging
            subprocess.run(
                ["aplay", "-q", self._sound_file],
                capture_output=True,
                timeout=self._ring_on_duration + 1.0,
                check=False,  # Don't raise on non-zero exit
            )

            # Disable amplifier
            self._gpio.output(RINGER, GPIO.LOW)

        except subprocess.TimeoutExpired:
            logger.warning("aplay timeout - ring sound may be longer than ring_on_duration")
            self._gpio.output(RINGER, GPIO.LOW)
        except FileNotFoundError:
            logger.error("aplay command not found - falling back to GPIO toggle mode")
            self._sound_file = None  # Disable audio mode
            self._gpio_toggle_ring()
        except Exception as e:
            logger.error("Error playing ring sound: %s", e)
            self._gpio.output(RINGER, GPIO.LOW)

    def _gpio_toggle_ring(self) -> None:
        """Simple GPIO toggle for buzzers (no audio playback)."""
        self._gpio.output(RINGER, GPIO.HIGH)
        logger.debug("Ring on (GPIO toggle)")
        time.sleep(self._ring_on_duration)
        self._gpio.output(RINGER, GPIO.LOW)
