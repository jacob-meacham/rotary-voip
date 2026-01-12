# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Rotary Phone VoIP Conversion project that converts vintage rotary phones into battery-powered, WiFi-connected VoIP phones. The system runs on a Raspberry Pi Zero 2 W and provides:

- **Rotary dial input**: Reads pulse dialing and converts to digits
- **VoIP calling**: SIP/VoIP calls over WiFi via providers like VoIP.ms
- **Speed dial**: 2-digit shortcuts for common contacts
- **Number whitelist**: Control which numbers can be dialed
- **Incoming calls**: Rings a speaker when receiving calls
- **Web admin interface**: Modern Python web interface for configuration and call logs
- **WiFi provisioning**: Auto-creates AP when not connected to allow network setup
- **Test harness**: Comprehensive testing framework for all components

## Development Commands

### Testing
```bash
./check.sh
```

### Running the Application
```bash
# Development mode (with debug output)
python -m src.main --debug

# Production mode
python -m src.main

# Run web admin interface only
python -m src.web_admin

# Run with mock hardware (for development on non-Pi systems)
MOCK_GPIO=1 python -m src.main
```

### Linting and Code Quality
```bash
./check.sh

# If needed, format code with black
black src/ tests/

# If needed, check types with mypy
mypy src/

# If needed, run linter
pylint src/

```

## Architecture

### High-Level Component Structure

```
src/
├── main.py                 # Application entry point
├── config/
│   ├── config_manager.py  # Configuration handling (YAML + runtime)
│   └── default_config.yaml
├── hardware/
│   ├── dial_reader.py     # Rotary dial pulse detection
│   ├── hook_monitor.py    # Hook switch state monitoring
│   ├── ringer.py          # Ringer speaker control
│   └── gpio_mock.py       # Mock GPIO for testing
├── voip/
│   ├── sip_client.py      # SIP/VoIP call handling (PJSUA2)
│   └── call_manager.py    # Call state management
├── network/
│   ├── wifi_manager.py    # WiFi connection management
│   └── access_point.py    # AP mode for provisioning
├── web_admin/
│   ├── app.py             # Web server (FastAPI)
│   ├── routes/
│   │   ├── settings.py    # Settings endpoints
│   │   ├── calls.py       # Call log endpoints
│   │   └── network.py     # Network config endpoints
│   ├── static/            # Frontend assets
│   └── templates/         # HTML templates
├── database/
│   ├── models.py          # Call log and settings models
│   └── db.py              # Database connection (SQLite)
└── phone_controller.py    # Main orchestrator

tests/
├── test_harness.py        # Interactive test harness
├── test_dial_reader.py
├── test_hook_monitor.py
├── test_sip_client.py
├── test_call_manager.py
└── fixtures/              # Test fixtures and mocks
```

### Key Architectural Patterns

**Event-Driven Design**: The phone controller uses callbacks and event handlers to coordinate between hardware inputs (dial, hook) and VoIP outputs.

**State Machine**: Call states (idle, dialing, ringing, in_call) are managed centrally to prevent race conditions.

**Dependency Injection**: Hardware components are injected into the controller, allowing for easy mocking in tests.

**Configuration Layers**:
- Default config in YAML
- User overrides in config.yaml
- Runtime state managed separately
- Web admin updates both file and runtime state

### GPIO Pin Assignments (BCM Mode)

| Function | GPIO Pin | Physical Pin | Notes |
|----------|----------|--------------|-------|
| Hook switch | GPIO 17 | Pin 11 | HIGH = on-hook, LOW = off-hook |
| Dial pulse | GPIO 27 | Pin 13 | Pulses LOW for each digit |
| Dial active | GPIO 22 | Pin 15 | LOW while dial rotating (optional) |
| Ringer enable | GPIO 23 | Pin 16 | HIGH to enable ringer amp |
| Low battery | GPIO 24 | Pin 18 | LOW when battery low (optional) |

### VoIP Integration

The system uses PJSUA2 (Python bindings for PJSIP) for SIP functionality:
- **Registration**: Auto-registers with VoIP provider on startup
- **Outbound calls**: Triggered by dial completion
- **Inbound calls**: Triggers ringer, answers on hook pickup
- **Audio routing**: USB audio device for handset mic/speaker

