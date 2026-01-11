"""Interactive test harness for the rotary phone system.

This harness allows you to manually test the phone system without physical hardware.
It uses MockGPIO and InMemorySIPClient to simulate all hardware interactions.

Run with:
    python -m tests.manual.test_harness
"""

import sys
import time
from unittest.mock import Mock

from rotary_phone.call_manager import CallManager, PhoneState
from rotary_phone.hardware.dial_reader import DialReader
from rotary_phone.hardware.gpio_abstraction import MockGPIO
from rotary_phone.hardware.hook_monitor import HookMonitor
from rotary_phone.hardware.pins import DIAL_PULSE, HOOK
from rotary_phone.hardware.ringer import Ringer
from rotary_phone.sip.in_memory_client import InMemorySIPClient


class TestHarness:
    """Interactive test harness for phone system."""

    def __init__(self):
        """Initialize the test harness with mock components."""
        self.gpio = MockGPIO()

        # Create mock config
        config = Mock()
        config.get.side_effect = lambda key, default=None: {
            "timing.inter_digit_timeout": 3.0,
            "speed_dial": {},
            "allowlist": ["*"],
        }.get(key, default)
        config.get_speed_dial.return_value = None
        config.is_allowed.return_value = True
        config.get_sip_config.return_value = {
            "server": "test.sip.server",
            "username": "testuser",
            "password": "testpass",
            "port": 5060,
        }

        # Create components
        self.hook_monitor = HookMonitor(gpio=self.gpio, debounce_time=0.05)
        self.dial_reader = DialReader(gpio=self.gpio, pulse_timeout=0.2)
        self.ringer = Ringer(gpio=self.gpio, ring_on_duration=2.0, ring_off_duration=4.0)
        self.sip_client = InMemorySIPClient(registration_delay=0.0)

        # Create call manager
        self.call_manager = CallManager(
            config=config,
            hook_monitor=self.hook_monitor,
            dial_reader=self.dial_reader,
            ringer=self.ringer,
            sip_client=self.sip_client,
        )

        # Start the system
        self.call_manager.start()
        time.sleep(0.1)  # Give system time to initialize

    def stop(self):
        """Stop the phone system."""
        self.call_manager.stop()

    def hook_off(self):
        """Simulate picking up the phone."""
        print("→ Picking up phone (hook off)")
        self.gpio.set_input(HOOK, MockGPIO.LOW)
        time.sleep(0.1)

    def hook_on(self):
        """Simulate hanging up the phone."""
        print("→ Hanging up phone (hook on)")
        self.gpio.set_input(HOOK, MockGPIO.HIGH)
        time.sleep(0.1)

    def dial_digit(self, digit: str):
        """Simulate dialing a digit.

        Args:
            digit: Digit to dial (0-9)
        """
        if not digit.isdigit():
            print(f"✗ Invalid digit: {digit}")
            return

        print(f"→ Dialing digit: {digit}")
        pulses = 10 if digit == "0" else int(digit)
        for _ in range(pulses):
            self.gpio.set_input(DIAL_PULSE, MockGPIO.LOW)
            time.sleep(0.02)
            self.gpio.set_input(DIAL_PULSE, MockGPIO.HIGH)
            time.sleep(0.02)
        time.sleep(0.1)

    def simulate_incoming_call(self, number: str = "5551234567"):
        """Simulate an incoming call.

        Args:
            number: The caller's number
        """
        print(f"→ Simulating incoming call from: {number}")
        self.sip_client.simulate_incoming_call(number)
        time.sleep(0.1)

    def simulate_call_answered(self):
        """Simulate the remote party answering the call."""
        print("→ Simulating remote party answered")
        self.sip_client.simulate_call_answered()
        time.sleep(0.1)

    def simulate_call_ended(self):
        """Simulate the remote party ending the call."""
        print("→ Simulating remote party hung up")
        self.sip_client.simulate_call_ended()
        time.sleep(0.1)

    def show_status(self):
        """Display current system status."""
        state = self.call_manager.get_state()
        dialed = self.call_manager.get_dialed_number()
        error = self.call_manager.get_error_message()
        sip_state = self.sip_client.get_call_state()
        hook_state = self.hook_monitor.get_state()
        ringing = self.ringer.is_ringing()

        print("\n" + "=" * 60)
        print("PHONE SYSTEM STATUS")
        print("=" * 60)
        print(f"Phone State:    {state.value}")
        print(f"Hook State:     {hook_state.value}")
        print(f"SIP State:      {sip_state.value}")
        print(f"Dialed Number:  {dialed or '(none)'}")
        print(f"Ringing:        {'YES' if ringing else 'NO'}")
        if error:
            print(f"Error:          {error}")
        print("=" * 60 + "\n")


def print_menu():
    """Print the interactive menu."""
    print("\n" + "─" * 60)
    print("COMMANDS:")
    print("  u  - Pick up phone (hook off)")
    print("  d  - Hang up phone (hook on)")
    print("  0-9 - Dial digit")
    print("  i  - Simulate incoming call")
    print("  a  - Simulate remote party answered")
    print("  e  - Simulate remote party hung up")
    print("  s  - Show status")
    print("  h  - Show this help")
    print("  q  - Quit")
    print("─" * 60)


def main():
    """Run the interactive test harness."""
    print("=" * 60)
    print("ROTARY PHONE TEST HARNESS")
    print("=" * 60)
    print("\nInitializing phone system...")

    harness = TestHarness()

    print("✓ System initialized")
    harness.show_status()
    print_menu()

    try:
        while True:
            try:
                cmd = input("\nCommand> ").strip().lower()

                if cmd == "q":
                    print("Shutting down...")
                    break
                elif cmd == "u":
                    harness.hook_off()
                    harness.show_status()
                elif cmd == "d":
                    harness.hook_on()
                    harness.show_status()
                elif cmd.isdigit() and len(cmd) == 1:
                    harness.dial_digit(cmd)
                    harness.show_status()
                elif cmd == "i":
                    number = input("  Caller number [5551234567]: ").strip() or "5551234567"
                    harness.simulate_incoming_call(number)
                    harness.show_status()
                elif cmd == "a":
                    harness.simulate_call_answered()
                    harness.show_status()
                elif cmd == "e":
                    harness.simulate_call_ended()
                    harness.show_status()
                elif cmd == "s":
                    harness.show_status()
                elif cmd == "h":
                    print_menu()
                elif cmd == "":
                    continue
                else:
                    print(f"✗ Unknown command: {cmd}")
                    print("  Type 'h' for help")

            except KeyboardInterrupt:
                print("\n\nShutting down...")
                break
            except EOFError:
                print("\n\nShutting down...")
                break

    finally:
        harness.stop()
        print("✓ Shutdown complete")


if __name__ == "__main__":
    main()
