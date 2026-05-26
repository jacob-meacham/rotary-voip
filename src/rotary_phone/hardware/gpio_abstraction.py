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


class RealGPIO(GPIO):  # pylint: disable=too-many-instance-attributes
    """Real GPIO implementation using libgpiod for inputs and lgpio for outputs.

    Input edge detection goes through libgpiod (same library gpiomon uses), so
    edge counts match what gpiomon would show. lgpio is still used for output
    pin writes because nothing about it was broken there.
    """

    _CHIP_PATH = "/dev/gpiochip0"
    _CONSUMER = "rotary-phone"

    def __init__(self) -> None:
        """Initialize real GPIO."""
        try:
            # pylint: disable=import-outside-toplevel
            import lgpio  # type: ignore
            import gpiod  # type: ignore
            from gpiod.line import Bias, Direction, Edge as GEdge  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "lgpio and/or python3-libgpiod not available. "
                "Install via apt (python3-lgpio python3-libgpiod) or use mock GPIO mode."
            ) from e

        self._lgpio = lgpio
        self._gpiod = gpiod
        self._gpiod_direction = Direction
        self._gpiod_edge = GEdge
        self._gpiod_bias = Bias

        self._lgpio_handle = lgpio.gpiochip_open(0)
        # Per-input-pin state. Each pin has its own gpiod request so we can
        # re-request with edge detection when add_event_detect is called.
        self._input_requests: Dict[int, Any] = {}
        self._input_pulls: Dict[int, PullMode] = {}
        self._monitor_threads: Dict[int, threading.Thread] = {}
        self._monitor_stops: Dict[int, threading.Event] = {}
        self._pin_modes: Dict[int, PinMode] = {}
        logger.info("Real GPIO initialized (inputs: libgpiod, outputs: lgpio)")

    def setmode(self, mode: str) -> None:
        """Set the pin numbering mode (BCM only)."""
        if mode != "BCM":
            logger.warning("Only BCM mode supported, ignoring mode: %s", mode)

    def setup(self, pin: int, mode: PinMode, pull_up_down: PullMode = PullMode.OFF) -> None:
        """Set up a GPIO pin."""
        if mode == PinMode.IN:
            self._input_pulls[pin] = pull_up_down
            # Initial request: input only, no edge detection. add_event_detect
            # will release and re-request with edge detection.
            self._request_input(pin, edge=None)
        else:
            # gpio_claim_output's lFlags is *drive* flags, not bias/pull
            # flags — DRIVE_OPEN_DRAIN, DRIVE_OPEN_SOURCE, ACTIVE_LOW —
            # and the integer values overlap with SET_PULL_*. Passing 0
            # selects the default DRIVE_PUSH_PULL so HIGH actually drives
            # the pin instead of letting it float.
            self._lgpio.gpio_claim_output(self._lgpio_handle, pin, 0, 0)
            _ = pull_up_down  # not meaningful for outputs

        self._pin_modes[pin] = mode

    def _request_input(self, pin: int, edge: Optional[Edge]) -> None:
        """(Re)request an input line, optionally with edge detection."""
        # Stop any existing monitor thread for this pin
        if pin in self._monitor_threads:
            self._stop_monitor(pin)

        # Release existing request so we can re-request with new settings
        if pin in self._input_requests:
            self._input_requests[pin].release()
            del self._input_requests[pin]

        bias_map = {
            PullMode.OFF: self._gpiod_bias.AS_IS,
            PullMode.UP: self._gpiod_bias.PULL_UP,
            PullMode.DOWN: self._gpiod_bias.PULL_DOWN,
        }
        bias = bias_map.get(self._input_pulls.get(pin, PullMode.OFF), self._gpiod_bias.AS_IS)

        line_settings_kwargs: Dict[str, Any] = {
            "direction": self._gpiod_direction.INPUT,
            "bias": bias,
        }
        if edge is not None:
            edge_map = {
                Edge.RISING: self._gpiod_edge.RISING,
                Edge.FALLING: self._gpiod_edge.FALLING,
                Edge.BOTH: self._gpiod_edge.BOTH,
            }
            line_settings_kwargs["edge_detection"] = edge_map[edge]

        line_settings = self._gpiod.LineSettings(**line_settings_kwargs)
        request = self._gpiod.request_lines(
            self._CHIP_PATH,
            consumer=self._CONSUMER,
            config={pin: line_settings},
        )
        self._input_requests[pin] = request

    def input(self, pin: int) -> int:
        """Read the value of a GPIO pin."""
        if pin in self._input_requests:
            value = self._input_requests[pin].get_value(pin)
            # gpiod returns Value.ACTIVE / Value.INACTIVE. ACTIVE corresponds
            # to whatever active-high/low was configured (default active-high).
            return 1 if int(value) == 1 else 0
        # For an output pin that someone reads back, use lgpio.
        result: int = self._lgpio.gpio_read(self._lgpio_handle, pin)
        return result

    def output(self, pin: int, value: int) -> None:
        """Set the value of a GPIO pin."""
        self._lgpio.gpio_write(self._lgpio_handle, pin, value)

    def add_event_detect(
        self,
        pin: int,
        edge: Edge,
        callback: Optional[Callable[[int], None]] = None,
        bouncetime: int = 0,  # pylint: disable=unused-argument
    ) -> None:
        """Add edge detection to a pin via libgpiod."""
        # Re-request the line with edge detection enabled
        self._request_input(pin, edge=edge)

        if callback is None:
            return

        # Start a background thread that polls for edge events and dispatches.
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._monitor_loop,
            args=(pin, callback, stop_event),
            daemon=True,
            name=f"gpio-edge-{pin}",
        )
        self._monitor_stops[pin] = stop_event
        self._monitor_threads[pin] = thread
        thread.start()

    def _monitor_loop(
        self,
        pin: int,
        callback: Callable[[int], None],
        stop_event: threading.Event,
    ) -> None:
        """Background loop reading edge events for one input pin."""
        request = self._input_requests[pin]
        while not stop_event.is_set():
            try:
                # wait_edge_events returns True if events are available within
                # the timeout, False otherwise. The short timeout gives us a
                # chance to check stop_event periodically for clean shutdown.
                if request.wait_edge_events(timeout=0.1):
                    for _event in request.read_edge_events():
                        try:
                            callback(pin)
                        except Exception:  # pylint: disable=broad-except
                            logger.exception("Error in GPIO callback for pin %d", pin)
            except Exception:  # pylint: disable=broad-except
                logger.exception("Edge monitor loop error on pin %d, exiting", pin)
                return

    def _stop_monitor(self, pin: int) -> None:
        """Stop the monitor thread for a pin, if running."""
        if pin in self._monitor_stops:
            self._monitor_stops[pin].set()
        if pin in self._monitor_threads:
            self._monitor_threads[pin].join(timeout=1.0)
            del self._monitor_threads[pin]
        self._monitor_stops.pop(pin, None)

    def remove_event_detect(self, pin: int) -> None:
        """Remove edge detection from a pin."""
        self._stop_monitor(pin)
        # Re-request the line without edge detection so reads still work
        if pin in self._input_pulls:
            self._request_input(pin, edge=None)

    def cleanup(self, pin: Optional[int] = None) -> None:
        """Clean up GPIO resources."""
        if pin is None:
            for monitored_pin in list(self._monitor_threads.keys()):
                self._stop_monitor(monitored_pin)
            for request in self._input_requests.values():
                request.release()
            self._input_requests.clear()
            self._lgpio.gpiochip_close(self._lgpio_handle)
        else:
            self._stop_monitor(pin)
            if pin in self._input_requests:
                self._input_requests[pin].release()
                del self._input_requests[pin]
            self._input_pulls.pop(pin, None)
            self._pin_modes.pop(pin, None)

    def setwarnings(self, enable: bool) -> None:
        """Enable or disable warnings (no-op)."""
        _ = enable


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
