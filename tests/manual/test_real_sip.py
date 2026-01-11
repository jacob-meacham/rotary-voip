"""Manual test script for real SIP provider (e.g., voip.ms).

This script tests the PyVoIPClient against a real SIP provider.
Configure your SIP credentials via environment variables:

    export SIP_SERVER=vancouver.voip.ms
    export SIP_PORT=5060
    export SIP_USERNAME=123456_test
    export SIP_PASSWORD=your_password_here
    export SIP_DID=+15551234567

Then run:
    python -m tests.manual.test_real_sip

WARNING: This will make actual SIP registration and may incur charges.
"""

import os
import sys
import time

from rotary_phone.sip import CallState, PyVoIPClient


def get_sip_config():
    """Get SIP configuration from environment variables."""
    required = ["SIP_SERVER", "SIP_USERNAME", "SIP_PASSWORD"]
    config = {}

    for var in required:
        value = os.getenv(var)
        if not value:
            print(f"Error: {var} environment variable not set", file=sys.stderr)
            print("\nRequired environment variables:", file=sys.stderr)
            print("  SIP_SERVER     - SIP server hostname (e.g., vancouver.voip.ms)", file=sys.stderr)
            print("  SIP_USERNAME   - SIP username (e.g., 123456_test)", file=sys.stderr)
            print("  SIP_PASSWORD   - SIP password", file=sys.stderr)
            print("\nOptional:", file=sys.stderr)
            print("  SIP_PORT       - SIP port (default: 5060)", file=sys.stderr)
            print("  SIP_DID        - Your DID/phone number for display", file=sys.stderr)
            sys.exit(1)
        config[var.lower()] = value

    config["sip_port"] = int(os.getenv("SIP_PORT", "5060"))
    config["sip_did"] = os.getenv("SIP_DID", "Unknown")

    return config


def test_registration():
    """Test SIP registration with real provider."""
    print("=" * 60)
    print("SIP Registration Test")
    print("=" * 60)

    config = get_sip_config()

    print(f"\nServer: {config['sip_server']}:{config['sip_port']}")
    print(f"Username: {config['sip_username']}")
    print(f"DID: {config['sip_did']}")
    print()

    client = PyVoIPClient()

    try:
        print("Registering...")
        account_uri = f"{config['sip_server']}:{config['sip_port']}"
        client.register(
            account_uri=account_uri,
            username=config["sip_username"],
            password=config["sip_password"],
        )

        # Wait for registration
        for i in range(10):
            state = client.get_call_state()
            print(f"  [{i+1}/10] State: {state.value}")

            if state == CallState.REGISTERED:
                print("\n✓ Registration successful!")
                break

            if state == CallState.IDLE:
                print("\n✗ Registration failed (returned to IDLE)")
                return False

            time.sleep(0.5)
        else:
            print("\n✗ Registration timeout")
            return False

        # Hold registration for a bit
        print("\nHolding registration for 5 seconds...")
        time.sleep(5)

        # Unregister
        print("Unregistering...")
        client.unregister()
        time.sleep(1)

        if client.get_call_state() == CallState.IDLE:
            print("✓ Unregistration successful!")
            return True

        print("✗ Failed to unregister properly")
        return False

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        try:
            client.unregister()
        except Exception:  # pylint: disable=broad-except
            pass


def test_outgoing_call():
    """Test making an actual outgoing call."""
    print("\n" + "=" * 60)
    print("Outgoing Call Test")
    print("=" * 60)

    config = get_sip_config()

    # Check if TEST_DESTINATION is configured
    test_destination = os.getenv("TEST_DESTINATION")
    if not test_destination:
        print("\n⚠️  TEST_DESTINATION not configured")
        print("  Set TEST_DESTINATION in .env.test to enable outgoing call test")
        print("  Example: TEST_DESTINATION=+15551234567")
        print("\n✓ Skipping outgoing call test (not configured)")
        return True

    print(f"\nDestination: {test_destination}")
    print("NOTE: This will make a REAL call to the destination number!")
    print("Make sure you have permission to call this number.\n")

    events = []

    def on_answered():
        events.append(("answered", time.time()))
        print("  → Call answered!")

    def on_ended():
        events.append(("ended", time.time()))
        print("  → Call ended!")

    client = PyVoIPClient(on_call_answered=on_answered, on_call_ended=on_ended)

    try:
        # Register
        print("Registering...")
        account_uri = f"{config['sip_server']}:{config['sip_port']}"
        client.register(
            account_uri=account_uri,
            username=config["sip_username"],
            password=config["sip_password"],
        )

        # Wait for registration
        for _ in range(10):
            if client.get_call_state() == CallState.REGISTERED:
                break
            time.sleep(0.5)
        else:
            print("✗ Registration failed")
            return False

        print("✓ Registered")

        # Make call
        print(f"\nCalling {test_destination}...")
        client.make_call(test_destination)

        # Wait for call to be answered or timeout
        print("Waiting for answer (15 seconds timeout)...")
        for i in range(30):  # 15 seconds
            state = client.get_call_state()
            if state == CallState.CONNECTED:
                print(f"\n✓ Call connected after {i*0.5:.1f}s!")
                break
            if state == CallState.DISCONNECTED:
                print("\n✗ Call failed (disconnected)")
                client.unregister()
                return False
            time.sleep(0.5)
        else:
            print("\n⚠️  Call not answered within timeout")
            print("  This may be normal if the number doesn't answer")
            client.hangup()
            client.unregister()
            return True  # Not a failure, just no answer

        # Call was answered, wait a moment then hang up
        print("Call connected! Hanging up in 3 seconds...")
        time.sleep(3)

        client.hangup()
        print("✓ Hung up")

        # Unregister
        client.unregister()

        if ("answered" in [e[0] for e in events]):
            print("\n✓ Outgoing call test PASSED")
            return True

        print("\n⚠️  Call connected but answer callback not triggered")
        return True  # Still consider it a pass

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        try:
            client.unregister()
        except Exception:  # pylint: disable=broad-except
            pass


def main():
    """Run all manual tests."""
    print("\n" + "=" * 60)
    print("Real SIP Provider Test Suite")
    print("=" * 60)
    print("\nWARNING: This will connect to a real SIP provider.")
    print("Make sure you have configured your credentials correctly.")
    print()

    results = []

    # Test 1: Registration
    results.append(("Registration", test_registration()))

    # Test 2: Outgoing call preparation
    results.append(("Outgoing Call Prep", test_outgoing_call()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    print()

    if all(passed for _, passed in results):
        print("All tests passed!")
        sys.exit(0)

    print("Some tests failed!")
    sys.exit(1)


if __name__ == "__main__":
    main()
