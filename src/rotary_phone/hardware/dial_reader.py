"""Rotary dial pulse reader for detecting dialed digits.

Counts falling edges on DIAL_PULSE and emits a digit when no further
pulse has arrived within pulse_timeout seconds.

The dial's off-normal switch (DIAL_ACTIVE / GPIO22) is polled on each
pulse: if it currently reads HIGH (dial at rest), the pulse is treated
as spurious — phantom from the hook switch firing, EMI from elsewhere,
etc. — and dropped. This is robust against the fact that GPIO22 itself
chatters during the pulse train (because off-normal mirrors pulse on
this dial's internal wiring): a momentary HIGH between pulses doesn't
coincide with a pulse on GPIO27, so the polled value is reliably LOW
when a real pulse is happening.
"""

import logging
import threading
import time
from typing import Callable, Optional

from rotary_phone.hardware.gpio_abstraction import GPIO
from rotary_phone.hardware.pins import DIAL_ACTIVE, DIAL_PULSE

logger = logging.getLogger(__name__)

DEFAULT_PULSE_TIMEOUT = 0.25
DEFAULT_PULSE_DEBOUNCE = 0.008
# After a fresh "dial just started moving" event (DIAL_ACTIVE goes LOW
# following a long quiet period), pulses arriving in this window are
# dropped. Suppresses the contact-close transient that otherwise rides
# through right alongside the off-normal switch's first closure.
DEFAULT_PULSE_SETTLE = 0.05
# Quiet period before a DIAL_ACTIVE LOW edge counts as "fresh start"
# (filters mid-pulse-train chatter where off-normal mirrors the pulse).
DEFAULT_DIAL_QUIET_PERIOD = 0.30


class DialReader:  # pylint: disable=too-many-instance-attributes
    """Reads pulses from a rotary dial and detects dialed digits."""

    # pylint: disable-next=too-many-positional-arguments
    def __init__(
        self,
        gpio: GPIO,
        on_digit: Optional[Callable[[str], None]] = None,
        pulse_timeout: float = DEFAULT_PULSE_TIMEOUT,
        pulse_debounce: float = DEFAULT_PULSE_DEBOUNCE,
        pulse_settle: float = DEFAULT_PULSE_SETTLE,
        dial_quiet_period: float = DEFAULT_DIAL_QUIET_PERIOD,
    ) -> None:
        """Initialize the dial reader.

        Args:
            gpio: GPIO interface to use
            on_digit: Callback when a digit is detected (receives digit as string)
            pulse_timeout: Seconds to wait after last pulse before emitting digit
            pulse_debounce: Minimum seconds between accepted pulse edges
            pulse_settle: After a fresh DIAL_ACTIVE LOW edge (start of a new
                digit), pulses arriving within this window are ignored.
                Suppresses the off-normal contact-close transient.
            dial_quiet_period: A DIAL_ACTIVE LOW edge opens a fresh settle
                window only if the line has been quiet (no pulses, no
                accepted dial-active edges) for at least this long.
        """
        self._gpio = gpio
        self._on_digit = on_digit
        self._pulse_timeout = pulse_timeout
        self._pulse_debounce = pulse_debounce
        self._pulse_settle = pulse_settle
        self._dial_quiet_period = dial_quiet_period

        self._pulse_count = 0
        self._last_pulse_time = 0.0
        self._last_activity_time = 0.0
        self._settle_until = 0.0  # pulses before this monotonic ts are ignored
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._running = False

        logger.debug(
            "DialReader initialized: timeout=%.3f debounce=%.3f settle=%.3f quiet=%.3f",
            self._pulse_timeout,
            self._pulse_debounce,
            self._pulse_settle,
            self._dial_quiet_period,
        )

    def start(self) -> None:
        """Start monitoring for dial pulses."""
        if self._running:
            logger.warning("DialReader already running")
            return

        self._running = True
        self._pulse_count = 0
        self._last_pulse_time = 0.0
        self._last_activity_time = 0.0
        self._settle_until = 0.0

        self._gpio.setup(DIAL_PULSE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self._gpio.add_event_detect(DIAL_PULSE, GPIO.FALLING, callback=self._on_pulse)

        # Watch DIAL_ACTIVE FALLING edges to open the settle window at the
        # start of each new digit. We also poll its level in _on_pulse —
        # the edge subscription + the level poll together catch both the
        # dial-start race (settle window) and any noise pulses that fire
        # while the dial is at rest (level check).
        self._gpio.setup(DIAL_ACTIVE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self._gpio.add_event_detect(DIAL_ACTIVE, GPIO.FALLING, callback=self._on_dial_active_low)

        logger.info("DialReader started")

    def stop(self) -> None:
        """Stop monitoring for dial pulses."""
        if not self._running:
            return

        self._running = False
        self._gpio.remove_event_detect(DIAL_PULSE)
        self._gpio.remove_event_detect(DIAL_ACTIVE)

        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._pulse_count = 0
            self._last_pulse_time = 0.0
            self._last_activity_time = 0.0
            self._settle_until = 0.0

        logger.info("DialReader stopped")

    def set_on_digit_callback(self, on_digit: Optional[Callable[[str], None]]) -> None:
        """Set callback for when a digit is detected."""
        self._on_digit = on_digit

    def _on_dial_active_low(self, _pin: int) -> None:
        """DIAL_ACTIVE went LOW — may be the start of a new digit."""
        if not self._running:
            return

        now = time.monotonic()
        with self._lock:
            # Only treat this LOW as "fresh start" if the line has been
            # quiet. The off-normal switch chatters along with the pulse
            # contact during the release, so most LOW edges are mid-train
            # noise we should ignore.
            if (now - self._last_activity_time) >= self._dial_quiet_period:
                self._settle_until = now + self._pulse_settle
                logger.debug("Dial start detected — settle window open")
            self._last_activity_time = now

    def _on_pulse(self, _pin: int) -> None:
        """Handle a dial pulse (falling edge on DIAL_PULSE)."""
        if not self._running:
            return

        # Drop pulses while the dial is at rest. A spurious falling edge on
        # DIAL_PULSE while DIAL_ACTIVE reads HIGH is noise (hook switch
        # operation, EMI, etc.).
        if self._gpio.input(DIAL_ACTIVE) == GPIO.HIGH:
            logger.debug("Pulse ignored (dial at rest)")
            return

        now = time.monotonic()
        with self._lock:
            # Drop pulses inside the dial-start settle window. They're the
            # contact-close transient that fires alongside the off-normal
            # switch closing — not a real digit pulse.
            if now < self._settle_until:
                logger.debug("Pulse ignored (within settle window)")
                self._last_activity_time = now
                return

            if (now - self._last_pulse_time) < self._pulse_debounce:
                # Sub-debounce-window edge — contact bounce.
                return

            self._last_pulse_time = now
            self._last_activity_time = now
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
            self._settle_until = 0.0
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
