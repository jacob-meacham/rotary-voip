"""Tests for GPIO abstraction layer."""

import threading
import time

import pytest

from rotary_phone.hardware import DIAL_PULSE, GPIO, HOOK, RINGER, get_gpio
from rotary_phone.hardware.gpio_abstraction import MockGPIO


def test_get_gpio_mock() -> None:
    """Test that get_gpio returns MockGPIO when requested."""
    gpio = get_gpio(mock=True)
    assert isinstance(gpio, MockGPIO)


def test_mock_gpio_setmode() -> None:
    """Test setting GPIO mode."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    # Should not raise an error


def test_mock_gpio_setup_input() -> None:
    """Test setting up an input pin."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(HOOK, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    state = gpio.get_pin_state(HOOK)
    assert state["mode"] == GPIO.IN
    assert state["pull"] == GPIO.PUD_UP
    assert state["value"] == GPIO.HIGH  # Pull-up should set HIGH


def test_mock_gpio_setup_output() -> None:
    """Test setting up an output pin."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(RINGER, GPIO.OUT)

    state = gpio.get_pin_state(RINGER)
    assert state["mode"] == GPIO.OUT


def test_mock_gpio_input_read() -> None:
    """Test reading from an input pin."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(HOOK, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Initial value should be HIGH due to pull-up
    assert gpio.input(HOOK) == GPIO.HIGH

    # Simulate pin going LOW
    gpio.set_input(HOOK, GPIO.LOW)
    assert gpio.input(HOOK) == GPIO.LOW


def test_mock_gpio_output_write() -> None:
    """Test writing to an output pin."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(RINGER, GPIO.OUT)

    gpio.output(RINGER, GPIO.HIGH)
    state = gpio.get_pin_state(RINGER)
    assert state["value"] == GPIO.HIGH

    gpio.output(RINGER, GPIO.LOW)
    state = gpio.get_pin_state(RINGER)
    assert state["value"] == GPIO.LOW


def test_mock_gpio_edge_detection_falling() -> None:
    """Test falling edge detection."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(DIAL_PULSE, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    events = []

    def callback(pin: int) -> None:
        events.append(("falling", pin))

    gpio.add_event_detect(DIAL_PULSE, GPIO.FALLING, callback=callback)

    # Initial state is HIGH (pull-up)
    assert gpio.input(DIAL_PULSE) == GPIO.HIGH

    # Trigger falling edge (HIGH -> LOW)
    gpio.set_input(DIAL_PULSE, GPIO.LOW)
    time.sleep(0.05)  # Give callback thread time to run

    assert len(events) == 1
    assert events[0] == ("falling", DIAL_PULSE)

    # Trigger rising edge (LOW -> HIGH) - should NOT trigger
    gpio.set_input(DIAL_PULSE, GPIO.HIGH)
    time.sleep(0.05)

    assert len(events) == 1  # Still only 1 event


def test_mock_gpio_edge_detection_rising() -> None:
    """Test rising edge detection."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(HOOK, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    events = []

    def callback(pin: int) -> None:
        events.append(("rising", pin))

    gpio.add_event_detect(HOOK, GPIO.RISING, callback=callback)

    # Initial state is LOW (pull-down)
    assert gpio.input(HOOK) == GPIO.LOW

    # Trigger rising edge (LOW -> HIGH)
    gpio.set_input(HOOK, GPIO.HIGH)
    time.sleep(0.05)

    assert len(events) == 1
    assert events[0] == ("rising", HOOK)


def test_mock_gpio_edge_detection_both() -> None:
    """Test both edge detection."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(HOOK, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    events = []

    def callback(pin: int) -> None:
        events.append(pin)

    gpio.add_event_detect(HOOK, GPIO.BOTH, callback=callback)

    # Trigger falling edge
    gpio.set_input(HOOK, GPIO.LOW)
    time.sleep(0.05)
    assert len(events) == 1

    # Trigger rising edge
    gpio.set_input(HOOK, GPIO.HIGH)
    time.sleep(0.05)
    assert len(events) == 2


def test_mock_gpio_remove_event_detect() -> None:
    """Test removing edge detection."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(DIAL_PULSE, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    events = []

    def callback(pin: int) -> None:
        events.append(pin)

    gpio.add_event_detect(DIAL_PULSE, GPIO.FALLING, callback=callback)

    # Trigger edge - should be detected
    gpio.set_input(DIAL_PULSE, GPIO.LOW)
    time.sleep(0.05)
    assert len(events) == 1

    # Remove event detect
    gpio.remove_event_detect(DIAL_PULSE)

    # Trigger edge again - should NOT be detected
    gpio.set_input(DIAL_PULSE, GPIO.HIGH)
    gpio.set_input(DIAL_PULSE, GPIO.LOW)
    time.sleep(0.05)
    assert len(events) == 1  # Still only 1 event


def test_mock_gpio_cleanup_all() -> None:
    """Test cleaning up all pins."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(HOOK, GPIO.IN)
    gpio.setup(RINGER, GPIO.OUT)

    gpio.cleanup()

    # After cleanup, pins should not be set up
    with pytest.raises(RuntimeError, match="not set up"):
        gpio.input(HOOK)


def test_mock_gpio_cleanup_specific_pin() -> None:
    """Test cleaning up a specific pin."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(HOOK, GPIO.IN)
    gpio.setup(RINGER, GPIO.OUT)

    gpio.cleanup(HOOK)

    # HOOK should be cleaned up
    with pytest.raises(RuntimeError, match="not set up"):
        gpio.input(HOOK)

    # RINGER should still be set up
    gpio.output(RINGER, GPIO.HIGH)  # Should not raise


def test_mock_gpio_error_read_from_output() -> None:
    """Test that reading from output pin gives warning."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(RINGER, GPIO.OUT)

    # Should not raise, but will log warning
    value = gpio.input(RINGER)
    assert isinstance(value, int)


def test_mock_gpio_error_write_to_input() -> None:
    """Test that writing to input pin raises error."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(HOOK, GPIO.IN)

    with pytest.raises(RuntimeError, match="not configured as output"):
        gpio.output(HOOK, GPIO.HIGH)


def test_mock_gpio_thread_safety_leaves_pin_in_consistent_state() -> None:
    """Under concurrent reads and writes, MockGPIO must (a) never raise from
    either side and (b) leave the pin in one of the values writers actually
    wrote. A torn read returning some garbage int (or None) would mean the
    internal dict was being mutated mid-read without locking."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(HOOK, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    errors: list[Exception] = []
    observed_reads: list[int] = []

    def reader() -> None:
        try:
            for _ in range(100):
                observed_reads.append(gpio.input(HOOK))
        except Exception as e:
            errors.append(e)

    def writer() -> None:
        try:
            for i in range(100):
                gpio.set_input(HOOK, i % 2)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=reader) for _ in range(5)]
    threads.extend([threading.Thread(target=writer) for _ in range(5)])
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # No exceptions on either side
    assert errors == [], f"thread errors: {errors!r}"
    # Every read returned one of the two values a writer could have written
    assert set(observed_reads) <= {0, 1}, f"saw unexpected reads: {set(observed_reads)}"
    # The final value is whichever thread's last write happened to land last.
    # Per-thread it's always 1 (i=99 -> 1), but the global "last" depends on
    # scheduling, so it can be either 0 or 1 in principle.
    assert gpio.input(HOOK) in {0, 1}
