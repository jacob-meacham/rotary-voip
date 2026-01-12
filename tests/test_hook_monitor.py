"""Tests for hook switch monitor component."""

import time
from typing import List

import pytest

from rotary_phone.hardware import HOOK
from rotary_phone.hardware.gpio_abstraction import GPIO, MockGPIO
from rotary_phone.hardware.hook_monitor import HookMonitor, HookState
from tests.test_harness import simulate_hang_up, simulate_hook_bounce, simulate_pick_up


@pytest.fixture
def hook_events() -> List[str]:
    """Provide a list to collect hook events."""
    return []


# Tests - Basic State Detection


def test_hook_monitor_initial_state_on_hook(mock_gpio: MockGPIO) -> None:
    """Test initial on-hook state detection."""
    # Ensure pin is HIGH (on-hook)
    mock_gpio.setup(HOOK, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    monitor = HookMonitor(gpio=mock_gpio)
    monitor.start()

    assert monitor.get_state() == HookState.ON_HOOK

    monitor.stop()


def test_hook_monitor_initial_state_off_hook(mock_gpio: MockGPIO) -> None:
    """Test initial off-hook state detection."""
    # Set pin to LOW (off-hook) before starting monitor
    mock_gpio.setup(HOOK, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    mock_gpio.set_input(HOOK, GPIO.LOW)

    monitor = HookMonitor(gpio=mock_gpio)
    monitor.start()

    assert monitor.get_state() == HookState.OFF_HOOK

    monitor.stop()


def test_hook_monitor_pick_up(mock_gpio: MockGPIO, hook_events: List[str]) -> None:
    """Test phone pick-up detection (on-hook -> off-hook)."""
    monitor = HookMonitor(
        gpio=mock_gpio,
        on_off_hook=lambda: hook_events.append("off_hook"),
    )
    monitor.start()

    assert monitor.get_state() == HookState.ON_HOOK

    # Pick up phone
    simulate_pick_up(mock_gpio)
    time.sleep(0.1)  # Wait for debounce

    assert monitor.get_state() == HookState.OFF_HOOK
    assert hook_events == ["off_hook"]

    monitor.stop()


def test_hook_monitor_hang_up(mock_gpio: MockGPIO, hook_events: List[str]) -> None:
    """Test phone hang-up detection (off-hook -> on-hook)."""
    # Start with phone off-hook
    mock_gpio.setup(HOOK, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    mock_gpio.set_input(HOOK, GPIO.LOW)

    monitor = HookMonitor(
        gpio=mock_gpio,
        on_on_hook=lambda: hook_events.append("on_hook"),
    )
    monitor.start()

    assert monitor.get_state() == HookState.OFF_HOOK

    # Hang up phone
    simulate_hang_up(mock_gpio)
    time.sleep(0.1)  # Wait for debounce

    assert monitor.get_state() == HookState.ON_HOOK
    assert hook_events == ["on_hook"]

    monitor.stop()


def test_hook_monitor_multiple_state_changes(mock_gpio: MockGPIO, hook_events: List[str]) -> None:
    """Test multiple pick up / hang up cycles."""
    monitor = HookMonitor(
        gpio=mock_gpio,
        on_off_hook=lambda: hook_events.append("off_hook"),
        on_on_hook=lambda: hook_events.append("on_hook"),
    )
    monitor.start()

    # Pick up
    simulate_pick_up(mock_gpio)
    time.sleep(0.1)
    assert monitor.get_state() == HookState.OFF_HOOK

    # Hang up
    simulate_hang_up(mock_gpio)
    time.sleep(0.1)
    assert monitor.get_state() == HookState.ON_HOOK

    # Pick up again
    simulate_pick_up(mock_gpio)
    time.sleep(0.1)
    assert monitor.get_state() == HookState.OFF_HOOK

    # Hang up again
    simulate_hang_up(mock_gpio)
    time.sleep(0.1)
    assert monitor.get_state() == HookState.ON_HOOK

    assert hook_events == ["off_hook", "on_hook", "off_hook", "on_hook"]

    monitor.stop()


# Tests - Debouncing


def test_hook_monitor_debounce_prevents_bounce(mock_gpio: MockGPIO, hook_events: List[str]) -> None:
    """Test debouncing prevents spurious events from switch bounce."""
    monitor = HookMonitor(
        gpio=mock_gpio,
        on_off_hook=lambda: hook_events.append("off_hook"),
    )
    monitor.start()

    # Simulate switch bounce when picking up
    simulate_hook_bounce(mock_gpio, final_state=GPIO.LOW, bounces=5)
    time.sleep(0.1)  # Wait for debounce

    # Should only register one off-hook event despite bounces
    assert monitor.get_state() == HookState.OFF_HOOK
    assert hook_events == ["off_hook"]

    monitor.stop()


def test_hook_monitor_rapid_changes_during_debounce(
    mock_gpio: MockGPIO, hook_events: List[str]
) -> None:
    """Test that rapid state changes during debounce are ignored."""
    monitor = HookMonitor(
        gpio=mock_gpio,
        on_off_hook=lambda: hook_events.append("off_hook"),
        on_on_hook=lambda: hook_events.append("on_hook"),
    )
    monitor.start()

    # Change state rapidly (faster than debounce time of 0.05s)
    simulate_pick_up(mock_gpio)
    time.sleep(0.02)  # Less than debounce time
    simulate_hang_up(mock_gpio)
    time.sleep(0.02)
    simulate_pick_up(mock_gpio)

    # Wait for debounce to complete
    time.sleep(0.1)

    # Should only register final state
    assert monitor.get_state() == HookState.OFF_HOOK
    assert hook_events == ["off_hook"]

    monitor.stop()


def test_hook_monitor_no_callback_if_state_unchanged(
    mock_gpio: MockGPIO, hook_events: List[str]
) -> None:
    """Test that callbacks are not called if state doesn't actually change."""
    monitor = HookMonitor(
        gpio=mock_gpio,
        on_off_hook=lambda: hook_events.append("off_hook"),
    )
    monitor.start()

    # Pick up phone
    simulate_pick_up(mock_gpio)
    time.sleep(0.1)
    assert hook_events == ["off_hook"]

    # Try to "pick up" again (already off-hook)
    simulate_pick_up(mock_gpio)
    time.sleep(0.1)

    # Should not trigger another callback
    assert hook_events == ["off_hook"]  # Still just one event

    monitor.stop()


def test_hook_monitor_debounce_timing(mock_gpio: MockGPIO) -> None:
    """Test monitor respects debounce timing."""
    monitor = HookMonitor(gpio=mock_gpio)
    monitor.start()
    simulate_pick_up(mock_gpio)
    # Wait for debounce (DEBOUNCE_TIME is 0.05s)
    time.sleep(0.1)
    assert monitor.get_state() == HookState.OFF_HOOK
    monitor.stop()


# Tests - Edge Cases


def test_hook_monitor_start_stop_multiple_times(
    mock_gpio: MockGPIO, hook_events: List[str]
) -> None:
    """Test starting and stopping the monitor multiple times."""
    monitor = HookMonitor(
        gpio=mock_gpio,
        on_off_hook=lambda: hook_events.append("off_hook"),
    )

    # First session
    monitor.start()
    simulate_pick_up(mock_gpio)
    time.sleep(0.1)
    assert monitor.get_state() == HookState.OFF_HOOK
    monitor.stop()

    # Reset to on-hook
    simulate_hang_up(mock_gpio)
    time.sleep(0.1)

    # Second session
    monitor.start()
    simulate_pick_up(mock_gpio)
    time.sleep(0.1)
    assert monitor.get_state() == HookState.OFF_HOOK
    monitor.stop()

    assert hook_events == ["off_hook", "off_hook"]


def test_hook_monitor_no_events_when_stopped(mock_gpio: MockGPIO, hook_events: List[str]) -> None:
    """Test no events when monitor is stopped."""
    monitor = HookMonitor(
        gpio=mock_gpio,
        on_off_hook=lambda: hook_events.append("off_hook"),
    )
    monitor.start()
    monitor.stop()

    # Try to trigger events while stopped
    simulate_pick_up(mock_gpio)
    time.sleep(0.1)

    assert hook_events == []


def test_hook_monitor_call_session(mock_gpio: MockGPIO, hook_events: List[str]) -> None:
    """Test a realistic call session: pick up, talk, hang up."""
    monitor = HookMonitor(
        gpio=mock_gpio,
        on_off_hook=lambda: hook_events.append("call_started"),
        on_on_hook=lambda: hook_events.append("call_ended"),
    )
    monitor.start()

    assert monitor.get_state() == HookState.ON_HOOK

    # User picks up phone to make a call
    simulate_pick_up(mock_gpio)
    time.sleep(0.1)
    assert monitor.get_state() == HookState.OFF_HOOK

    # Simulate some time during the call
    time.sleep(0.2)

    # User hangs up
    simulate_hang_up(mock_gpio)
    time.sleep(0.1)
    assert monitor.get_state() == HookState.ON_HOOK

    assert hook_events == ["call_started", "call_ended"]

    monitor.stop()
