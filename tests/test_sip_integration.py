"""Integration tests for SIP client against real SIPp server.

These tests require Docker and docker-compose to be installed.
Run with: ./run_integration_tests.sh

Or manually:
    docker-compose -f docker-compose.test.yml up -d
    pytest tests/test_sip_integration.py -v
    docker-compose -f docker-compose.test.yml down
"""

import time

import pytest

from rotary_phone.sip import CallState, PyVoIPClient

pytestmark = pytest.mark.integration


@pytest.fixture
def sip_server_config():
    """SIP server configuration for testing against Docker SIPp container."""
    return {
        "server": "127.0.0.1",
        "port": 5060,
        "username": "testuser",
        "password": "testpass",
    }


def test_registration(sip_server_config):
    """Test SIP registration against SIPp server."""
    client = PyVoIPClient()

    try:
        # Register
        account_uri = f"{sip_server_config['server']}:{sip_server_config['port']}"
        client.register(
            account_uri=account_uri,
            username=sip_server_config["username"],
            password=sip_server_config["password"],
        )

        # Wait for registration
        time.sleep(1)

        # Check state
        assert client.get_call_state() in (CallState.REGISTERING, CallState.REGISTERED)

        # Clean up
        client.unregister()
        time.sleep(0.5)

        assert client.get_call_state() == CallState.IDLE

    finally:
        # Ensure cleanup
        try:
            client.unregister()
        except Exception:  # pylint: disable=broad-except
            pass


def test_outgoing_call(sip_server_config):
    """Test making an outgoing call to SIPp server."""
    events = []

    def on_answered():
        events.append("answered")

    def on_ended():
        events.append("ended")

    client = PyVoIPClient(on_call_answered=on_answered, on_call_ended=on_ended)

    try:
        # Register
        account_uri = f"{sip_server_config['server']}:{sip_server_config['port']}"
        client.register(
            account_uri=account_uri,
            username=sip_server_config["username"],
            password=sip_server_config["password"],
        )

        # Wait for registration
        time.sleep(1)
        assert client.get_call_state() in (CallState.REGISTERING, CallState.REGISTERED)

        # Make call
        client.make_call("5551234567")

        # Wait for call to progress
        time.sleep(0.5)
        assert client.get_call_state() in (CallState.CALLING, CallState.CONNECTED)

        # Wait for answer (SIPp scenario answers after 1 second)
        time.sleep(2)

        # Should be connected and callback triggered
        assert client.get_call_state() == CallState.CONNECTED
        assert "answered" in events

        # Hang up
        client.hangup()
        time.sleep(0.5)

        # Should be back to registered
        assert client.get_call_state() == CallState.REGISTERED
        assert "ended" in events

        # Clean up
        client.unregister()

    finally:
        # Ensure cleanup
        try:
            client.unregister()
        except Exception:  # pylint: disable=broad-except
            pass


def test_call_flow_complete(sip_server_config):
    """Test complete call flow: register -> call -> connected -> hangup -> unregister."""
    events = []

    def on_answered():
        events.append(("answered", time.time()))

    def on_ended():
        events.append(("ended", time.time()))

    client = PyVoIPClient(on_call_answered=on_answered, on_call_ended=on_ended)

    try:
        # 1. Register
        account_uri = f"{sip_server_config['server']}:{sip_server_config['port']}"
        client.register(
            account_uri=account_uri,
            username=sip_server_config["username"],
            password=sip_server_config["password"],
        )
        time.sleep(1)
        assert client.get_call_state() in (CallState.REGISTERING, CallState.REGISTERED)

        # 2. Make call
        client.make_call("5551234567")
        time.sleep(0.5)
        assert client.get_call_state() in (CallState.CALLING, CallState.CONNECTED)

        # 3. Wait for connected
        time.sleep(2)
        assert client.get_call_state() == CallState.CONNECTED
        assert len(events) >= 1
        assert events[0][0] == "answered"

        # 4. Hang up
        client.hangup()
        time.sleep(0.5)
        assert client.get_call_state() == CallState.REGISTERED
        assert len(events) == 2
        assert events[1][0] == "ended"

        # 5. Unregister
        client.unregister()
        time.sleep(0.5)
        assert client.get_call_state() == CallState.IDLE

    finally:
        try:
            client.unregister()
        except Exception:  # pylint: disable=broad-except
            pass
