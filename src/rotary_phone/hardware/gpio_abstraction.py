"""GPIO abstraction layer supporting both real hardware and mocking."""

import logging
import threading
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any, Callable, Dict, Optional


logger = logging.getLogger(__name__)


class PinMode(IntEnum):
    """GPIO pin modes."""

    IN = 0
    OUT = 1


class PullMode(IntEnum):
    """GPIO pull-up/pull-down resistor modes."""

    OFF = 0
    DOWN = 1
    UP = 2


class Edge(IntEnum):
    """GPIO edge detection modes."""

    RISING = 1
    FALLING = 2
    BOTH = 3


class GPIO(ABC):
    """Abstract base class for GPIO operations."""

    # Constants for compatibility with RPi.GPIO
    BCM = "BCM"
    BOARD = "BOARD"
    IN = PinMode.IN
    OUT = PinMode.OUT
    PUD_OFF = PullMode.OFF
    PUD_DOWN = PullMode.DOWN
    PUD_UP = PullMode.UP
    RISING = Edge.RISING
    FALLING = Edge.FALLING
    BOTH = Edge.BOTH
    HIGH = 1
    LOW = 0

    @abstractmethod
    def setmode(self, mode: str) -> None:
        """Set the pin numbering mode (BCM or BOARD)."""

    @abstractmethod
    def setup(self, pin: int, mode: PinMode, pull_up_down: PullMode = PullMode.OFF) -> None:
        """Set up a GPIO pin as input or output."""

    @abstractmethod
    def input(self, pin: int) -> int:
        """Read the value of a GPIO pin."""

    @abstractmethod
    def output(self, pin: int, value: int) -> None:
        """Set the value of a GPIO pin."""

    @abstractmethod
    def add_event_detect(
        self,
        pin: int,
        edge: Edge,
        callback: Optional[Callable[[int], None]] = None,
        bouncetime: int = 0,
    ) -> None:
        """Add edge detection to a pin."""

    @abstractmethod
    def remove_event_detect(self, pin: int) -> None:
        """Remove edge detection from a pin."""

    @abstractmethod
    def cleanup(self, pin: Optional[int] = None) -> None:
        """Clean up GPIO resources."""

    @abstractmethod
    def setwarnings(self, enable: bool) -> None:
        """Enable or disable warnings."""


