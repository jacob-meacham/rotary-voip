"""Tests for SIP client implementation."""

import time
from unittest.mock import Mock, call

from rotary_phone.sip import CallState, InMemorySIPClient


# Tests - Registration


def test_initial_state() -> None:
    """Test client starts in IDLE state."""
    client = InMemorySIPClient()
    assert client.get_call_state() == CallState.IDLE


def test_register_immediate() -> None:
    """Test immediate registration (no delay)."""
    client = InMemorySIPClient(registration_delay=0.0)

    client.register("sip:user@example.com", "user", "password")

    assert client.get_call_state() == CallState.REGISTERED


def test_register_with_delay() -> None:
    """Test registration with simulated delay."""
    client = InMemorySIPClient(registration_delay=0.05)

    client.register("sip:user@example.com", "user", "password")

    # Should be in REGISTERING state initially
    assert client.get_call_state() == CallState.REGISTERING

    # Wait for registration to complete
    time.sleep(0.1)
    assert client.get_call_state() == CallState.REGISTERED


def test_unregister() -> None:
    """Test unregistering from SIP server."""
    client = InMemorySIPClient()
    client.register("sip:user@example.com", "user", "password")
    assert client.get_call_state() == CallState.REGISTERED

    client.unregister()

    assert client.get_call_state() == CallState.IDLE


def test_unregister_while_registering() -> None:
    """Test unregister cancels pending registration."""
    client = InMemorySIPClient(registration_delay=0.1)

    client.register("sip:user@example.com", "user", "password")
    assert client.get_call_state() == CallState.REGISTERING

    client.unregister()
    assert client.get_call_state() == CallState.IDLE

    # Wait and verify it doesn't complete registration
    time.sleep(0.15)
    assert client.get_call_state() == CallState.IDLE


def test_register_when_already_registered() -> None:
    """Test registering when already in non-IDLE state does nothing."""
    client = InMemorySIPClient()
    client.register("sip:user1@example.com", "user1", "password1")
    assert client.get_call_state() == CallState.REGISTERED

    # Try to register again (should be ignored)
    client.register("sip:user2@example.com", "user2", "password2")
    assert client.get_call_state() == CallState.REGISTERED


# Tests - Outgoing Calls


def test_make_call_immediate() -> None:
    """Test making an outgoing call with immediate connection."""
    client = InMemorySIPClient(call_connect_delay=0.0)
    client.register("sip:user@example.com", "user", "password")

    client.make_call("5551234567")

    assert client.get_call_state() == CallState.CONNECTED
    assert client.get_current_call_info() == "5551234567"


def test_make_call_with_delay() -> None:
    """Test making an outgoing call with connection delay."""
    client = InMemorySIPClient(call_connect_delay=0.05)
    client.register("sip:user@example.com", "user", "password")

    client.make_call("5551234567")

    # Should be in CALLING state initially
    assert client.get_call_state() == CallState.CALLING
    assert client.get_current_call_info() == "5551234567"

    # Wait for call to connect
    time.sleep(0.1)
    assert client.get_call_state() == CallState.CONNECTED


def test_make_call_when_not_registered() -> None:
    """Test making call without being registered does nothing."""
    client = InMemorySIPClient()

    client.make_call("5551234567")

    assert client.get_call_state() == CallState.IDLE
    assert client.get_current_call_info() is None


def test_hangup_outgoing_call() -> None:
    """Test hanging up an outgoing call."""
    client = InMemorySIPClient()
    client.register("sip:user@example.com", "user", "password")
    client.make_call("5551234567")
    assert client.get_call_state() == CallState.CONNECTED

    client.hangup()

    assert client.get_call_state() == CallState.REGISTERED
    assert client.get_current_call_info() is None


def test_hangup_while_calling() -> None:
    """Test hanging up while call is still connecting."""
    client = InMemorySIPClient(call_connect_delay=0.1)
    client.register("sip:user@example.com", "user", "password")

    client.make_call("5551234567")
    assert client.get_call_state() == CallState.CALLING

    client.hangup()
    assert client.get_call_state() == CallState.REGISTERED

    # Wait and verify call doesn't connect
    time.sleep(0.15)
    assert client.get_call_state() == CallState.REGISTERED


# Tests - Incoming Calls


def test_incoming_call() -> None:
    """Test receiving an incoming call."""
    client = InMemorySIPClient()
    client.register("sip:user@example.com", "user", "password")

    client.simulate_incoming_call("5559876543")

    assert client.get_call_state() == CallState.RINGING
    assert client.get_current_call_info() == "5559876543"


def test_answer_incoming_call() -> None:
    """Test answering an incoming call."""
    client = InMemorySIPClient()
    client.register("sip:user@example.com", "user", "password")
    client.simulate_incoming_call("5559876543")
    assert client.get_call_state() == CallState.RINGING

    client.answer_call()

    assert client.get_call_state() == CallState.CONNECTED
    assert client.get_current_call_info() == "5559876543"


def test_answer_when_not_ringing() -> None:
    """Test answering when not in RINGING state does nothing."""
    client = InMemorySIPClient()
    client.register("sip:user@example.com", "user", "password")

    client.answer_call()

    assert client.get_call_state() == CallState.REGISTERED


def test_hangup_incoming_call() -> None:
    """Test hanging up an incoming call (reject)."""
    client = InMemorySIPClient()
    client.register("sip:user@example.com", "user", "password")
    client.simulate_incoming_call("5559876543")
    assert client.get_call_state() == CallState.RINGING

    client.hangup()

    assert client.get_call_state() == CallState.REGISTERED
    assert client.get_current_call_info() is None


