# Next Steps - Rotary Phone VoIP Project

## Current Status
✅ **Code Cleanup Complete**: All quality improvements done

### Cleanup Tasks (Completed):
- [x] Remove dead FileNotFoundError handler
- [x] Fix threading issue in MockGPIO
- [x] Convert Pins class to Enum
- [x] Add type specificity to ConfigManager.get()
- [x] Rename GPIO → PhoneHardware in public API
- [x] Fix all pylint errors (10.00/10 score)
- [x] Ensure full mypy type coverage (0 errors)
- [x] Fix logging to use lazy % formatting
- [x] Add proper exception chaining with `from`
- [x] Remove unnecessary pass statements
- [x] Add encoding to file opens

---

✅ **Phase 5 Complete**: HookMonitor with debouncing is working

Latest commits:
- `81d174e` - Add GPIO abstraction layer for hardware independence
- `168e05c` - Simplify configuration: remove GPIO pins, rename to allowlist
- `da0ec54` - Add configuration management system
- `b3c0977` - Initial project setup with uv and pytest

What works now:
- YAML-based configuration with simplified structure
- GPIO abstraction (MockGPIO + RealGPIO) for hardware independence
- Pin constants defined (HOOK=17, DIAL_PULSE=27, etc.)
- Full GPIO simulation for testing without hardware
- Edge detection with callbacks
- **DialReader component** - Reads rotary dial pulses and detects digits
  - Counts pulses with timeout-based digit completion
  - Thread-safe pulse handling
  - Proper mapping (1 pulse = 1, 10 pulses = 0)
- **HookMonitor component** - Detects phone on-hook/off-hook state changes
  - Debouncing to prevent spurious state changes from switch bounce
  - State verification after debounce period
  - Callbacks for pick-up and hang-up events
  - Thread-safe with Timer-based debouncing
- **Automated test harness** - Simulation helpers for testing real logic
  - simulate_pulse() - Generate single pulse
  - simulate_dial_digit() - Dial digit with proper timing
  - simulate_dial_number() - Dial full phone numbers
  - simulate_pick_up() / simulate_hang_up() - Hook state changes
  - simulate_hook_bounce() - Mechanical switch bounce
- 52 tests all passing (13 config + 11 dial reader + 12 hook monitor + 16 GPIO)

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

## Immediate Next Steps - Phase 1: Foundation

### Goal
Set up modern Python development environment with uv and testing framework for the core phone controller.

### Tasks

#### 1.1 Initialize uv Project
- [ ] Initialize uv project with `uv init`
- [ ] Configure `pyproject.toml` with project metadata
- [ ] Set up Python version (3.11+)
- [ ] Add core dependencies (PyYAML, pytest)
- [ ] Add dev dependencies (black, mypy, pylint)
- [ ] Note: GPIO libraries will be optional (mock-able for dev)

#### 1.2 Basic Project Structure
Create only what we need to start:
```
src/
  rotary_phone/
    __init__.py
    main.py          # Entry point for phone controller
tests/
  __init__.py
  test_main.py       # Basic test
.gitignore
pyproject.toml
README.md
```

#### 1.3 Hello World Phone Controller
- [ ] Create basic main.py that prints "Phone controller starting..."
- [ ] Add command-line argument parsing (--debug, --mock-gpio)
- [ ] Add proper logging setup
- [ ] Make it runnable with `uv run python -m rotary_phone.main`

#### 1.4 Test Framework
- [ ] Configure pytest in `pyproject.toml`
- [ ] Create first test in `tests/test_main.py`
- [ ] Verify tests run with `uv run pytest`
- [ ] Add test coverage reporting

#### 1.5 Development Workflow Commands
- [ ] Add commands to `pyproject.toml` for:
  - `uv run phone` - Start phone controller
  - `uv run phone --mock-gpio` - Start with mock hardware
  - `uv run test` - Run tests
  - `uv run test-watch` - Run tests in watch mode
  - `uv run format` - Format code with black
  - `uv run lint` - Run linter
  - `uv run typecheck` - Run mypy

#### 1.6 Basic .gitignore
- [ ] Create `.gitignore` for Python, uv, IDE files
- [ ] Ignore config.yaml (contains secrets)
- [ ] Ignore *.log files

#### 1.7 First Commit
- [ ] Commit foundation: "Initial project setup with uv and pytest"

### Success Criteria
- [ ] `uv run phone` starts the phone controller (even if it does nothing yet)
- [ ] `uv run test` runs and passes basic tests
- [ ] Can iterate quickly: change code → test → commit
- [ ] Foundation ready for building hardware abstractions

---

## Next Phases (Core Phone Controller)

After foundation, we'll build incrementally:

### Phase 2: Configuration Management
- [ ] ConfigManager class
- [ ] Load/validate YAML config
- [ ] Tests for config loading
- [ ] Commit: "Add configuration management"

### Phase 3: GPIO Abstraction Layer
- [ ] Abstract GPIO interface
- [ ] Mock GPIO implementation
- [ ] Auto-detect real vs mock
- [ ] Tests for both modes
- [ ] Commit: "Add GPIO abstraction layer"

### Phase 4: Test Harness
- [ ] Interactive CLI for testing without hardware
- [ ] Simulate dial pulses, hook states
- [ ] Automated test scenarios
- [ ] Commit: "Add interactive test harness"

### Phase 5: Dial Reader
- [ ] DialReader class with pulse counting
- [ ] Background thread for timeout detection
- [ ] Tests with mock GPIO
- [ ] Test in harness
- [ ] Commit: "Add dial reader component"

### Phase 6: Hook Monitor
- [ ] HookMonitor class
- [ ] Debouncing logic
- [ ] Tests
- [ ] Commit: "Add hook monitor component"

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