class MockGPIO(GPIO):  # pylint: disable=too-many-instance-attributes
    """Mock GPIO implementation for testing without hardware."""

    def __init__(self) -> None:
        """Initialize mock GPIO."""
        self._mode: Optional[str] = None
        self._pin_modes: Dict[int, PinMode] = {}
        self._pin_values: Dict[int, int] = {}
        self._pin_pulls: Dict[int, PullMode] = {}
        self._event_callbacks: Dict[int, Callable[[int], None]] = {}
        self._event_edges: Dict[int, Edge] = {}
        self._last_values: Dict[int, int] = {}
        self._warnings_enabled = True
        self._lock = threading.Lock()
        logger.info("MockGPIO initialized - no hardware required")

    def setmode(self, mode: str) -> None:
        """Set the pin numbering mode."""
        if mode not in (self.BCM, self.BOARD):
            raise ValueError(f"Invalid mode: {mode}")
        self._mode = mode
        logger.debug("GPIO mode set to: %s", mode)

    def setup(self, pin: int, mode: PinMode, pull_up_down: PullMode = PullMode.OFF) -> None:
        """Set up a GPIO pin."""
        with self._lock:
            self._pin_modes[pin] = mode
            self._pin_pulls[pin] = pull_up_down

            # Initialize pin value based on pull resistor, but only if not already set
            # This allows tests to set initial state before setup
            if mode == PinMode.IN and pin not in self._pin_values:
                if pull_up_down == PullMode.UP:
                    self._pin_values[pin] = self.HIGH
                elif pull_up_down == PullMode.DOWN:
                    self._pin_values[pin] = self.LOW
                else:
                    self._pin_values[pin] = self.LOW  # Default to LOW

            logger.debug(
                "Pin %d setup: mode=%s, pull=%s, value=%d",
                pin,
                mode.name,
                pull_up_down.name,
                self._pin_values.get(pin, 0),
            )

    def input(self, pin: int) -> int:
        """Read the value of a GPIO pin."""
        with self._lock:
            if pin not in self._pin_modes:
                raise RuntimeError(f"Pin {pin} not set up")
            if self._pin_modes[pin] != PinMode.IN:
                if self._warnings_enabled:
                    logger.warning("Reading from output pin %d", pin)
            return self._pin_values.get(pin, self.LOW)

    def output(self, pin: int, value: int) -> None:
        """Set the value of a GPIO pin."""
        with self._lock:
            if pin not in self._pin_modes:
                raise RuntimeError(f"Pin {pin} not set up")
            if self._pin_modes[pin] != PinMode.OUT:
                raise RuntimeError(f"Pin {pin} is not configured as output")

            old_value = self._pin_values.get(pin, self.LOW)
            self._pin_values[pin] = value

            logger.debug("Pin %d output: %d -> %d", pin, old_value, value)

    def add_event_detect(
        self,
        pin: int,
        edge: Edge,
        callback: Optional[Callable[[int], None]] = None,
        bouncetime: int = 0,
    ) -> None:
        """Add edge detection to a pin."""
        with self._lock:
            if pin not in self._pin_modes:
                raise RuntimeError(f"Pin {pin} not set up")
            if self._pin_modes[pin] != PinMode.IN:
                raise RuntimeError(f"Pin {pin} is not configured as input")

            self._event_edges[pin] = edge
            if callback:
                self._event_callbacks[pin] = callback
            self._last_values[pin] = self._pin_values.get(pin, self.LOW)

            logger.debug("Event detect added: pin=%d, edge=%s", pin, edge.name)

    def remove_event_detect(self, pin: int) -> None:
        """Remove edge detection from a pin."""
        with self._lock:
            if pin in self._event_edges:
                del self._event_edges[pin]
            if pin in self._event_callbacks:
                del self._event_callbacks[pin]
            if pin in self._last_values:
                del self._last_values[pin]

            logger.debug("Event detect removed from pin %d", pin)

    def cleanup(self, pin: Optional[int] = None) -> None:
        """Clean up GPIO resources."""
        with self._lock:
            if pin is None:
                # Clean up all pins
                self._pin_modes.clear()
                self._pin_values.clear()
                self._pin_pulls.clear()
                self._event_callbacks.clear()
                self._event_edges.clear()
                self._last_values.clear()
                logger.debug("All GPIO pins cleaned up")
            else:
                # Clean up specific pin
                self._pin_modes.pop(pin, None)
                self._pin_values.pop(pin, None)
                self._pin_pulls.pop(pin, None)
                self._event_callbacks.pop(pin, None)
                self._event_edges.pop(pin, None)
                self._last_values.pop(pin, None)
                logger.debug("Pin %d cleaned up", pin)

    def setwarnings(self, enable: bool) -> None:
        """Enable or disable warnings."""
        self._warnings_enabled = enable

    # Mock-specific methods for testing

    def set_input(self, pin: int, value: int) -> None:
        """Set an input pin value (for testing).

        This simulates external hardware changing the pin state.
        """
        with self._lock:
            if pin not in self._pin_modes:
                raise RuntimeError(f"Pin {pin} not set up")
            if self._pin_modes[pin] != PinMode.IN:
                raise RuntimeError(f"Pin {pin} is not configured as input")

            old_value = self._pin_values.get(pin, self.LOW)
            self._pin_values[pin] = value

            # Trigger edge detection callback if registered
            callback_to_call = None
            if pin in self._event_edges and pin in self._event_callbacks:
                last_value = self._last_values.get(pin, old_value)
                edge = self._event_edges[pin]

                # Check if edge matches
                trigger = False
                if edge == Edge.RISING and last_value == self.LOW and value == self.HIGH:
                    trigger = True
                elif edge == Edge.FALLING and last_value == self.HIGH and value == self.LOW:
                    trigger = True
                elif edge == Edge.BOTH and last_value != value:
                    trigger = True

                if trigger:
                    callback_to_call = self._event_callbacks[pin]

                self._last_values[pin] = value

        # Call callback outside of lock to avoid deadlock
        if callback_to_call is not None:
            callback_to_call(pin)

            logger.debug("Mock input: pin=%d, value=%d, triggered edge detect", pin, value)

    def get_pin_state(self, pin: int) -> Dict[str, Any]:
        """Get the current state of a pin (for testing)."""
        with self._lock:
            return {
                "mode": self._pin_modes.get(pin),
                "value": self._pin_values.get(pin),
                "pull": self._pin_pulls.get(pin),
                "has_event": pin in self._event_edges,
            }


