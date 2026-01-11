"""Hook switch monitor for detecting phone on-hook and off-hook states."""

import logging
import threading
from enum import Enum
from typing import Callable, Optional

from rotary_phone.hardware.gpio_abstraction import GPIO
from rotary_phone.hardware.pins import HOOK

logger = logging.getLogger(__name__)


class HookState(Enum):
    """Hook switch states."""

    ON_HOOK = "on_hook"  # Phone is hung up (idle)
    OFF_HOOK = "off_hook"  # Phone is picked up (in use)


class HookMonitor:
    """Monitors the hook switch and detects state changes with debouncing.

    The hook switch indicates whether the phone handset is on or off the cradle:
    - ON_HOOK (HIGH): Phone is hung up, idle
    - OFF_HOOK (LOW): Phone is picked up, ready for use

    Debouncing prevents spurious state changes from mechanical switch bounce.
    """

    def __init__(
        self,
        gpio: GPIO,
        debounce_time: float,
        on_off_hook: Optional[Callable[[], None]] = None,
        on_on_hook: Optional[Callable[[], None]] = None,
    ) -> None:
        """Initialize the hook monitor.

        Args:
            gpio: GPIO interface to use
            debounce_time: Seconds to wait for stable state before confirming change
            on_off_hook: Callback when phone goes off-hook (picked up)
            on_on_hook: Callback when phone goes on-hook (hung up)
        """
        self._gpio = gpio
        self._debounce_time = debounce_time
        self._on_off_hook = on_off_hook
        self._on_on_hook = on_on_hook

        self._state = HookState.ON_HOOK  # Assume phone starts on-hook
        self._debounce_timer: Optional[threading.Timer] = None
        self._pending_state: Optional[HookState] = None
        self._lock = threading.Lock()
        self._running = False

        logger.debug("HookMonitor initialized with debounce_time=%.3f", debounce_time)

    def start(self) -> None:
        """Start monitoring the hook switch."""
        if self._running:
            logger.warning("HookMonitor already running")
            return

        self._running = True

        # Set up hook pin with pull-up (HIGH = on-hook, LOW = off-hook)
        self._gpio.setup(HOOK, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Read initial state
        initial_pin_state = self._gpio.input(HOOK)
        self._state = HookState.ON_HOOK if initial_pin_state == GPIO.HIGH else HookState.OFF_HOOK
        logger.info("HookMonitor started, initial state: %s", self._state.value)

        # Set up edge detection for both edges
        self._gpio.add_event_detect(HOOK, GPIO.BOTH, callback=self._on_edge)

    def stop(self) -> None:
        """Stop monitoring the hook switch."""
        if not self._running:
            return

        self._running = False

        # Cancel any pending debounce timer
        with self._lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            self._pending_state = None

        # Remove event detection
        self._gpio.remove_event_detect(HOOK)

        logger.info("HookMonitor stopped")

    def get_state(self) -> HookState:
        """Get the current hook state.

        Returns:
            Current hook state (ON_HOOK or OFF_HOOK)
        """
        return self._state

    def _on_edge(self, _pin: int) -> None:
        """Handle edge detection on hook pin.

        Args:
            _pin: Pin number that triggered (should be HOOK)
        """
        if not self._running:
            return

        # Read current pin state
        pin_state = self._gpio.input(HOOK)
        new_state = HookState.ON_HOOK if pin_state == GPIO.HIGH else HookState.OFF_HOOK

        with self._lock:
            # Ignore if this is the same as current state
            if new_state == self._state:
                return

            # Cancel any existing debounce timer
            if self._debounce_timer:
                self._debounce_timer.cancel()

            # Start new debounce timer
            self._pending_state = new_state
            self._debounce_timer = threading.Timer(self._debounce_time, self._on_debounce_complete)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

            logger.debug(
                "Hook edge detected: %s -> %s (debouncing)",
                self._state.value,
                new_state.value,
            )

    def _on_debounce_complete(self) -> None:
        """Handle debounce timer completion - state change is confirmed."""
        with self._lock:
            if not self._running or self._pending_state is None:
                return

            new_state = self._pending_state
            old_state = self._state

            # Verify state is still what we expect (check pin again)
            pin_state = self._gpio.input(HOOK)
            current_state = HookState.ON_HOOK if pin_state == GPIO.HIGH else HookState.OFF_HOOK

            if current_state != new_state:
                # State changed during debounce, ignore
                logger.debug("Hook state changed during debounce, ignoring transition")
                self._pending_state = None
                self._debounce_timer = None
                return

            # Commit state change
            self._state = new_state
            self._pending_state = None
            self._debounce_timer = None

            logger.info("Hook state changed: %s -> %s", old_state.value, new_state.value)

        # Call callbacks outside of lock
        if new_state == HookState.OFF_HOOK and self._on_off_hook:
            self._on_off_hook()
        elif new_state == HookState.ON_HOOK and self._on_on_hook:
            self._on_on_hook()
