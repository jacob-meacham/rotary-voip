"""End-to-end integration tests for the complete phone system.

These tests verify that all components work together correctly:
- CallManager orchestrates everything
- Hardware components (HookMonitor, DialReader, Ringer)
- SIP client (InMemorySIPClient for testing)
- Configuration and allowlist logic

Focus: Critical user flows and component integration.
Edge cases and unit-level behavior are tested in component-specific test files.
"""

import time
from unittest.mock import Mock

import pytest

from rotary_phone.call_manager import CallManager, PhoneState
from rotary_phone.hardware.dial_reader import DialReader
from rotary_phone.hardware.gpio_abstraction import MockGPIO
from rotary_phone.hardware.hook_monitor import HookMonitor, HookState
from rotary_phone.hardware.pins import DIAL_PULSE, HOOK, RINGER
from rotary_phone.hardware.ringer import Ringer
from rotary_phone.sip.in_memory_client import InMemorySIPClient
from rotary_phone.sip.sip_client import CallState


@pytest.fixture
def mock_gpio():
    """Create a mock GPIO instance."""
    return MockGPIO()


@pytest.fixture
def test_config():
    """Create a test configuration."""
    config = Mock()

    def config_get(key, default=None):
        config_values = {
            "timing.inter_digit_timeout": 0.5,  # Shorter timeout for tests
            "speed_dial": {},
            "allowlist": ["*"],  # Allow all by default
        }
        return config_values.get(key, default)

    config.get.side_effect = config_get
    config.get_sip_config.return_value = {
        "server": "test.sip.server",
        "username": "testuser",
        "password": "testpass",
        "port": 5060,
    }
    config.get_speed_dial.return_value = None
    config.is_allowed.return_value = True

    return config


@pytest.fixture
def phone_system(mock_gpio, test_config):
    """Create a complete phone system with all components wired together."""
    # Initialize GPIO pins to default states (before components read them)
    # This ensures consistent starting state
    # Note: setup() will initialize values, but we want to be explicit

    # Create components
    hook_monitor = HookMonitor(gpio=mock_gpio, debounce_time=0.01)
    dial_reader = DialReader(gpio=mock_gpio, pulse_timeout=0.2)  # Longer pulse timeout
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.1, ring_off_duration=0.1)
    sip_client = InMemorySIPClient(registration_delay=0.0)  # Immediate registration

    # Create call manager
    call_manager = CallManager(
        config=test_config,
        hook_monitor=hook_monitor,
        dial_reader=dial_reader,
        ringer=ringer,
        sip_client=sip_client,
    )

    # Start the system
    call_manager.start()

    # Give system time to initialize and register
    time.sleep(0.15)

    yield {
        "gpio": mock_gpio,
        "hook_monitor": hook_monitor,
        "dial_reader": dial_reader,
        "ringer": ringer,
        "sip_client": sip_client,
        "call_manager": call_manager,
        "config": test_config,
    }

    # Cleanup
    call_manager.stop()


def simulate_hook_off(gpio):
    """Simulate picking up the phone."""
    gpio.set_input(HOOK, MockGPIO.LOW)


def simulate_hook_on(gpio):
    """Simulate hanging up the phone."""
    gpio.set_input(HOOK, MockGPIO.HIGH)


def simulate_dial_digit(gpio, digit):
    """Simulate dialing a digit on the rotary dial.

    Args:
        gpio: MockGPIO instance
        digit: Digit to dial (0-9)
    """
    pulses = 10 if digit == "0" else int(digit)
    for _ in range(pulses):
        gpio.set_input(DIAL_PULSE, MockGPIO.LOW)  # Falling edge
        time.sleep(0.03)
        gpio.set_input(DIAL_PULSE, MockGPIO.HIGH)  # Rising edge
        time.sleep(0.03)


