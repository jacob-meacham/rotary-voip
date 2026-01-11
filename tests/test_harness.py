"""Test harness utilities for simulating rotary phone hardware behavior.

This module provides simulation helpers for testing phone components
without actual hardware. All functions work with MockGPIO instances.
"""

import time

from rotary_phone.hardware import DIAL_PULSE, HOOK
from rotary_phone.hardware.gpio_abstraction import GPIO, MockGPIO


# Dial Simulation Helpers


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