def test_reject_incoming_call() -> None:
    """Test rejecting an incoming call."""
    ended_calls = []

    def on_ended() -> None:
        ended_calls.append(True)

    client = InMemorySIPClient(on_call_ended=on_ended)
    client.register("sip:user@example.com", "user", "password")
    client.simulate_incoming_call("5559876543")
    assert client.get_call_state() == CallState.RINGING

    client.reject_call()

    assert client.get_call_state() == CallState.REGISTERED
    assert client.get_current_call_info() is None
    assert len(ended_calls) == 1


def test_reject_call_when_not_ringing() -> None:
    """Test rejecting when there's no incoming call does nothing."""
    client = InMemorySIPClient()
    client.register("sip:user@example.com", "user", "password")

    # Try to reject when not ringing
    client.reject_call()

    assert client.get_call_state() == CallState.REGISTERED


def test_incoming_call_when_not_registered() -> None:
    """Test incoming call when not registered is ignored."""
    client = InMemorySIPClient()

    client.simulate_incoming_call("5559876543")

    assert client.get_call_state() == CallState.IDLE
    assert client.get_current_call_info() is None


# Tests - Callbacks


def test_on_incoming_call_callback_fires_once_with_caller_id() -> None:
    """simulate_incoming_call invokes on_incoming_call exactly once with the
    caller id passed in."""
    on_incoming = Mock()
    client = InMemorySIPClient(on_incoming_call=on_incoming)
    client.register("sip:user@example.com", "user", "password")

    client.simulate_incoming_call("5559876543")

    on_incoming.assert_called_once_with("5559876543")


def test_on_call_answered_fires_once_for_outgoing_call() -> None:
    """make_call invokes on_call_answered exactly once (the in-memory client
    auto-answers); the callback is invoked with no arguments."""
    on_answered = Mock()
    client = InMemorySIPClient(on_call_answered=on_answered)
    client.register("sip:user@example.com", "user", "password")

    client.make_call("5551234567")

    on_answered.assert_called_once_with()


def test_on_call_answered_fires_once_for_inbound_answer() -> None:
    """answer_call on a ringing inbound call invokes on_call_answered exactly
    once, with no arguments."""
    on_answered = Mock()
    client = InMemorySIPClient(on_call_answered=on_answered)
    client.register("sip:user@example.com", "user", "password")
    client.simulate_incoming_call("5559876543")

    client.answer_call()

    on_answered.assert_called_once_with()


def test_on_call_ended_fires_once_with_no_args_after_hangup() -> None:
    """hangup() invokes on_call_ended exactly once with no arguments."""
    on_ended = Mock()
    client = InMemorySIPClient(on_call_ended=on_ended)
    client.register("sip:user@example.com", "user", "password")
    client.make_call("5551234567")

    client.hangup()

    on_ended.assert_called_once_with()


def test_callbacks_fire_in_order_incoming_then_answered_then_ended() -> None:
    """A full incoming-call lifecycle invokes the callbacks in the documented
    order: on_incoming_call(caller_id) -> on_call_answered() -> on_call_ended().
    """
    on_incoming = Mock()
    on_answered = Mock()
    on_ended = Mock()
    parent = Mock()
    parent.attach_mock(on_incoming, "incoming")
    parent.attach_mock(on_answered, "answered")
    parent.attach_mock(on_ended, "ended")

    client = InMemorySIPClient(
        on_incoming_call=on_incoming,
        on_call_answered=on_answered,
        on_call_ended=on_ended,
    )
    client.register("sip:user@example.com", "user", "password")

    client.simulate_incoming_call("5559876543")
    client.answer_call()
    client.hangup()

    assert parent.mock_calls == [
        call.incoming("5559876543"),
        call.answered(),
        call.ended(),
    ]


# Tests - Edge Cases


def test_hangup_when_no_call() -> None:
    """Test hanging up when there's no active call."""
    client = InMemorySIPClient()
    client.register("sip:user@example.com", "user", "password")

    client.hangup()

    assert client.get_call_state() == CallState.REGISTERED


def test_unregister_during_call() -> None:
    """Test unregister clears call state."""
    client = InMemorySIPClient()
    client.register("sip:user@example.com", "user", "password")
    client.make_call("5551234567")
    assert client.get_call_state() == CallState.CONNECTED

    client.unregister()

    assert client.get_call_state() == CallState.IDLE
    assert client.get_current_call_info() is None


def test_sequential_calls() -> None:
    """Test making multiple calls in sequence."""
    client = InMemorySIPClient()
    client.register("sip:user@example.com", "user", "password")

    # First call
    client.make_call("5551111111")
    assert client.get_call_state() == CallState.CONNECTED
    assert client.get_current_call_info() == "5551111111"
    client.hangup()
    assert client.get_call_state() == CallState.REGISTERED

    # Second call
    client.make_call("5552222222")
    assert client.get_call_state() == CallState.CONNECTED
    assert client.get_current_call_info() == "5552222222"
    client.hangup()
    assert client.get_call_state() == CallState.REGISTERED


def test_sip_uri_destination() -> None:
    """Test making call to SIP URI instead of phone number."""
    client = InMemorySIPClient()
    client.register("sip:user@example.com", "user", "password")

    client.make_call("sip:friend@example.com")

    assert client.get_call_state() == CallState.CONNECTED
    assert client.get_current_call_info() == "sip:friend@example.com"
