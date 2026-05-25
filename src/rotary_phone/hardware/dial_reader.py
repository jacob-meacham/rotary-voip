"""Rotary dial pulse reader for detecting dialed digits.

Uses the dial's off-normal switch (DIAL_ACTIVE) as the gate that
delimits one digit:

  - DIAL_ACTIVE going LOW  = dial has been moved off its rest position
                             (the user is starting to dial a digit)
  - DIAL_ACTIVE going HIGH = dial has fully returned to rest
                             (the digit is complete; emit it)

Pulses on DIAL_PULSE that arrive when DIAL_ACTIVE is high (dial at rest)
or within the brief settle window after DIAL_ACTIVE goes low are ignored
— those are the contact-close glitches we'd otherwise miscount as a
phantom pulse on slow dials.

Wiring assumptions (see HARDWARE.md):
  - DIAL_PULSE input reads HIGH at rest, pulses LOW with each
    pulse-contact closure during dial release.
  - DIAL_ACTIVE input reads HIGH at rest and stays LOW for the entire
    time the dial is moved off rest (both pull and release).
"""

import logging
import threading
import time
from typing import Callable, Optional

from rotary_phone.hardware.gpio_abstraction import GPIO
from rotary_phone.hardware.pins import DIAL_ACTIVE, DIAL_PULSE

logger = logging.getLogger(__name__)

DEFAULT_PULSE_DEBOUNCE = 0.008
DEFAULT_PULSE_SETTLE = 0.15


class DialReader:
    """Reads pulses from a rotary dial and detects dialed digits."""

    # pylint: disable-next=too-many-positional-arguments
    def __init__(
        self,
        gpio: GPIO,
        on_digit: Optional[Callable[[str], None]] = None,
        pulse_debounce: float = DEFAULT_PULSE_DEBOUNCE,
        pulse_settle: float = DEFAULT_PULSE_SETTLE,
    ) -> None:
        """Initialize the dial reader.

        Args:
            gpio: GPIO interface to use
            on_digit: Callback when a digit is detected (receives digit as string)
            pulse_debounce: Minimum seconds between accepted pulse edges. Edges
                arriving closer than this are treated as contact bounce.
            pulse_settle: Pulses are ignored for this many seconds after the
                dial leaves rest. Suppresses the contact-close glitch on the
                dial-active switch that otherwise looks like a phantom pulse.
        """
        self._gpio = gpio
        self._on_digit = on_digit
        self._pulse_debounce = pulse_debounce
        self._pulse_settle = pulse_settle

        self._dial_active = False
        self._dial_active_at = 0.0
        self._pulse_count = 0
        self._last_pulse_time = 0.0
        self._lock = threading.Lock()
        self._running = False

        logger.debug(
            "DialReader initialized with pulse_debounce=%.3f, pulse_settle=%.3f",
            self._pulse_debounce,
            self._pulse_settle,
        )

    def start(self) -> None:
        """Start monitoring for dial pulses and dial activity."""
        if self._running:
            logger.warning("DialReader already running")
            return

        self._running = True
        self._reset_state()

        self._gpio.setup(DIAL_PULSE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self._gpio.add_event_detect(DIAL_PULSE, GPIO.FALLING, callback=self._on_pulse)

        self._gpio.setup(DIAL_ACTIVE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self._gpio.add_event_detect(DIAL_ACTIVE, GPIO.BOTH, callback=self._on_active_change)

        logger.info("DialReader started")

    def stop(self) -> None:
        """Stop monitoring for dial pulses."""
        if not self._running:
            return

        self._running = False
        self._gpio.remove_event_detect(DIAL_PULSE)
        self._gpio.remove_event_detect(DIAL_ACTIVE)

        with self._lock:
            self._reset_state()

        logger.info("DialReader stopped")

    def set_on_digit_callback(self, on_digit: Optional[Callable[[str], None]]) -> None:
        """Set callback for when a digit is detected."""
        self._on_digit = on_digit

    def _reset_state(self) -> None:
        """Reset per-digit tracking. Caller must hold _lock (or be in start/stop)."""
        self._dial_active = False
        self._dial_active_at = 0.0
        self._pulse_count = 0
        self._last_pulse_time = 0.0

    def _on_active_change(self, _pin: int) -> None:
        """DIAL_ACTIVE edge — dial entered or left the rest position."""
        if not self._running:
            return

        level = self._gpio.input(DIAL_ACTIVE)
        now = time.monotonic()

        digit_to_emit: Optional[str] = None
        with self._lock:
            if level == GPIO.LOW:
                # Dial left rest — start of a new digit.
                self._dial_active = True
                self._dial_active_at = now
                self._pulse_count = 0
                self._last_pulse_time = 0.0
                logger.debug("Dial active (off rest); awaiting pulses")
            else:
                # Dial returned to rest — emit whatever we counted.
                count = self._pulse_count
                was_active = self._dial_active
                self._reset_state()
                if not was_active:
                    logger.debug("DIAL_ACTIVE went HIGH without prior LOW; ignoring")
                else:
                    digit_to_emit = self._count_to_digit(count)

        if digit_to_emit is not None and self._on_digit is not None:
            self._on_digit(digit_to_emit)

    def _on_pulse(self, _pin: int) -> None:
        """Handle a dial pulse (falling edge on DIAL_PULSE)."""
        if not self._running:
            return

        now = time.monotonic()
        with self._lock:
            if not self._dial_active:
                logger.debug("Pulse ignored (dial not active)")
                return

            if (now - self._dial_active_at) < self._pulse_settle:
                logger.debug("Pulse ignored (within settle window)")
                return

            if (now - self._last_pulse_time) < self._pulse_debounce:
                return

            self._last_pulse_time = now
            self._pulse_count += 1
            logger.debug("Pulse detected, count=%d", self._pulse_count)

    @staticmethod
    def _count_to_digit(count: int) -> Optional[str]:
        """Map a pulse count to a dialed digit, or None if invalid."""
        if count == 0:
            logger.debug("Dial returned to rest with no pulses; not emitting")
            return None
        if count == 10:
            digit = "0"
        elif 1 <= count <= 9:
            digit = str(count)
        else:
            logger.warning("Invalid pulse count: %d, ignoring", count)
            return None
        logger.info("Digit detected: %s (%d pulses)", digit, count)
        return digit
