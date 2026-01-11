"""Tests for CallManager."""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from rotary_phone.call_manager import CallManager, PhoneState
from rotary_phone.hardware.hook_monitor import HookState
from rotary_phone.sip.sip_client import CallState


@pytest.fixture
def mock_config():
    """Create a mock configuration manager."""
    config = Mock()

    # Set up get() to return different values based on key
    def config_get_side_effect(key, default=None):
        if key == "timing.inter_digit_timeout":
            return 2.0
        return default

    config.get.side_effect = config_get_side_effect
    config.get_sip_config.return_value = {"server": "", "username": ""}
    config.get_timing_config.return_value = {
        "debounce_time": 0.05,
        "pulse_timeout": 0.1,
        "inter_digit_timeout": 2.0,
    }
    config.get_speed_dial.return_value = None
    config.is_allowed.return_value = True
    return config


@pytest.fixture
def mock_hook_monitor():
    """Create a mock hook monitor."""
    monitor = Mock()
    monitor.get_state.return_value = HookState.ON_HOOK
    monitor.start = Mock()
    monitor.stop = Mock()
    return monitor


@pytest.fixture
def mock_dial_reader():
    """Create a mock dial reader."""
    reader = Mock()
    reader.start = Mock()
    reader.stop = Mock()
    return reader


@pytest.fixture
def mock_ringer():
    """Create a mock ringer."""
    ringer = Mock()
    ringer.start_ringing = Mock()
    ringer.stop_ringing = Mock()
    ringer.is_ringing.return_value = False
    return ringer


@pytest.fixture
def mock_sip_client():
    """Create a mock SIP client."""
    client = Mock()
    client.register = Mock()
    client.unregister = Mock()
    client.make_call = Mock()
    client.answer_call = Mock()
    client.hangup = Mock()
    client.get_call_state.return_value = CallState.IDLE
    return client


@pytest.fixture
def call_manager(mock_config, mock_hook_monitor, mock_dial_reader, mock_ringer, mock_sip_client):
    """Create a call manager with mocked dependencies."""
    return CallManager(
        config=mock_config,
        hook_monitor=mock_hook_monitor,
        dial_reader=mock_dial_reader,
        ringer=mock_ringer,
        sip_client=mock_sip_client,
    )


def test_call_manager_initialization(call_manager):
    """Test that CallManager initializes in IDLE state."""
    assert call_manager.get_state() == PhoneState.IDLE
    assert call_manager.get_dialed_number() == ""
    assert call_manager.get_error_message() == ""


def test_call_manager_start_stop(
    call_manager, mock_hook_monitor, mock_dial_reader, mock_sip_client
):
    """Test starting and stopping the call manager."""
    # Start
    call_manager.start()
    mock_hook_monitor.start.assert_called_once()
    mock_dial_reader.start.assert_called_once()

    # Stop
    call_manager.stop()
    mock_dial_reader.stop.assert_called_once()
    mock_hook_monitor.stop.assert_called_once()
    mock_sip_client.unregister.assert_called_once()


def test_off_hook_from_idle(call_manager):
    """Test going off-hook from IDLE state."""
    call_manager.start()
    assert call_manager.get_state() == PhoneState.IDLE

    # Simulate off-hook
    call_manager._on_off_hook()
    assert call_manager.get_state() == PhoneState.OFF_HOOK_WAITING
    assert call_manager.get_dialed_number() == ""


def test_dialing_single_digit(call_manager):
    """Test dialing a single digit."""
    call_manager.start()
    call_manager._on_off_hook()  # Go off-hook
    assert call_manager.get_state() == PhoneState.OFF_HOOK_WAITING

    # Dial a digit
    call_manager._on_digit("5")
    assert call_manager.get_state() == PhoneState.DIALING
    assert call_manager.get_dialed_number() == "5"


def test_dialing_multiple_digits(call_manager):
    """Test dialing multiple digits."""
    call_manager.start()
    call_manager._on_off_hook()

    # Dial digits
    call_manager._on_digit("1")
    call_manager._on_digit("2")
    call_manager._on_digit("3")

    assert call_manager.get_state() == PhoneState.DIALING
    assert call_manager.get_dialed_number() == "123"


def test_digit_timeout_triggers_validation(call_manager, mock_config):
    """Test that digit timeout triggers number validation."""
    mock_config.is_allowed.return_value = True
    call_manager.start()
    call_manager._on_off_hook()

    # Dial a number
    call_manager._on_digit("5")
    call_manager._on_digit("5")
    call_manager._on_digit("5")

    # Manually trigger timeout
    call_manager._on_digit_timeout()

    # Should transition through VALIDATING to CALLING
    assert call_manager.get_state() == PhoneState.CALLING


