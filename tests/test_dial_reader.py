"""Tests for rotary dial reader component."""

import time
from typing import List

import pytest

from rotary_phone.hardware.dial_reader import DialReader
from rotary_phone.hardware.gpio_abstraction import MockGPIO
from tests.test_harness import simulate_dial_digit, simulate_dial_number, simulate_pulse


@pytest.fixture
def collected_digits() -> List[str]:
    """Provide a list to collect detected digits."""
    return []


# Tests


def test_dial_reader_single_digit_1(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test digit 1 detection (1 pulse)."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.1,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    simulate_dial_digit(mock_gpio, "1")
    time.sleep(0.15)  # Wait for timeout

    reader.stop()

    assert collected_digits == ["1"]


def test_dial_reader_single_digit_5(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test digit 5 detection (5 pulses)."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.1,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    simulate_dial_digit(mock_gpio, "5")
    time.sleep(0.15)  # Wait for timeout

    reader.stop()

    assert collected_digits == ["5"]


def test_dial_reader_single_digit_0(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test digit 0 detection (10 pulses)."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.1,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    simulate_dial_digit(mock_gpio, "0")
    time.sleep(0.15)  # Wait for timeout

    reader.stop()

    assert collected_digits == ["0"]


def test_dial_reader_phone_number(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test complete phone number dialing."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.1,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    simulate_dial_number(mock_gpio, "5551234", digit_gap=0.15)
    time.sleep(0.15)  # Wait for last digit timeout

    reader.stop()

    assert collected_digits == ["5", "5", "5", "1", "2", "3", "4"]


def test_dial_reader_rapid_pulses(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test rapid pulse handling (faster than normal)."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.1,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    # Dial with very short gaps (20ms instead of 60ms)
    simulate_dial_digit(mock_gpio, "3", pulse_gap=0.02)
    time.sleep(0.15)  # Wait for timeout

    reader.stop()

    assert collected_digits == ["3"]


def test_dial_reader_slow_pulses(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test slow pulse handling (slower than normal)."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.2,  # Longer timeout for slow pulses
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    # Dial with longer gaps (100ms instead of 60ms)
    simulate_dial_digit(mock_gpio, "4", pulse_gap=0.1)
    time.sleep(0.25)  # Wait for timeout

    reader.stop()

    assert collected_digits == ["4"]


def test_dial_reader_partial_dial_timeout(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test partial pulse sequence timeout behavior."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.1,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    # Start dialing a digit but stop mid-way
    simulate_pulse(mock_gpio)
    time.sleep(0.05)
    simulate_pulse(mock_gpio)
    # Wait for timeout - should detect "2"
    time.sleep(0.15)

    reader.stop()

    assert collected_digits == ["2"]


def test_dial_reader_no_pulses(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test no detection when no pulses occur."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.1,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    time.sleep(0.15)  # Wait with no activity

    reader.stop()

    assert collected_digits == []


def test_dial_reader_start_stop_multiple_times(
    mock_gpio: MockGPIO, collected_digits: List[str]
) -> None:
    """Test multiple start/stop cycles."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.1,
        on_digit=lambda d: collected_digits.append(d),
    )

    # First session
    reader.start()
    simulate_dial_digit(mock_gpio, "1")
    time.sleep(0.15)
    reader.stop()

    # Second session
    reader.start()
    simulate_dial_digit(mock_gpio, "2")
    time.sleep(0.15)
    reader.stop()

    assert collected_digits == ["1", "2"]
