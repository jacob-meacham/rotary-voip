"""Test harness utilities for simulating rotary phone hardware behavior.

This module provides simulation helpers for testing phone components
without actual hardware. All functions work with MockGPIO instances.
"""

import time

from rotary_phone.hardware import DIAL_PULSE, HOOK
from rotary_phone.hardware.gpio_abstraction import GPIO, MockGPIO
from rotary_phone.hardware.pins import DIAL_ACTIVE


# Dial Simulation Helpers
#
# DialReader now uses DIAL_ACTIVE as a digit gate: LOW = dial moved off rest,
# HIGH = dial returned. simulate_dial_digit drives DIAL_ACTIVE around the
# pulse train, including waiting out the settle window so pulses are
# accepted.

# Settle window in DialReader; tests must wait at least this long after
# DIAL_ACTIVE goes LOW before sending the first pulse. Kept short so tests
# stay fast; test DialReaders should also use a small pulse_settle to match.
_TEST_DIAL_SETTLE = 0.04


def simulate_pulse(gpio: MockGPIO) -> None:
    """Simulate a single dial pulse (falling edge on DIAL_PULSE pin).

    NOTE: DialReader now ignores pulses unless DIAL_ACTIVE is LOW. For tests
    that call this standalone, set DIAL_ACTIVE LOW and wait through the
    settle window first.

    Args:
        gpio: MockGPIO instance to simulate on
    """
    gpio.set_input(DIAL_PULSE, GPIO.LOW)
    time.sleep(0.01)
    gpio.set_input(DIAL_PULSE, GPIO.HIGH)


def simulate_dial_digit(gpio: MockGPIO, digit: str, pulse_gap: float = 0.06) -> None:
    """Simulate dialing a single digit on a rotary phone.

    Drives DIAL_ACTIVE around the pulse train so the new gate-based
    DialReader emits the digit:
      1. DIAL_ACTIVE LOW (dial off rest), wait settle window
      2. Send N pulses
      3. DIAL_ACTIVE HIGH (dial returned) — triggers digit emission

    Args:
        gpio: MockGPIO instance to simulate on
        digit: Digit to dial ('0'-'9')
        pulse_gap: Seconds between pulses (default 60ms, realistic for rotary dial)
    """
    pulse_count = 10 if digit == "0" else int(digit)

    # Dial leaves rest
    gpio.set_input(DIAL_ACTIVE, GPIO.LOW)
    # Wait through the settle window so pulses get accepted
    time.sleep(_TEST_DIAL_SETTLE + 0.02)

    for i in range(pulse_count):
        simulate_pulse(gpio)
        if i < pulse_count - 1:
            time.sleep(pulse_gap)

    # Dial returns to rest — DialReader emits the digit on this edge
    time.sleep(0.02)
    gpio.set_input(DIAL_ACTIVE, GPIO.HIGH)


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


# Hook Simulation Helpers


def simulate_pick_up(gpio: MockGPIO) -> None:
    """Simulate picking up the phone (on-hook -> off-hook).

    Args:
        gpio: MockGPIO instance to simulate on
    """
    # Off-hook is LOW
    gpio.set_input(HOOK, GPIO.LOW)


def simulate_hang_up(gpio: MockGPIO) -> None:
    """Simulate hanging up the phone (off-hook -> on-hook).

    Args:
        gpio: MockGPIO instance to simulate on
    """
    # On-hook is HIGH
    gpio.set_input(HOOK, GPIO.HIGH)


def simulate_hook_bounce(gpio: MockGPIO, final_state: int, bounces: int = 3) -> None:
    """Simulate mechanical switch bounce when changing hook state.

    Args:
        gpio: MockGPIO instance to simulate on
        final_state: Final state after bouncing (GPIO.HIGH or GPIO.LOW)
        bounces: Number of bounces to simulate
    """
    current = gpio.input(HOOK)
    for _ in range(bounces):
        # Toggle briefly
        gpio.set_input(HOOK, GPIO.LOW if current == GPIO.HIGH else GPIO.HIGH)
        time.sleep(0.005)  # 5ms bounce
        gpio.set_input(HOOK, current)
        time.sleep(0.005)
    # Set final state
    gpio.set_input(HOOK, final_state)
