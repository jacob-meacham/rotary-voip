"""Hardware abstraction layer for rotary phone components."""

from .gpio_abstraction import GPIO, get_gpio
from .pins import Pin

__all__ = ["GPIO", "get_gpio", "Pin"]
