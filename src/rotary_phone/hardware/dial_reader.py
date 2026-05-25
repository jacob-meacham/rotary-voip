"""Rotary dial pulse reader for detecting dialed digits.

Counts falling edges on DIAL_PULSE and emits a digit when no further
pulse has arrived within pulse_timeout seconds. The hardware-side cap
on the DIAL_PULSE line (see HARDWARE.md) takes care of fast bounce
edges and the contact-close glitch the off-normal switch otherwise
created on the pulse line; software-side debounce is a small extra
filter.

The dial's off-normal switch (DIAL_ACTIVE / GPIO22) is not used here —
on this dial the off-normal contact briefly breaks during each pulse
cycle, so it doesn't behave as a clean "dial is active" gate. It's
left wired (the pin claim is harmless) but DialReader doesn't watch it.
"""

import logging
import threading
import time
from typing import Callable, Optional

from rotary_phone.hardware.gpio_abstraction import GPIO
from rotary_phone.hardware.pins import DIAL_PULSE

logger = logging.getLogger(__name__)

# Seconds to wait after the last pulse before considering the digit complete.
DEFAULT_PULSE_TIMEOUT = 0.25
# Minimum gap between accepted pulse edges. Real pulses are ~100 ms apart,
# bounce is typically <5 ms — anything tighter than this is contact bounce.
DEFAULT_PULSE_DEBOUNCE = 0.008


class DialReader:
    """Reads pulses from a rotary dial and detects dialed digits.

    A pulse cycle on DIAL_PULSE = one digit's worth of pulses (1-9 for
    digits 1-9, 10 for 0). After pulse_timeout of silence, the count
    is converted to a digit and emitted via the on_digit callback.
    """

    def __init__(
        self,
        gpio: GPIO,
        on_digit: Optional[Callable[[str], None]] = None,
        pulse_timeout: float = DEFAULT_PULSE_TIMEOUT,
        pulse_debounce: float = DEFAULT_PULSE_DEBOUNCE,
    ) -> None:
        """Initialize the dial reader.

        Args:
            gpio: GPIO interface to use
            on_digit: Callback when a digit is detected (receives digit as string)
            pulse_timeout: Seconds to wait after last pulse before emitting digit
            pulse_debounce: Minimum seconds between accepted pulse edges
        """
        self._gpio = gpio
        self._on_digit = on_digit
        self._pulse_timeout = pulse_timeout
        self._pulse_debounce = pulse_debounce

        self._pulse_count = 0
        self._last_pulse_time = 0.0
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._running = False

        logger.debug(
            "DialReader initialized with pulse_timeout=%.3f, pulse_debounce=%.3f",
            self._pulse_timeout,
            self._pulse_debounce,
        )

    def start(self) -> None:
        """Start monitoring for dial pulses."""
        if self._running:
            logger.warning("DialReader already running")
            return

        self._running = True
        self._pulse_count = 0
        self._last_pulse_time = 0.0

        self._gpio.setup(DIAL_PULSE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self._gpio.add_event_detect(DIAL_PULSE, GPIO.FALLING, callback=self._on_pulse)

        logger.info("DialReader started")

    def stop(self) -> None:
        """Stop monitoring for dial pulses."""
        if not self._running:
            return

        self._running = False
        self._gpio.remove_event_detect(DIAL_PULSE)

        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._pulse_count = 0
            self._last_pulse_time = 0.0

        logger.info("DialReader stopped")

    def set_on_digit_callback(self, on_digit: Optional[Callable[[str], None]]) -> None:
        """Set callback for when a digit is detected."""
        self._on_digit = on_digit

    def _on_pulse(self, _pin: int) -> None:
        """Handle a dial pulse (falling edge on DIAL_PULSE)."""
        if not self._running:
            return

        now = time.monotonic()
        with self._lock:
            if (now - self._last_pulse_time) < self._pulse_debounce:
                # Sub-debounce-window edge — contact bounce.
                return

            self._last_pulse_time = now
            self._pulse_count += 1
            logger.debug("Pulse detected, count=%d", self._pulse_count)

            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self._pulse_timeout, self._emit_digit)
            self._timer.daemon = True
            self._timer.start()

    def _emit_digit(self) -> None:
        """Inter-pulse timer fired — digit is complete."""
        with self._lock:
            count = self._pulse_count
            self._pulse_count = 0
            self._last_pulse_time = 0.0
            self._timer = None
            digit = self._count_to_digit(count)

        if digit is not None and self._on_digit is not None:
            self._on_digit(digit)

    @staticmethod
    def _count_to_digit(count: int) -> Optional[str]:
        """Map a pulse count to a dialed digit, or None if invalid."""
        if count == 0:
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
