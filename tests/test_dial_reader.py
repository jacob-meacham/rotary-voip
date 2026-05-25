"""Tests for rotary dial reader component."""

import time
from typing import List

import pytest

from rotary_phone.hardware.dial_reader import DialReader
from rotary_phone.hardware.gpio_abstraction import MockGPIO
from tests.test_harness import simulate_dial_digit, simulate_dial_number

# Short pulse timeout so tests don't wait long.
TEST_PULSE_TIMEOUT = 0.1


@pytest.fixture
def collected_digits() -> List[str]:
    """Provide a list to collect detected digits."""
    return []


def _new_reader(gpio: MockGPIO, on_digit) -> DialReader:
    """Build a DialReader configured for fast test runs."""
    return DialReader(
        gpio=gpio,
        on_digit=on_digit,
        pulse_timeout=TEST_PULSE_TIMEOUT,
        pulse_debounce=0.005,
    )


def test_dial_reader_single_digit_1(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test digit 1 detection (1 pulse)."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    simulate_dial_digit(mock_gpio, "1")
    time.sleep(TEST_PULSE_TIMEOUT + 0.05)

    reader.stop()

    assert collected_digits == ["1"]


def test_dial_reader_single_digit_5(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test digit 5 detection (5 pulses)."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    simulate_dial_digit(mock_gpio, "5")
    time.sleep(TEST_PULSE_TIMEOUT + 0.05)

    reader.stop()

    assert collected_digits == ["5"]


def test_dial_reader_single_digit_0(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test digit 0 detection (10 pulses)."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    simulate_dial_digit(mock_gpio, "0")
    time.sleep(TEST_PULSE_TIMEOUT + 0.05)

    reader.stop()

    assert collected_digits == ["0"]


def test_dial_reader_phone_number(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test complete phone number dialing."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    simulate_dial_number(mock_gpio, "5551234", digit_gap=TEST_PULSE_TIMEOUT + 0.05)
    time.sleep(TEST_PULSE_TIMEOUT + 0.05)

    reader.stop()

    assert collected_digits == ["5", "5", "5", "1", "2", "3", "4"]


def test_dial_reader_rapid_pulses(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test rapid pulse handling (faster than normal)."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    simulate_dial_digit(mock_gpio, "3", pulse_gap=0.02)
    time.sleep(TEST_PULSE_TIMEOUT + 0.05)

    reader.stop()

    assert collected_digits == ["3"]


def test_dial_reader_slow_pulses(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test slow pulse handling (slower than normal — children dialing)."""
    reader = DialReader(
        gpio=mock_gpio,
        on_digit=lambda d: collected_digits.append(d),
        pulse_timeout=0.15,  # Longer timeout for slow pulses
        pulse_debounce=0.005,
    )
    reader.start()

    simulate_dial_digit(mock_gpio, "4", pulse_gap=0.1)
    time.sleep(0.2)

    reader.stop()

    assert collected_digits == ["4"]


def test_dial_reader_partial_dial_timeout(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Two pulses within one dial cycle emit digit '2' after the timeout fires."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    # Dial '2' (2 pulses in a single dial cycle). The inter-pulse timeout
    # fires after the cycle completes and emits the digit.
    simulate_dial_digit(mock_gpio, "2")
    time.sleep(TEST_PULSE_TIMEOUT + 0.05)

    reader.stop()

    assert collected_digits == ["2"]


def test_dial_reader_no_pulses(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test no detection when no pulses occur."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))
    reader.start()

    time.sleep(TEST_PULSE_TIMEOUT + 0.05)

    reader.stop()

    assert collected_digits == []


def test_dial_reader_start_stop_multiple_times(
    mock_gpio: MockGPIO, collected_digits: List[str]
) -> None:
    """Test multiple start/stop cycles."""
    reader = _new_reader(mock_gpio, on_digit=lambda d: collected_digits.append(d))

    reader.start()
    simulate_dial_digit(mock_gpio, "1")
    time.sleep(TEST_PULSE_TIMEOUT + 0.05)
    reader.stop()

    reader.start()
    simulate_dial_digit(mock_gpio, "2")
    time.sleep(TEST_PULSE_TIMEOUT + 0.05)
    reader.stop()

    assert collected_digits == ["1", "2"]
