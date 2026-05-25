"""Tests for rotary dial reader component."""

import time
from typing import List

import pytest

from rotary_phone.hardware.dial_reader import DialReader
from rotary_phone.hardware.gpio_abstraction import GPIO, MockGPIO
from rotary_phone.hardware.pins import DIAL_ACTIVE
from tests.test_harness import simulate_dial_digit, simulate_dial_number, simulate_pulse


@pytest.fixture
def collected_digits() -> List[str]:
    """Provide a list to collect detected digits."""
    return []


def _new_reader(gpio: MockGPIO, on_digit) -> DialReader:
    """Build a DialReader configured for fast test runs."""
    return DialReader(
        gpio=gpio,
        on_digit=on_digit,
        # Short settle so tests don't have to wait 150 ms per digit
        pulse_settle=0.02,
        pulse_debounce=0.005,
    )


def test_dial_reader_single_digit_1(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test digit 1 detection (1 pulse)."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    simulate_dial_digit(mock_gpio, "1")
    time.sleep(0.05)  # Let the DIAL_ACTIVE-rising callback fire

    reader.stop()

    assert collected_digits == ["1"]


def test_dial_reader_single_digit_5(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test digit 5 detection (5 pulses)."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    simulate_dial_digit(mock_gpio, "5")
    time.sleep(0.05)

    reader.stop()

    assert collected_digits == ["5"]


def test_dial_reader_single_digit_0(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test digit 0 detection (10 pulses)."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    simulate_dial_digit(mock_gpio, "0")
    time.sleep(0.05)

    reader.stop()

    assert collected_digits == ["0"]


def test_dial_reader_phone_number(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test complete phone number dialing."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    simulate_dial_number(mock_gpio, "5551234", digit_gap=0.1)
    time.sleep(0.05)

    reader.stop()

    assert collected_digits == ["5", "5", "5", "1", "2", "3", "4"]


def test_dial_reader_rapid_pulses(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test rapid pulse handling (faster than normal)."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    simulate_dial_digit(mock_gpio, "3", pulse_gap=0.02)
    time.sleep(0.05)

    reader.stop()

    assert collected_digits == ["3"]


def test_dial_reader_slow_pulses(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test slow pulse handling (slower than normal — children dialing)."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    simulate_dial_digit(mock_gpio, "4", pulse_gap=0.1)
    time.sleep(0.05)

    reader.stop()

    assert collected_digits == ["4"]


def test_pulse_before_dial_active_is_ignored(
    mock_gpio: MockGPIO, collected_digits: List[str]
) -> None:
    """Pulses with the dial at rest must not be counted (e.g., phantom noise)."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    # Send pulses without ever activating DIAL_ACTIVE — should never emit a digit.
    simulate_pulse(mock_gpio)
    time.sleep(0.05)
    simulate_pulse(mock_gpio)
    time.sleep(0.1)

    reader.stop()

    assert collected_digits == []


def test_pulses_inside_settle_window_are_ignored(
    mock_gpio: MockGPIO, collected_digits: List[str]
) -> None:
    """Pulses landing inside the settle window after DIAL_ACTIVE go uncounted.

    This is the phantom-pulse suppression: a contact-close glitch arrives
    immediately after the off-normal switch fires; we discard pulses within
    the settle window so it doesn't get counted as part of the digit.
    """
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    # Dial leaves rest
    mock_gpio.set_input(DIAL_ACTIVE, GPIO.LOW)
    # Immediate "phantom" pulse inside the settle window — should be ignored
    simulate_pulse(mock_gpio)
    # Wait past the settle window then send one real pulse
    time.sleep(0.04)
    simulate_pulse(mock_gpio)
    # Dial returns
    time.sleep(0.02)
    mock_gpio.set_input(DIAL_ACTIVE, GPIO.HIGH)
    time.sleep(0.05)

    reader.stop()

    # Only the real pulse (after settle) was counted → digit "1"
    assert collected_digits == ["1"]


def test_dial_reader_no_pulses(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """No DIAL_ACTIVE transition → no digit emitted."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    time.sleep(0.1)

    reader.stop()

    assert collected_digits == []


def test_dial_active_with_no_pulses_emits_nothing(
    mock_gpio: MockGPIO, collected_digits: List[str]
) -> None:
    """DIAL_ACTIVE cycling LOW→HIGH with zero pulses must not emit a digit."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    mock_gpio.set_input(DIAL_ACTIVE, GPIO.LOW)
    time.sleep(0.05)
    mock_gpio.set_input(DIAL_ACTIVE, GPIO.HIGH)
    time.sleep(0.05)

    reader.stop()

    assert collected_digits == []


def test_dial_reader_start_stop_multiple_times(
    mock_gpio: MockGPIO, collected_digits: List[str]
) -> None:
    """Test multiple start/stop cycles."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))

    reader.start()
    simulate_dial_digit(mock_gpio, "1")
    time.sleep(0.05)
    reader.stop()

    reader.start()
    simulate_dial_digit(mock_gpio, "2")
    time.sleep(0.05)
    reader.stop()

    assert collected_digits == ["1", "2"]
