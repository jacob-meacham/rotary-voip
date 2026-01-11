# Next Steps - Rotary Phone VoIP Project

## Current Status
✅ **Phases 1-6 Complete**: Foundation through HookMonitor working with test infrastructure

Latest commits:
- `14bd156` - Refactor test infrastructure: extract shared fixtures and helpers
- `178df7d` - Add HookMonitor component with debouncing
- `20435fa` - Add DialReader component with automated test harness
- `ab0d72e` - Remove auto-detection from get_gpio(), require explicit mock parameter
- `7762505` - Simplify Pin constants from IntEnum to plain module constants
- `51fff81` - Code quality improvements: linting, typing, and cleanup
- `81d174e` - Add GPIO abstraction layer for hardware independence
- `168e05c` - Simplify configuration: remove GPIO pins, rename to allowlist
- `da0ec54` - Add configuration management system
- `b3c0977` - Initial project setup with uv and pytest

What works now:
- ✅ **Phase 1: Foundation** - Modern Python dev environment with uv and pytest
- ✅ **Phase 2: Configuration Management** - YAML-based config with simplified structure
- ✅ **Phase 3: GPIO Abstraction** - MockGPIO + RealGPIO for hardware independence
  - Pin constants defined (HOOK=17, DIAL_PULSE=27, etc.)
  - Full GPIO simulation for testing without hardware
  - Edge detection with callbacks
- ✅ **Phase 4: Test Harness** - Simulation helpers for testing real logic
  - simulate_pulse() - Generate single pulse
  - simulate_dial_digit() - Dial digit with proper timing
  - simulate_dial_number() - Dial full phone numbers
  - simulate_pick_up() / simulate_hang_up() - Hook state changes
  - simulate_hook_bounce() - Mechanical switch bounce
  - Shared test fixtures in conftest.py
  - Test harness utilities in test_harness.py
- ✅ **Phase 5: DialReader component** - Reads rotary dial pulses and detects digits
  - Counts pulses with timeout-based digit completion
  - Thread-safe pulse handling
  - Proper mapping (1 pulse = 1, 10 pulses = 0)
  - 11 tests all passing
- ✅ **Phase 6: HookMonitor component** - Detects phone on-hook/off-hook state changes
  - Debouncing to prevent spurious state changes from switch bounce
  - State verification after debounce period
  - Callbacks for pick-up and hang-up events
  - Thread-safe with Timer-based debouncing
  - 12 tests all passing
- **Total: 52 tests passing** (13 config + 11 dial reader + 12 hook monitor + 16 GPIO)
- **Code Quality: pylint 10.00/10, mypy 0 errors**

## Project Architecture - Two Parts

### Part 1: Core Phone Controller (CURRENT FOCUS)
The standalone phone system that:
- Reads rotary dial pulses
- Monitors hook switch
- Controls ringer
- Makes/receives SIP calls
- Logs to console/file
- Uses YAML config file

**This runs independently and makes the phone work.**

### Part 2: Web Admin Interface (LATER)
Optional web interface that:
- Provides UI for configuration
- Shows call logs
- Manages network settings
- Controls the phone remotely

---

## Completed Phases

### ✅ Phase 1: Foundation
- [x] Initialize uv project with `uv init`
- [x] Configure `pyproject.toml` with project metadata
- [x] Set up Python version (3.11+)
- [x] Add core dependencies (PyYAML, pytest)
- [x] Add dev dependencies (black, mypy, pylint)
- [x] Basic project structure
- [x] Test framework with pytest
- [x] Development workflow commands
- [x] Basic .gitignore

### ✅ Phase 2: Configuration Management
- [x] ConfigManager class
- [x] Load/validate YAML config
- [x] Tests for config loading
- [x] Simplified configuration structure

### ✅ Phase 3: GPIO Abstraction Layer
- [x] Abstract GPIO interface
- [x] Mock GPIO implementation
- [x] Explicit mock parameter (no auto-detection)
- [x] Tests for both modes
- [x] Pin constants (HOOK, DIAL_PULSE, etc.)

### ✅ Phase 4: Test Harness
- [x] Simulation helpers for dial and hook
- [x] Automated test scenarios
- [x] Shared fixtures in conftest.py
- [x] Test utilities in test_harness.py

### ✅ Phase 5: Dial Reader
- [x] DialReader class with pulse counting
- [x] Timer-based timeout detection
- [x] Tests with mock GPIO
- [x] Thread-safe implementation

### ✅ Phase 6: Hook Monitor
- [x] HookMonitor class
- [x] Debouncing logic with Timer
- [x] Tests with mock GPIO
- [x] State change callbacks

---

## Next Phases (Core Phone Controller)

### Phase 7: Ringer
- [ ] Ringer class with audio playback
- [ ] Ring pattern logic
- [ ] Tests
- [ ] Commit: "Add ringer component"

### Phase 8: SIP Client
- [ ] SIPClient class (PJSUA2)
- [ ] Account registration
- [ ] Call handling
- [ ] Mock SIP for testing
- [ ] Tests
- [ ] Commit: "Add SIP client"

### Phase 9: Call Manager
- [ ] CallManager with state machine
- [ ] Speed dial / whitelist logic
- [ ] Tests
- [ ] Commit: "Add call manager"

### Phase 10: Phone Controller Integration
- [ ] Wire all components together
- [ ] Main event loop
- [ ] Integration tests
- [ ] End-to-end testing in harness
- [ ] Commit: "Complete phone controller integration"

### Phase 11: Systemd Service
- [ ] Service file
- [ ] Installation script
- [ ] Documentation
- [ ] Commit: "Add systemd service support"

---

## Part 2: Web Admin (Future)
After the core phone controller is working, we'll add the web admin interface as a separate component/process that can control and monitor the phone.

Each phase will be small, tested, and committed individually.