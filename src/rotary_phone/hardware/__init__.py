"""Hardware abstraction layer for rotary phone components."""

from .dial_reader import DialReader
from .gpio_abstraction import GPIO, get_gpio
from .pins import DIAL_ACTIVE, DIAL_PULSE, HOOK, RINGER

__all__ = [
    "GPIO",
    "get_gpio",
    "HOOK",
    "DIAL_PULSE",
    "DIAL_ACTIVE",
    "RINGER",
    "DialReader",
]
