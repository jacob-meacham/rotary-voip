"""Shared pytest fixtures for all tests."""

import pytest

from rotary_phone.hardware import get_gpio
from rotary_phone.hardware.gpio_abstraction import GPIO, MockGPIO


@pytest.fixture
def mock_gpio() -> MockGPIO:
    """Provide a configured MockGPIO instance for tests.

    Returns:
        MockGPIO instance with BCM mode set
    """
    gpio = get_gpio(mock=True)
    gpio.setmode(GPIO.BCM)
    assert isinstance(gpio, MockGPIO)
    return gpio