def test_allowlist_blocks_number(call_manager, mock_config, mock_sip_client):
    """Test that numbers not in allowlist are blocked."""
    mock_config.is_allowed.return_value = False
    call_manager.start()
    call_manager._on_off_hook()

    # Dial a number
    call_manager._on_digit("9")
    call_manager._on_digit("9")
    call_manager._on_digit("9")
    call_manager._on_digit_timeout()

    # Should transition to ERROR state
    assert call_manager.get_state() == PhoneState.ERROR
    assert "not allowed" in call_manager.get_error_message()
    mock_sip_client.make_call.assert_not_called()


def test_speed_dial_expansion(call_manager, mock_config, mock_sip_client):
    """Test that speed dial codes are expanded."""
    mock_config.get_speed_dial.return_value = "5551234567"
    mock_config.is_allowed.return_value = True
    call_manager.start()
    call_manager._on_off_hook()

    # Dial speed dial code
    call_manager._on_digit("1")
    call_manager._on_digit("1")
    call_manager._on_digit_timeout()

    # Should call the expanded number
    mock_config.get_speed_dial.assert_called_with("11")
    mock_sip_client.make_call.assert_called_with("5551234567")
    assert call_manager.get_state() == PhoneState.CALLING


def test_outbound_call_flow(call_manager, mock_config, mock_sip_client):
    """Test complete outbound call flow."""
    mock_config.is_allowed.return_value = True
    call_manager.start()

    # Pick up phone
    call_manager._on_off_hook()
    assert call_manager.get_state() == PhoneState.OFF_HOOK_WAITING

    # Dial number
    call_manager._on_digit("5")
    call_manager._on_digit("5")
    call_manager._on_digit("5")
    call_manager._on_digit_timeout()
    assert call_manager.get_state() == PhoneState.CALLING

    # Call answered
    call_manager._on_call_answered()
    assert call_manager.get_state() == PhoneState.CONNECTED

    # Hang up
    call_manager._on_on_hook()
    assert call_manager.get_state() == PhoneState.IDLE
    mock_sip_client.hangup.assert_called_once()


def test_incoming_call_flow(call_manager, mock_ringer, mock_sip_client, mock_hook_monitor):
    """Test incoming call flow."""
    call_manager.start()
    assert call_manager.get_state() == PhoneState.IDLE

    # Incoming call
    call_manager._on_incoming_call("5551234567")
    assert call_manager.get_state() == PhoneState.RINGING
    mock_ringer.start_ringing.assert_called_once()

    # Answer call
    call_manager._on_off_hook()
    assert call_manager.get_state() == PhoneState.CONNECTED
    mock_ringer.stop_ringing.assert_called_once()
    mock_sip_client.answer_call.assert_called_once()

    # Hang up
    call_manager._on_on_hook()
    assert call_manager.get_state() == PhoneState.IDLE
    mock_sip_client.hangup.assert_called_once()


def test_incoming_call_ignored_when_not_idle(call_manager, mock_ringer):
    """Test that incoming calls are ignored when phone is not idle."""
    call_manager.start()
    call_manager._on_off_hook()  # Go off-hook
    assert call_manager.get_state() == PhoneState.OFF_HOOK_WAITING

    # Try to receive incoming call
    call_manager._on_incoming_call("5551234567")

    # Should remain in OFF_HOOK_WAITING, ringer not started
    assert call_manager.get_state() == PhoneState.OFF_HOOK_WAITING
    mock_ringer.start_ringing.assert_not_called()


def test_hang_up_during_dialing(call_manager, mock_sip_client):
    """Test hanging up while dialing."""
    call_manager.start()
    call_manager._on_off_hook()
    call_manager._on_digit("5")
    call_manager._on_digit("5")
    assert call_manager.get_state() == PhoneState.DIALING

    # Hang up
    call_manager._on_on_hook()

    # Should cancel dialing and return to IDLE
    assert call_manager.get_state() == PhoneState.IDLE
    assert call_manager.get_dialed_number() == ""
    mock_sip_client.make_call.assert_not_called()


def test_hang_up_during_ringing(call_manager, mock_ringer):
    """Test hanging up during incoming call."""
    call_manager.start()
    call_manager._on_incoming_call("5551234567")
    assert call_manager.get_state() == PhoneState.RINGING

    # Hang up (or rather, stay on-hook)
    call_manager._on_on_hook()

    # Should stop ringing and return to IDLE
    assert call_manager.get_state() == PhoneState.IDLE
    mock_ringer.stop_ringing.assert_called_once()


def test_ignore_digits_in_wrong_state(call_manager):
    """Test that digits are ignored in wrong states."""
    call_manager.start()
    assert call_manager.get_state() == PhoneState.IDLE

    # Try to dial while on-hook
    call_manager._on_digit("5")

    # Should remain IDLE, number not recorded
    assert call_manager.get_state() == PhoneState.IDLE
    assert call_manager.get_dialed_number() == ""


