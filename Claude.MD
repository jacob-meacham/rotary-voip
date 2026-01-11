# Claude Code Instructions

This file contains instructions and guidelines for Claude Code when working on this project.

## Test Suites

This project has three test suites with different purposes and costs:

### 1. Standard Unit & E2E Tests (`uv run pytest`)
**When to run:** Anytime during development

**What it includes:**
- All unit tests (GPIO, dial reader, hook monitor, ringer, SIP client, call manager)
- `tests/test_integration_e2e.py` - 6 end-to-end tests with mock components
- Uses MockGPIO + InMemorySIPClient (no real hardware or SIP calls)

**Cost:** Free, fast (~5 seconds)

**Permission:** Run freely without asking

```bash
uv run pytest                                    # All tests
uv run pytest tests/test_integration_e2e.py -v  # Just E2E
```

---

### 2. Docker SIPp Integration Tests (`./run_integration_tests.sh`)
**When to run:** When verifying SIP protocol compliance

**What it includes:**
- Starts Docker container with SIPp (SIP testing tool)
- `tests/test_sip_integration.py` - Protocol-level SIP tests
- Tests PyVoIPClient against simulated SIP server

**Cost:** Free, requires Docker (~10 seconds)

**Permission:** Run freely without asking

```bash
./run_integration_tests.sh
```

---

### 3. Real SIP Provider Tests (`python -m tests.manual.test_real_sip`)
**When to run:** Manual verification only, before production deployment

**What it includes:**
- Tests against **real** SIP provider (voip.ms)
- Makes **actual** phone calls to TEST_DESTINATION
- Tests registration, outgoing calls, answer detection

**Cost:** **Uses real SIP credits and makes actual phone calls**

**Permission:** ⚠️ **ALWAYS ASK USER BEFORE RUNNING** ⚠️

**Setup required:**
- User must configure `.env.test` with voip.ms credentials
- User must set TEST_DESTINATION to a number they control

```bash
# DO NOT run without explicit user permission!
python -m tests.manual.test_real_sip
```

---

## Quick Reference for Claude

```bash
# Safe to run anytime
uv run pytest
./run_integration_tests.sh

# MUST ASK FIRST (costs money, makes real calls)
python -m tests.manual.test_real_sip
```
