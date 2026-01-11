"""Tests for rotary dial reader with simulation helpers."""

import time
from typing import List

import pytest

from rotary_phone.hardware import DIAL_PULSE, get_gpio
from rotary_phone.hardware.dial_reader import DialReader
from rotary_phone.hardware.gpio_abstraction import GPIO, MockGPIO


# Test Harness Helpers


def simulate_pulse(gpio: MockGPIO) -> None:
    """Simulate a single dial pulse (falling edge on DIAL_PULSE pin).

    Args:
        gpio: MockGPIO instance to simulate on
    """
    # Dial pulse is a falling edge (HIGH -> LOW -> HIGH)
    # The DialReader only cares about falling edges
    gpio.set_input(DIAL_PULSE, GPIO.LOW)
    time.sleep(0.01)  # Brief pulse
    gpio.set_input(DIAL_PULSE, GPIO.HIGH)


def simulate_dial_digit(gpio: MockGPIO, digit: str, pulse_gap: float = 0.06) -> None:
    """Simulate dialing a single digit on a rotary phone.

    Args:
        gpio: MockGPIO instance to simulate on
        digit: Digit to dial ('0'-'9')
        pulse_gap: Seconds between pulses (default 60ms, realistic for rotary dial)
    """
    # Map digit to pulse count (0 = 10 pulses, 1 = 1 pulse, etc.)
    pulse_count = 10 if digit == "0" else int(digit)

    for i in range(pulse_count):
        simulate_pulse(gpio)
        if i < pulse_count - 1:  # Don't wait after last pulse
            time.sleep(pulse_gap)


def simulate_dial_number(
    gpio: MockGPIO,
    number: str,
    pulse_gap: float = 0.06,
    digit_gap: float = 0.5,
) -> None:
    """Simulate dialing a complete phone number.

    Args:
        gpio: MockGPIO instance to simulate on
        number: Phone number to dial (string of digits)
        pulse_gap: Seconds between pulses within a digit
        digit_gap: Seconds between digits
    """
    for i, digit in enumerate(number):
        if not digit.isdigit():
            continue
        simulate_dial_digit(gpio, digit, pulse_gap)
        if i < len(number) - 1:  # Don't wait after last digit
            time.sleep(digit_gap)


# Fixtures


@pytest.fixture
def mock_gpio() -> MockGPIO:
    """Provide a MockGPIO instance for tests."""
    gpio = get_gpio(mock=True)
    gpio.setmode(GPIO.BCM)
    assert isinstance(gpio, MockGPIO)
    return gpio


@pytest.fixture
def collected_digits() -> List[str]:
    """Provide a list to collect detected digits."""
    return []


# Tests


def test_dial_reader_single_digit_1(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test detecting digit 1 (1 pulse)."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.3,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    simulate_dial_digit(mock_gpio, "1")
    time.sleep(0.4)  # Wait for timeout

    reader.stop()

    assert collected_digits == ["1"]


def test_dial_reader_single_digit_5(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test detecting digit 5 (5 pulses)."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.3,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    simulate_dial_digit(mock_gpio, "5")
    time.sleep(0.4)  # Wait for timeout

    reader.stop()

    assert collected_digits == ["5"]


def test_dial_reader_single_digit_0(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test detecting digit 0 (10 pulses)."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.3,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    simulate_dial_digit(mock_gpio, "0")
    time.sleep(0.4)  # Wait for timeout

    reader.stop()

    assert collected_digits == ["0"]


def test_dial_reader_all_digits(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test detecting all digits 0-9."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.3,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    # Dial all digits with gaps between them
    for digit in "1234567890":
        simulate_dial_digit(mock_gpio, digit)
        time.sleep(0.5)  # Gap between digits

    reader.stop()

    assert collected_digits == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]


def test_dial_reader_phone_number(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test dialing a complete phone number."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.3,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    simulate_dial_number(mock_gpio, "5551234")
    time.sleep(0.5)  # Wait for last digit timeout

    reader.stop()

    assert collected_digits == ["5", "5", "5", "1", "2", "3", "4"]


def test_dial_reader_emergency_number(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test dialing 911."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.3,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    simulate_dial_number(mock_gpio, "911")
    time.sleep(0.5)  # Wait for last digit timeout

    reader.stop()

    assert collected_digits == ["9", "1", "1"]


def test_dial_reader_rapid_pulses(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test handling rapid pulses (faster than normal dialing)."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.3,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    # Dial with very short gaps (20ms instead of 60ms)
    simulate_dial_digit(mock_gpio, "3", pulse_gap=0.02)
    time.sleep(0.4)  # Wait for timeout

    reader.stop()

    assert collected_digits == ["3"]


def test_dial_reader_slow_pulses(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test handling slow pulses (slower than normal dialing)."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.3,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    # Dial with longer gaps (150ms instead of 60ms)
    simulate_dial_digit(mock_gpio, "4", pulse_gap=0.15)
    time.sleep(0.4)  # Wait for timeout

    reader.stop()

    assert collected_digits == ["4"]


def test_dial_reader_partial_dial_timeout(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test that partial pulse sequences timeout correctly."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.2,  # Shorter timeout
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    # Start dialing a digit but stop mid-way
    simulate_pulse(mock_gpio)
    time.sleep(0.05)
    simulate_pulse(mock_gpio)
    # Wait for timeout - should detect "2"
    time.sleep(0.3)

    reader.stop()

    assert collected_digits == ["2"]


def test_dial_reader_no_pulses(mock_gpio: MockGPIO, collected_digits: List[str]) -> None:
    """Test that no digits are detected when no pulses occur."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.3,
        on_digit=lambda d: collected_digits.append(d),
    )
    reader.start()

    time.sleep(0.5)  # Wait with no activity

    reader.stop()

    assert collected_digits == []


def test_dial_reader_start_stop_multiple_times(
    mock_gpio: MockGPIO, collected_digits: List[str]
) -> None:
    """Test starting and stopping the reader multiple times."""
    reader = DialReader(
        gpio=mock_gpio,
        pulse_timeout=0.3,
        on_digit=lambda d: collected_digits.append(d),
    )

    # First session
    reader.start()
    simulate_dial_digit(mock_gpio, "1")
    time.sleep(0.4)
    reader.stop()

    # Second session
    reader.start()
    simulate_dial_digit(mock_gpio, "2")
    time.sleep(0.4)
    reader.stop()

    assert collected_digits == ["1", "2"]