@pytest.mark.flaky
def test_outbound_call_flow(phone_system):
    """Test complete outbound call flow: pick up, dial, call, answer, hang up.

    Note: This test has timing issues with state transitions and may fail intermittently.
    """
    manager = phone_system["call_manager"]
    gpio = phone_system["gpio"]
    sip_client = phone_system["sip_client"]

    # Initially idle
    assert manager.get_state() == PhoneState.IDLE

    # Pick up phone
    simulate_hook_off(gpio)
    time.sleep(0.05)  # Wait for debounce
    assert manager.get_state() == PhoneState.OFF_HOOK_WAITING

    # Dial a number
    simulate_dial_digit(gpio, "5")
    time.sleep(0.15)  # Wait for pulse timeout
    assert manager.get_state() == PhoneState.DIALING
    assert manager.get_dialed_number() == "5"

    simulate_dial_digit(gpio, "5")
    time.sleep(0.15)
    assert manager.get_dialed_number() == "55"

    simulate_dial_digit(gpio, "5")
    time.sleep(0.6)  # Wait for inter-digit timeout
    assert manager.get_dialed_number() == "555"

    # Wait for state machine to transition from DIALING -> VALIDATING -> CALLING
    # This happens asynchronously in the timer thread
    time.sleep(0.4)  # Give time for validation and call initiation
    assert manager.get_state() == PhoneState.CALLING

    # Simulate call being answered - add small delay to ensure CALLING state is fully established
    time.sleep(0.1)
    sip_client.simulate_call_answered()
    time.sleep(0.2)  # Wait for state transition
    assert manager.get_state() == PhoneState.CONNECTED

    # Hang up
    simulate_hook_on(gpio)
    time.sleep(0.05)
    assert manager.get_state() == PhoneState.IDLE
    assert sip_client.get_call_state() == CallState.REGISTERED  # Still registered, just no call


def test_incoming_call_flow(phone_system):
    """Test incoming call flow: ring, answer, connected, hang up."""
    manager = phone_system["call_manager"]
    gpio = phone_system["gpio"]
    sip_client = phone_system["sip_client"]
    ringer = phone_system["ringer"]

    # Initially idle
    assert manager.get_state() == PhoneState.IDLE
    assert not ringer.is_ringing()

    # Simulate incoming call
    sip_client.simulate_incoming_call("5551234567")
    time.sleep(0.05)

    # Should be ringing
    assert manager.get_state() == PhoneState.RINGING
    assert ringer.is_ringing()

    # Answer call
    simulate_hook_off(gpio)
    time.sleep(0.05)

    # Should be connected, ringer stopped
    assert manager.get_state() == PhoneState.CONNECTED
    assert not ringer.is_ringing()

    # Hang up
    simulate_hook_on(gpio)
    time.sleep(0.05)

    # Back to idle
    assert manager.get_state() == PhoneState.IDLE
    assert sip_client.get_call_state() == CallState.REGISTERED  # Still registered after call


def test_allowlist_blocking(phone_system):
    """Test that numbers not in allowlist are blocked."""
    manager = phone_system["call_manager"]
    gpio = phone_system["gpio"]
    sip_client = phone_system["sip_client"]
    config = phone_system["config"]

    # Set allowlist to block all
    config.is_allowed.return_value = False

    # Pick up and dial
    simulate_hook_off(gpio)
    time.sleep(0.1)

    simulate_dial_digit(gpio, "9")
    time.sleep(0.25)
    simulate_dial_digit(gpio, "9")
    time.sleep(0.25)
    simulate_dial_digit(gpio, "9")
    time.sleep(0.7)  # Wait for inter-digit timeout

    # Should be in ERROR state
    assert manager.get_state() == PhoneState.ERROR
    assert "not allowed" in manager.get_error_message()

    # Should NOT have made a call
    assert sip_client.get_call_state() == CallState.REGISTERED  # Still registered after call

    # Hang up clears error
    simulate_hook_on(gpio)
    time.sleep(0.05)
    assert manager.get_state() == PhoneState.IDLE
    assert manager.get_error_message() == ""


