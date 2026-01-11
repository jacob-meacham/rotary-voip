"""GPIO abstraction layer supporting both real hardware and mocking."""

import logging
import os
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
        pass

    @abstractmethod
    def setup(self, pin: int, mode: PinMode, pull_up_down: PullMode = PullMode.OFF) -> None:
        """Set up a GPIO pin as input or output."""
        pass

    @abstractmethod
    def input(self, pin: int) -> int:
        """Read the value of a GPIO pin."""
        pass

    @abstractmethod
    def output(self, pin: int, value: int) -> None:
        """Set the value of a GPIO pin."""
        pass

    @abstractmethod
    def add_event_detect(
        self,
        pin: int,
        edge: Edge,
        callback: Optional[Callable[[int], None]] = None,
        bouncetime: int = 0,
    ) -> None:
        """Add edge detection to a pin."""
        pass

    @abstractmethod
    def remove_event_detect(self, pin: int) -> None:
        """Remove edge detection from a pin."""
        pass

    @abstractmethod
    def cleanup(self, pin: Optional[int] = None) -> None:
        """Clean up GPIO resources."""
        pass

    @abstractmethod
    def setwarnings(self, enable: bool) -> None:
        """Enable or disable warnings."""
        pass


class MockGPIO(GPIO):
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
        logger.debug(f"GPIO mode set to: {mode}")

    def setup(self, pin: int, mode: PinMode, pull_up_down: PullMode = PullMode.OFF) -> None:
        """Set up a GPIO pin."""
        with self._lock:
            self._pin_modes[pin] = mode
            self._pin_pulls[pin] = pull_up_down

            # Initialize pin value based on pull resistor
            if mode == PinMode.IN:
                if pull_up_down == PullMode.UP:
                    self._pin_values[pin] = self.HIGH
                elif pull_up_down == PullMode.DOWN:
                    self._pin_values[pin] = self.LOW
                else:
                    self._pin_values[pin] = self.LOW  # Default to LOW

            logger.debug(
                f"Pin {pin} setup: mode={mode.name}, pull={pull_up_down.name}, "
                f"value={self._pin_values.get(pin, 0)}"
            )

    def input(self, pin: int) -> int:
        """Read the value of a GPIO pin."""
        with self._lock:
            if pin not in self._pin_modes:
                raise RuntimeError(f"Pin {pin} not set up")
            if self._pin_modes[pin] != PinMode.IN:
                if self._warnings_enabled:
                    logger.warning(f"Reading from output pin {pin}")
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

            logger.debug(f"Pin {pin} output: {old_value} -> {value}")

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

            logger.debug(f"Event detect added: pin={pin}, edge={edge.name}")

    def remove_event_detect(self, pin: int) -> None:
        """Remove edge detection from a pin."""
        with self._lock:
            if pin in self._event_edges:
                del self._event_edges[pin]
            if pin in self._event_callbacks:
                del self._event_callbacks[pin]
            if pin in self._last_values:
                del self._last_values[pin]

            logger.debug(f"Event detect removed from pin {pin}")

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
                logger.debug(f"Pin {pin} cleaned up")

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
                    callback = self._event_callbacks[pin]
                    # Call callback outside of lock to avoid deadlock
                    threading.Thread(target=callback, args=(pin,), daemon=True).start()

                self._last_values[pin] = value

            logger.debug(f"Mock input: pin={pin}, value={value}, triggered edge detect")

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
    """Real GPIO implementation using RPi.GPIO."""

    def __init__(self) -> None:
        """Initialize real GPIO using RPi.GPIO."""
        try:
            import RPi.GPIO as gpio  # type: ignore

            self._gpio = gpio
            logger.info("Real GPIO initialized using RPi.GPIO")
        except ImportError:
            raise RuntimeError("RPi.GPIO not available. Install it or use mock GPIO mode.")

    def setmode(self, mode: str) -> None:
        """Set the pin numbering mode."""
        self._gpio.setmode(getattr(self._gpio, mode))

    def setup(self, pin: int, mode: PinMode, pull_up_down: PullMode = PullMode.OFF) -> None:
        """Set up a GPIO pin."""
        gpio_mode = self._gpio.IN if mode == PinMode.IN else self._gpio.OUT
        gpio_pull = getattr(self._gpio, f"PUD_{pull_up_down.name}")
        self._gpio.setup(pin, gpio_mode, pull_up_down=gpio_pull)

    def input(self, pin: int) -> int:
        """Read the value of a GPIO pin."""
        return self._gpio.input(pin)

    def output(self, pin: int, value: int) -> None:
        """Set the value of a GPIO pin."""
        self._gpio.output(pin, value)

    def add_event_detect(
        self,
        pin: int,
        edge: Edge,
        callback: Optional[Callable[[int], None]] = None,
        bouncetime: int = 0,
    ) -> None:
        """Add edge detection to a pin."""
        gpio_edge = getattr(self._gpio, edge.name)
        self._gpio.add_event_detect(pin, gpio_edge, callback=callback, bouncetime=bouncetime)

    def remove_event_detect(self, pin: int) -> None:
        """Remove edge detection from a pin."""
        self._gpio.remove_event_detect(pin)

    def cleanup(self, pin: Optional[int] = None) -> None:
        """Clean up GPIO resources."""
        if pin is None:
            self._gpio.cleanup()
        else:
            self._gpio.cleanup(pin)

    def setwarnings(self, enable: bool) -> None:
        """Enable or disable warnings."""
        self._gpio.setwarnings(enable)


def get_gpio(mock: Optional[bool] = None) -> GPIO:
    """Get the appropriate GPIO implementation.

    Args:
        mock: If True, force mock GPIO. If False, force real GPIO.
              If None, auto-detect based on environment and platform.

    Returns:
        GPIO implementation (MockGPIO or RealGPIO)
    """
    if mock is None:
        # Auto-detect: check environment variable first
        if os.getenv("MOCK_GPIO", "").lower() in ("1", "true", "yes"):
            mock = True
        else:
            # Try to import RPi.GPIO - if it fails, use mock
            try:
                import RPi.GPIO  # type: ignore  # noqa: F401

                mock = False
                logger.info("Auto-detected: Using real GPIO (RPi.GPIO available)")
            except ImportError:
                mock = True
                logger.info("Auto-detected: Using mock GPIO (RPi.GPIO not available)")

    if mock:
        return MockGPIO()
    else:
        return RealGPIO()