def test_call_ended_callback(call_manager, mock_hook_monitor):
    """Test handling call ended callback."""
    mock_hook_monitor.get_state.return_value = HookState.ON_HOOK
    call_manager.start()

    # Simulate active call
    call_manager._transition_to(PhoneState.CONNECTED)

    # Call ends
    call_manager._on_call_ended()

    # Should return to IDLE if phone on-hook
    assert call_manager.get_state() == PhoneState.IDLE


def test_call_ended_while_off_hook(call_manager, mock_hook_monitor):
    """Test call ending while phone is still off-hook."""
    mock_hook_monitor.get_state.return_value = HookState.OFF_HOOK
    call_manager.start()

    # Simulate active call
    call_manager._transition_to(PhoneState.CONNECTED)

    # Call ends but phone still off-hook
    call_manager._on_call_ended()

    # Should transition to OFF_HOOK_WAITING
    assert call_manager.get_state() == PhoneState.OFF_HOOK_WAITING


def test_make_call_failure(call_manager, mock_config, mock_sip_client):
    """Test handling of make_call failure."""
    mock_config.is_allowed.return_value = True
    mock_sip_client.make_call.side_effect = Exception("SIP error")

    call_manager.start()
    call_manager._on_off_hook()
    call_manager._on_digit("5")
    call_manager._on_digit("5")
    call_manager._on_digit("5")
    call_manager._on_digit_timeout()

    # Should transition to ERROR state
    assert call_manager.get_state() == PhoneState.ERROR
    assert "Call failed" in call_manager.get_error_message()


def test_answer_call_failure(call_manager, mock_sip_client, mock_ringer):
    """Test handling of answer_call failure."""
    mock_sip_client.answer_call.side_effect = Exception("Answer failed")

    call_manager.start()
    call_manager._on_incoming_call("5551234567")
    assert call_manager.get_state() == PhoneState.RINGING

    # Try to answer
    call_manager._on_off_hook()

    # Should transition to ERROR state
    assert call_manager.get_state() == PhoneState.ERROR
    assert "Failed to answer" in call_manager.get_error_message()
    mock_ringer.stop_ringing.assert_called_once()


def test_inter_digit_timer_cancellation(call_manager):
    """Test that inter-digit timer is properly cancelled."""
    call_manager.start()
    call_manager._on_off_hook()

    # Dial first digit
    call_manager._on_digit("5")
    first_timer = call_manager._digit_timer
    assert first_timer is not None

    # Dial second digit quickly (should cancel first timer)
    call_manager._on_digit("5")
    second_timer = call_manager._digit_timer

    # Timers should be different
    assert first_timer != second_timer
    assert not first_timer.is_alive()  # First timer should be cancelled


def test_multiple_starts_ignored(call_manager, mock_hook_monitor):
    """Test that multiple start() calls are ignored."""
    call_manager.start()
    call_manager.start()
    call_manager.start()

    # Should only start once
    assert mock_hook_monitor.start.call_count == 1


def test_error_state_clears_on_hangup(call_manager):
    """Test that ERROR state clears when hanging up."""
    call_manager.start()
    call_manager._transition_to(PhoneState.ERROR, "Some error")
    assert call_manager.get_error_message() == "Some error"

    # Hang up
    call_manager._on_on_hook()

    # Should return to IDLE and clear error
    assert call_manager.get_state() == PhoneState.IDLE
    assert call_manager.get_error_message() == ""


def test_sip_registration_with_credentials(call_manager, mock_config, mock_sip_client):
    """Test that SIP registration is attempted when credentials are provided."""
    mock_config.get_sip_config.return_value = {
        "server": "sip.example.com",
        "username": "test_user",
        "password": "test_pass",
        "port": 5060,
    }

    call_manager.start()

    mock_sip_client.register.assert_called_once_with(
        account_uri="sip.example.com:5060",
        username="test_user",
        password="test_pass",
    )


def test_sip_registration_skipped_without_credentials(call_manager, mock_config, mock_sip_client):
    """Test that SIP registration is skipped when credentials are missing."""
    mock_config.get_sip_config.return_value = {"server": "", "username": ""}

    call_manager.start()

    # Should not attempt registration
    mock_sip_client.register.assert_not_called()


def test_inter_digit_timeout_value():
    """Test that inter-digit timeout is configured from config."""
    mock_config = Mock()
    mock_config.get.return_value = 3.5
    mock_config.get_sip_config.return_value = {"server": "", "username": ""}

    # Create new manager to pick up config
    manager = CallManager(
        config=mock_config,
        hook_monitor=Mock(),
        dial_reader=Mock(),
        ringer=Mock(),
        sip_client=Mock(),
    )

    assert manager._inter_digit_timeout == 3.5
