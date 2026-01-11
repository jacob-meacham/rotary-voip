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
    """Test making an outgoing call (will fail without destination)."""
    print("\n" + "=" * 60)
    print("Outgoing Call Test (No Destination)")
    print("=" * 60)
    print("\nNOTE: This test registers and prepares to make a call,")
    print("but does not actually dial (no destination configured).")
    print()

    config = get_sip_config()

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

        # Note: Not actually making a call since we don't have a destination
        print("\n✓ Ready to make calls (stopping here)")
        print("  To test actual calls, modify this script with a destination number")

        # Unregister
        client.unregister()
        return True

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
