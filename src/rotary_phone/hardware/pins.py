"""GPIO pin assignments for the rotary phone hardware.

All pin numbers use BCM (Broadcom) numbering.
"""


class Pins:
    """GPIO pin assignments (BCM numbering)."""

    # Input pins
    HOOK = 17  # Hook switch (HIGH = on-hook, LOW = off-hook)
    DIAL_PULSE = 27  # Dial pulse output
    DIAL_ACTIVE = 22  # Dial off-normal (0 to disable)
    LOW_BATTERY = 24  # PowerBoost LBO pin (optional, 0 to disable)

    # Output pins
    RINGER = 23  # Ringer amplifier enable