**Call Flow**:
1. User lifts handset → Hook monitor detects off-hook
2. User dials digits → Dial reader accumulates pulses
3. After 2s timeout → Speed dial lookup or whitelist check
4. If allowed → SIP client initiates call
5. Audio flows through USB audio device
6. User hangs up → Call terminated

### Web Admin Interface

Modern Python web framework (FastAPI recommended) serving:
- **Dashboard**: Call statistics, system status
- **Settings**: Speed dial configuration, whitelist management
- **Call Log**: Searchable history with timestamps, duration
- **Network**: WiFi configuration, AP mode toggle
- **System**: Restart service, view logs, battery status

**Security**: Basic auth or session-based auth to prevent unauthorized access.

### Network Provisioning

**Boot Sequence**:
1. Try to connect to configured WiFi (30s timeout)
2. If fails → Start Access Point mode
3. AP serves captive portal for network configuration
4. User selects network and enters password
5. Store credentials and restart in client mode

**AP Details**:
- SSID: `RotaryPhone-XXXX` (last 4 of MAC)
- Password: Configurable, default `rotaryphone`
- IP: `192.168.4.1`
- Web UI on port 80

## Mandatory Development Workflow

### Before Writing Code

1. **Understand Requirements**: If anything is unclear, ask clarifying questions
2. **Create Implementation Plan**: Include:
   - Goal summary
   - Assumptions
   - Affected files/modules
   - Step-by-step approach
   - Considerations (edge cases, risks, alternatives)
3. **Present Plan**: Wait for explicit approval before implementing
4. **Implement**: Only proceed after receiving approval

### After Writing Code

1. **Run Build & Tests**: Ensure all tests pass
   ```bash
   python -m pytest tests/
   ```

2. **Fix Root Issues**: Address root causes, not just symptoms
   ```python
   # Bad: Patching a symptom
   if data is not None and len(data) > 0:
       process(data)

   # Good: Fix the root cause
   def get_data() -> list:
       return fetch_data() or []  # Never return None
   ```

3. **Document Unresolved Issues**: If you can't fix something immediately, document it in `next_steps.md` with:
   - Problem description
   - Steps to reproduce
   - Potential solutions

4. **Commit Changes**: Make focused commits after successful fixes
   ```bash
   git add src/voip/sip_client.py
   git commit -m "Fix SIP registration timeout handling"
   ```

5. **Keep Changes Scoped**: Smallest possible change that fixes the issue. Don't mix multiple changes in one commit.

## Testing Strategy

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

### 3. Real SIP Provider Tests (`python -m tests.manual.test_real_phone`)
**When to run:** Manual verification only, before production deployment

**What it includes:**
- Tests against **real** SIP provider (voip.ms)
- Makes **actual** phone calls
- Tests registration, outgoing calls, answer detection

**Cost:** **Uses real SIP credits and makes actual phone calls**

**Permission:** ⚠️ **ALWAYS ASK USER BEFORE RUNNING** ⚠️

**Setup required:**
- User must configure `.env.test` with voip.ms credentials

```bash
# DO NOT run without explicit user permission!
python -m tests.manual.test_real_phone
```

---

### Quick Reference for Claude

```bash
# Safe to run anytime
uv run pytest
./run_integration_tests.sh

# MUST ASK FIRST (costs money, makes real calls)
python -m tests.manual.test_real_sip
```

---

### Interactive Test Harness

The `tests/manual/test_harness.py` provides an interactive simulator for testing without real hardware:
- **Mock GPIO**: Simulates dial pulses, hook switch states
- **Mock SIP**: Simulates call states without real VoIP
- **Interactive CLI**: Test scenarios manually
- **Real-time status**: View all component states

**Usage**:
```bash
python -m tests.manual.test_harness
```

**Commands:**
- `u` - Pick up phone (hook off)
- `d` - Hang up phone (hook on)
- `0-9` - Dial digit
- `i` - Simulate incoming call
- `a` - Simulate remote party answered
- `e` - Simulate remote party hung up
- `s` - Show status
- `q` - Quit

---

### Unit Tests

