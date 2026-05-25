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
# DialReader polls DIAL_ACTIVE on each pulse and drops the pulse if the line
# is HIGH (dial at rest). Tests must drive DIAL_ACTIVE LOW around any
# simulated pulse train so the pulses get accepted.


_TEST_DIAL_SETTLE = 0.07  # must exceed DialReader's pulse_settle default


def simulate_pulse(gpio: MockGPIO) -> None:
    """Simulate a single dial pulse (falling edge on DIAL_PULSE pin).

    Drives DIAL_ACTIVE LOW for the duration (waiting out the settle
    window) so the reader accepts the pulse. Resets DIAL_ACTIVE HIGH
    on exit.

    Args:
        gpio: MockGPIO instance to simulate on
    """
    gpio.set_input(DIAL_ACTIVE, GPIO.LOW)
    time.sleep(_TEST_DIAL_SETTLE)
    gpio.set_input(DIAL_PULSE, GPIO.LOW)
    time.sleep(0.01)
    gpio.set_input(DIAL_PULSE, GPIO.HIGH)
    gpio.set_input(DIAL_ACTIVE, GPIO.HIGH)


def simulate_dial_digit(gpio: MockGPIO, digit: str, pulse_gap: float = 0.06) -> None:
    """Simulate dialing a single digit on a rotary phone.

    Args:
        gpio: MockGPIO instance to simulate on
        digit: Digit to dial ('0'-'9')
        pulse_gap: Seconds between pulses (default 60ms, realistic for rotary dial)
    """
    pulse_count = 10 if digit == "0" else int(digit)

    # Hold DIAL_ACTIVE LOW for the whole pulse train, waiting out the
    # reader's dial-start settle window before sending the first pulse.
    gpio.set_input(DIAL_ACTIVE, GPIO.LOW)
    time.sleep(_TEST_DIAL_SETTLE)
    try:
        for i in range(pulse_count):
            gpio.set_input(DIAL_PULSE, GPIO.LOW)
            time.sleep(0.01)
            gpio.set_input(DIAL_PULSE, GPIO.HIGH)
            if i < pulse_count - 1:
                time.sleep(pulse_gap)
    finally:
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