class RealGPIO(GPIO):
    """Real GPIO implementation using lgpio."""

    def __init__(self) -> None:
        """Initialize real GPIO using lgpio."""
        try:
            import lgpio  # type: ignore  # pylint: disable=import-outside-toplevel

            self._lgpio = lgpio
            self._handle = lgpio.gpiochip_open(0)
            self._callbacks: Dict[int, Any] = {}
            self._pin_modes: Dict[int, PinMode] = {}
            logger.info("Real GPIO initialized using lgpio")
        except ImportError as e:
            raise RuntimeError("lgpio not available. Install it or use mock GPIO mode.") from e

    def setmode(self, mode: str) -> None:
        """Set the pin numbering mode (BCM only supported with lgpio)."""
        if mode != "BCM":
            logger.warning("lgpio only supports BCM mode, ignoring mode: %s", mode)

    def setup(self, pin: int, mode: PinMode, pull_up_down: PullMode = PullMode.OFF) -> None:
        """Set up a GPIO pin."""
        # Map pull mode to lgpio flags
        pull_flags = {
            PullMode.OFF: self._lgpio.SET_PULL_NONE,
            PullMode.UP: self._lgpio.SET_PULL_UP,
            PullMode.DOWN: self._lgpio.SET_PULL_DOWN,
        }
        flags = pull_flags.get(pull_up_down, self._lgpio.SET_PULL_NONE)

        if mode == PinMode.IN:
            self._lgpio.gpio_claim_input(self._handle, pin, flags)
        else:
            self._lgpio.gpio_claim_output(self._handle, pin, 0, flags)

        self._pin_modes[pin] = mode

    def input(self, pin: int) -> int:
        """Read the value of a GPIO pin."""
        result: int = self._lgpio.gpio_read(self._handle, pin)
        return result

    def output(self, pin: int, value: int) -> None:
        """Set the value of a GPIO pin."""
        self._lgpio.gpio_write(self._handle, pin, value)

    def add_event_detect(
        self,
        pin: int,
        edge: Edge,
        callback: Optional[Callable[[int], None]] = None,
        bouncetime: int = 0,
    ) -> None:
        """Add edge detection to a pin."""
        # Map edge to lgpio constant
        edge_map = {
            Edge.RISING: self._lgpio.RISING_EDGE,
            Edge.FALLING: self._lgpio.FALLING_EDGE,
            Edge.BOTH: self._lgpio.BOTH_EDGES,
        }
        lgpio_edge = edge_map[edge]

        if callback:
            # lgpio callback signature is (chip, gpio, level, timestamp)
            # Wrap to match RPi.GPIO signature (pin)
            def wrapped_callback(
                chip: int, gpio: int, level: int, timestamp: int  # pylint: disable=unused-argument
            ) -> None:
                callback(gpio)

            cb = self._lgpio.callback(self._handle, pin, lgpio_edge, wrapped_callback)
            self._callbacks[pin] = cb

    def remove_event_detect(self, pin: int) -> None:
        """Remove edge detection from a pin."""
        if pin in self._callbacks:
            self._callbacks[pin].cancel()
            del self._callbacks[pin]

    def cleanup(self, pin: Optional[int] = None) -> None:
        """Clean up GPIO resources."""
        if pin is None:
            # Cancel all callbacks and close handle
            for cb in self._callbacks.values():
                cb.cancel()
            self._callbacks.clear()
            self._lgpio.gpiochip_close(self._handle)
        else:
            # Free specific pin
            if pin in self._callbacks:
                self._callbacks[pin].cancel()
                del self._callbacks[pin]
            self._lgpio.gpio_free(self._handle, pin)
            self._pin_modes.pop(pin, None)

    def setwarnings(self, enable: bool) -> None:
        """Enable or disable warnings (no-op for lgpio)."""
        _ = enable  # lgpio doesn't have a warnings setting


def get_gpio(mock: bool) -> GPIO:
    """Get the appropriate GPIO implementation.

    Args:
        mock: If True, use mock GPIO. If False, use real GPIO.

    Returns:
        GPIO implementation (MockGPIO or RealGPIO)
    """
    if mock:
        return MockGPIO()
    return RealGPIO()
