"""Rotary dial pulse reader for detecting dialed digits."""

import logging
import threading
from typing import Callable, Optional

from rotary_phone.hardware.gpio_abstraction import GPIO
from rotary_phone.hardware.pins import DIAL_PULSE

logger = logging.getLogger(__name__)

# Seconds to wait after last pulse before emitting the digit
PULSE_TIMEOUT = 0.15


class DialReader:
    """Reads pulses from rotary dial and detects dialed digits.

    The rotary dial generates pulses as it returns to rest position:
    - 1 pulse = digit 1
    - 2 pulses = digit 2
    - ...
    - 9 pulses = digit 9
    - 10 pulses = digit 0

    Pulses are detected on falling edges of the DIAL_PULSE pin.
    A timeout determines when a digit is complete.
    """

    def __init__(
        self,
        gpio: GPIO,
        on_digit: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize the dial reader.

        Args:
            gpio: GPIO interface to use
            on_digit: Callback when a digit is detected (receives digit as string)
        """
        self._gpio = gpio
        self._on_digit = on_digit

        self._pulse_count = 0
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._running = False

        logger.debug("DialReader initialized with pulse_timeout=%.3f", PULSE_TIMEOUT)

    def start(self) -> None:
        """Start monitoring for dial pulses."""
        if self._running:
            logger.warning("DialReader already running")
            return

        self._running = True
        self._pulse_count = 0

        # Set up edge detection on dial pulse pin
        self._gpio.setup(DIAL_PULSE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self._gpio.add_event_detect(DIAL_PULSE, GPIO.FALLING, callback=self._on_pulse)

        logger.info("DialReader started")

    def stop(self) -> None:
        """Stop monitoring for dial pulses."""
        if not self._running:
            return

        self._running = False

        # Cancel any pending timer
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None

        # Remove event detection
        self._gpio.remove_event_detect(DIAL_PULSE)

        logger.info("DialReader stopped")

    def set_on_digit_callback(self, on_digit: Optional[Callable[[str], None]]) -> None:
        """Set callback for when a digit is detected.

        Args:
            on_digit: Callback that receives the detected digit as a string
        """
        self._on_digit = on_digit

    def _on_pulse(self, _pin: int) -> None:
        """Handle a dial pulse (falling edge).

        Args:
            _pin: Pin number that triggered (should be DIAL_PULSE)
        """
        if not self._running:
            return

        with self._lock:
            # Increment pulse count
            self._pulse_count += 1
            logger.debug("Pulse detected, count=%d", self._pulse_count)

            # Cancel existing timer if any
            if self._timer:
                self._timer.cancel()

            # Start new timer to detect end of pulse sequence
            self._timer = threading.Timer(PULSE_TIMEOUT, self._on_timeout)
            self._timer.daemon = True
            self._timer.start()

    def _on_timeout(self) -> None:
        """Handle timeout - pulse sequence is complete, emit digit."""
        with self._lock:
            if self._pulse_count == 0:
                # Spurious timeout, ignore
                return

            # Convert pulse count to digit (10 pulses = 0)
            if self._pulse_count == 10:
                digit = "0"
            elif 1 <= self._pulse_count <= 9:
                digit = str(self._pulse_count)
            else:
                logger.warning("Invalid pulse count: %d, ignoring", self._pulse_count)
                self._pulse_count = 0
                self._timer = None
                return

            logger.info("Digit detected: %s (%d pulses)", digit, self._pulse_count)

            # Reset for next digit
            self._pulse_count = 0
            self._timer = None

        # Call callback outside of lock to avoid potential deadlock
        if self._on_digit:
            self._on_digit(digit)
