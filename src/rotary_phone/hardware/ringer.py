"""Ringer control for rotary phone hardware.

This module provides the Ringer class for controlling the phone's ringer
with configurable ring patterns.
"""

import logging
import threading
from typing import Optional

from rotary_phone.hardware import RINGER
from rotary_phone.hardware.gpio_abstraction import GPIO

logger = logging.getLogger(__name__)


class Ringer:
    """Controls the phone ringer with configurable ring patterns.

    The ringer alternates between on and off states with configurable durations.
    Standard North American ring pattern is 2 seconds on, 4 seconds off.
    """

    def __init__(
        self,
        gpio: GPIO,
        ring_on_duration: float = 2.0,
        ring_off_duration: float = 4.0,
    ) -> None:
        """Initialize the ringer.

        Args:
            gpio: GPIO abstraction instance
            ring_on_duration: Duration in seconds for ringer on state (default 2.0)
            ring_off_duration: Duration in seconds for ringer off state (default 4.0)
        """
        self._gpio = gpio
        self._ring_on_duration = ring_on_duration
        self._ring_off_duration = ring_off_duration
        self._is_ringing = False
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.RLock()  # Reentrant lock for nested calls

        # Set up RINGER pin as output, initially LOW (ringer off)
        self._gpio.setup(RINGER, GPIO.OUT)
        self._gpio.output(RINGER, GPIO.LOW)
        logger.debug(
            "Ringer initialized (on=%.1fs, off=%.1fs)", ring_on_duration, ring_off_duration
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
            self._start_ring_cycle()

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

            # Cancel any pending timer
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

            # Turn off ringer
            self._gpio.output(RINGER, GPIO.LOW)

    def is_ringing(self) -> bool:
        """Check if the ringer is currently active.

        Returns:
            True if ringing, False otherwise
        """
        with self._lock:
            return self._is_ringing

    def _start_ring_cycle(self) -> None:
        """Start a new ring cycle (ringer on phase)."""
        with self._lock:
            if not self._is_ringing:
                return

            # Turn on ringer
            self._gpio.output(RINGER, GPIO.HIGH)
            logger.debug("Ring on")

            # Schedule transition to off phase
            self._timer = threading.Timer(self._ring_on_duration, self._start_silent_cycle)
            self._timer.daemon = True
            self._timer.start()

    def _start_silent_cycle(self) -> None:
        """Start silent cycle (ringer off phase)."""
        with self._lock:
            if not self._is_ringing:
                return

            # Turn off ringer
            self._gpio.output(RINGER, GPIO.LOW)
            logger.debug("Ring off")

            # Schedule transition to on phase
            self._timer = threading.Timer(self._ring_off_duration, self._start_ring_cycle)
            self._timer.daemon = True
            self._timer.start()