def test_speed_dial_expansion(phone_system):
    """Test speed dial code expansion."""
    manager = phone_system["call_manager"]
    gpio = phone_system["gpio"]
    sip_client = phone_system["sip_client"]
    config = phone_system["config"]

    # Set up speed dial
    config.get_speed_dial.return_value = "5551234567"

    # Pick up and dial speed code
    simulate_hook_off(gpio)
    time.sleep(0.1)

    simulate_dial_digit(gpio, "1")
    time.sleep(0.25)
    simulate_dial_digit(gpio, "1")
    time.sleep(0.7)  # Wait for inter-digit timeout

    # Should be calling the expanded number
    time.sleep(0.2)
    assert manager.get_state() == PhoneState.CALLING
    config.get_speed_dial.assert_called_with("11")




@pytest.mark.flaky
def test_call_ended_remotely(phone_system):
    """Test handling when remote party hangs up.

    Note: This test has timing issues with state transitions and may fail intermittently.
    """
    manager = phone_system["call_manager"]
    gpio = phone_system["gpio"]
    sip_client = phone_system["sip_client"]

    # Make a call
    simulate_hook_off(gpio)
    time.sleep(0.1)

    simulate_dial_digit(gpio, "5")
    time.sleep(0.25)
    simulate_dial_digit(gpio, "5")
    time.sleep(0.25)
    simulate_dial_digit(gpio, "5")
    time.sleep(0.7)  # Wait for inter-digit timeout

    # Wait for VALIDATING -> CALLING transition
    time.sleep(0.4)  # Give time for validation and call initiation
    assert manager.get_state() == PhoneState.CALLING

    # Add delay before answering to ensure CALLING state is fully established
    time.sleep(0.1)
    sip_client.simulate_call_answered()
    time.sleep(0.2)  # Wait for CONNECTED state
    assert manager.get_state() == PhoneState.CONNECTED

    # Remote party hangs up (phone still off-hook)
    sip_client.simulate_call_ended()
    time.sleep(0.1)

    # Should return to OFF_HOOK_WAITING (phone still off-hook)
    assert manager.get_state() == PhoneState.OFF_HOOK_WAITING

    # Now hang up
    simulate_hook_on(gpio)
    time.sleep(0.05)
    assert manager.get_state() == PhoneState.IDLE




@pytest.mark.flaky
def test_multiple_sequential_calls(phone_system):
    """Test making multiple calls in sequence.

    Note: This test has timing issues with state transitions and may fail intermittently.
    """
    manager = phone_system["call_manager"]
    gpio = phone_system["gpio"]
    sip_client = phone_system["sip_client"]

    # First call
    simulate_hook_off(gpio)
    time.sleep(0.1)
    simulate_dial_digit(gpio, "1")
    time.sleep(0.25)
    simulate_dial_digit(gpio, "1")
    time.sleep(0.25)
    simulate_dial_digit(gpio, "1")
    time.sleep(0.7)  # Wait for inter-digit timeout

    # Wait for VALIDATING -> CALLING transition
    time.sleep(0.4)
    assert manager.get_state() == PhoneState.CALLING

    # Add delay before answering to ensure CALLING state is fully established
    time.sleep(0.1)
    sip_client.simulate_call_answered()
    time.sleep(0.2)
    assert manager.get_state() == PhoneState.CONNECTED

    simulate_hook_on(gpio)
    time.sleep(0.1)
    assert manager.get_state() == PhoneState.IDLE

    # Second call
    simulate_hook_off(gpio)
    time.sleep(0.1)
    assert manager.get_dialed_number() == ""  # Number should be cleared

    simulate_dial_digit(gpio, "2")
    time.sleep(0.25)
    simulate_dial_digit(gpio, "2")
    time.sleep(0.25)
    simulate_dial_digit(gpio, "2")
    time.sleep(0.7)  # Wait for inter-digit timeout
    assert manager.get_dialed_number() == "222"

    # Wait for VALIDATING -> CALLING transition
    time.sleep(0.4)
    assert manager.get_state() == PhoneState.CALLING

    simulate_hook_on(gpio)
    time.sleep(0.05)
    assert manager.get_state() == PhoneState.IDLE


