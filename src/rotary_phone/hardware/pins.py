"""GPIO pin assignments for the rotary phone hardware.

All pin numbers use BCM (Broadcom) numbering.
"""

# Input pins
HOOK = 17  # Hook switch (HIGH = on-hook, LOW = off-hook)
DIAL_PULSE = 27  # Dial pulse input
DIAL_ACTIVE = 22  # Dial off-normal indicator (optional)

# Output pins
RINGER = 23  # Ringer amplifier enable