- Each hardware component has isolated unit tests
- Use pytest fixtures for common setups
- Mock GPIO and external dependencies
- Test edge cases (rapid dial, hook bounce, network failures)

### Integration Tests

- Test full call flow from dial to hangup
- Test WiFi provisioning flow
- Test web admin API endpoints

## Configuration Management

### Config File Structure (config.yaml)

```yaml
sip:
  server: "seattle.voip.ms"
  username: "123456"
  password: "your_sip_password"

speed_dial:
  "11": "+12065551234"  # Dad
  "12": "+12065555678"  # Mom

whitelist:
  - "+12065551234"
  - "+12065555678"

network:
  wifi_ssid: "YourNetwork"
  wifi_password: "password"
  ap_ssid: "RotaryPhone"
  ap_password: "rotaryphone"

hardware:
  pin_hook: 17
  pin_dial_pulse: 27
  pin_dial_active: 22
  pin_ringer: 23
  pulse_timeout: 0.3
  inter_digit_timeout: 2.0

audio:
  ring_sound: "sounds/ring.wav"
  dial_tone: "sounds/dialtone.wav"

web_admin:
  enabled: true
  port: 8080
  auth_required: true
  username: "admin"
  password_hash: "..."  # bcrypt hash
```

### Runtime Config Updates

When web admin updates config:
1. Validate new values
2. Update config file (YAML)
3. Update runtime state (reload components as needed)
4. Return success/failure to web UI

## Hardware-Specific Notes

### Rotary Dial Timing

The dial reader must handle timing variations:
- **Pulse width**: ~60ms (varies by phone model)
- **Pulse gap**: ~40ms between pulses
- **Inter-digit gap**: ~300-800ms between digits
- **Dial return time**: ~600ms for full rotation

**Tuning**: Adjust `PULSE_TIMEOUT` in config if digits are misread.

### USB Audio Configuration

The Pi must route audio correctly:
```bash
# List audio devices
aplay -l
arecord -l

# Set default device in ~/.asoundrc
pcm.!default {
    type hw
    card 1  # USB audio device
}
```

**PJSUA2 Config**: Set audio device index in SIP client initialization.

## Common Development Tasks

### Adding a New Speed Dial Entry

1. Update `config.yaml` or use web admin
2. No code changes needed (config is reloaded automatically)

### Changing Dial Pulse Timing

1. Edit `hardware.pulse_timeout` in `config.yaml`
2. Restart service or reload config via web admin

### Adding a New Web Admin Page

1. Create route in `src/web_admin/routes/`
2. Add HTML template in `src/web_admin/templates/`
3. Link from main dashboard
4. Add tests in `tests/test_web_admin.py`

### Debugging SIP Issues

1. Enable verbose logging: Set `ep_cfg.logConfig.level = 5` in `sip_client.py`
2. Check registration: `journalctl -u rotary-phone | grep -i registration`
3. Test with linphonec manually to isolate SIP vs. hardware issues

## Dependencies

### Core Python Packages
- `RPi.GPIO`: GPIO control (auto-mocked on non-Pi systems)
- `pjsua2`: SIP/VoIP (requires system package `python3-pjsua2`)
- `PyYAML`: Config file parsing
- `fastapi`: Web framework
- `uvicorn`: ASGI server for FastAPI
- `sqlalchemy`: Database ORM for call logs
- `pytest`: Testing framework
- `black`: Code formatter
- `mypy`: Type checking
- `uv`: Environment management

### System Packages (Raspberry Pi)
```bash
sudo apt install python3-pjsua2 alsa-utils pulseaudio hostapd dnsmasq
```

## Security Considerations

- **Web Admin Auth**: Always enable authentication in production
- **SIP Credentials**: Store in config file, never commit to git
- **Whitelist**: Default to restrictive (kids' phones should have limited access)
- **AP Mode Password**: Change default password on first boot
- **HTTPS**: Consider adding TLS for web admin (use Let's Encrypt or self-signed cert)

## Known Limitations

- **Pulse Dialing Only**: Tone (DTMF) dialing not supported

## Future Enhancements

- Voice mail indicator (LED when messages waiting)
- Caller ID display (small OLED screen)
- Bluetooth speaker support
- Multiple phone support (extension system)
- Call recording/archiving
- Integration with smart home systems