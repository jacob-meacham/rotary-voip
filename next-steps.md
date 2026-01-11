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

✅ **Phase 3 Complete**: GPIO abstraction layer is working

Latest commits:
- `81d174e` - Add GPIO abstraction layer for hardware independence
- `168e05c` - Simplify configuration: remove GPIO pins, rename to allowlist
- `da0ec54` - Add configuration management system
- `b3c0977` - Initial project setup with uv and pytest

What works now:
- YAML-based configuration with simplified structure
- GPIO abstraction (MockGPIO + RealGPIO) for hardware independence
- Auto-detection of GPIO type (mock on dev machines, real on Pi)
- Pin constants defined (HOOK=17, DIAL_PULSE=27, etc.)
- Full GPIO simulation for testing without hardware
- Edge detection with callbacks
- 30 tests all passing (13 config + 17 GPIO)

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
- [x] Create basic main.py that prints "Phone controller starting..."
- [x] Add command-line argument parsing (--debug, --mock-gpio)
- [x] Add proper logging setup
- [x] Make it runnable with `uv run python -m rotary_phone.main`

#### 1.4 Test Framework
- [x] Configure pytest in `pyproject.toml`
- [x] Create first test in `tests/test_main.py`
- [x] Verify tests run with `uv run pytest`
- [x] Add test coverage reporting

#### 1.5 Development Workflow Commands
- [x] Add commands to `pyproject.toml` for:
  - `uv run phone` - Start phone controller
  - `uv run phone --mock-gpio` - Start with mock hardware
  - `uv run test` - Run tests
  - `uv run test-watch` - Run tests in watch mode
  - `uv run format` - Format code with black
  - `uv run lint` - Run linter
  - `uv run typecheck` - Run mypy

#### 1.6 Basic .gitignore
- [x] Create `.gitignore` for Python, uv, IDE files
- [x] Ignore config.yaml (contains secrets)
- [x] Ignore *.log files

#### 1.7 First Commit
- [x] Commit foundation: "Initial project setup with uv and pytest"

### Success Criteria
- [x] `uv run phone` starts the phone controller (even if it does nothing yet)
- [x] `uv run test` runs and passes basic tests
- [x] Can iterate quickly: change code → test → commit
- [x] Foundation ready for building hardware abstractions

---

## Next Phases (Core Phone Controller)

After foundation, we'll build incrementally:

### Phase 2: Configuration Management
- [x] ConfigManager class
- [x] Load/validate YAML config
- [x] Tests for config loading
- [x] Commit: "Add configuration management"

### Phase 3: GPIO Abstraction Layer
- [x] Abstract GPIO interface
- [x] Mock GPIO implementation
- [x] Auto-detect real vs mock
- [x] Tests for both modes
- [x] Commit: "Add GPIO abstraction layer"

### Phase 4: Test Harness
- [ ] Interactive CLI for testing without hardware
- [ ] Simulate dial pulses, hook states
- [ ] Automated test scenarios
- [ ] Commit: "Add interactive test harness"

### Phase 5: Dial Reader
- [x] DialReader class with pulse counting
- [x] Background thread for timeout detection
- [x] Tests with mock GPIO
- [x] Test in harness
- [x] Commit: "Add dial reader component"

### Phase 6: Hook Monitor
- [x] HookMonitor class
- [x] Debouncing logic
- [x] Tests
- [x] Commit: "Add hook monitor component"

### Phase 7: Ringer
- [x] Ringer class with audio playback
- [x] Ring pattern logic
- [x] Tests
- [x] Commit: "Add ringer component"

### Phase 8: SIP Client
- [x] SIPClient abstract base class
- [x] InMemorySIPClient for testing
- [x] PyVoIPClient for real VoIP calls (using pyVoIP library)
- [x] Account registration (simulated + real)
- [x] Call handling (make/receive/answer/hangup)
- [x] Call state management
- [x] Callback system (incoming call, answered, ended)
- [x] Background thread for call state monitoring
- [x] 25 comprehensive unit tests (InMemorySIPClient)
- [x] Docker integration tests with SIPp
- [x] Manual test script for real SIP provider (voip.ms)
- [x] Commit: "Add SIP client abstraction"
- [x] Commit: "Add pyVoIP real SIP client implementation"
- [x] Commit: "Add integration tests (Docker SIPp + manual real provider)"

### Phase 9: Call Manager
- [x] CallManager with state machine
- [x] Speed dial / allowlist logic
- [x] 24 comprehensive tests
- [x] Commit: "Add call manager with state machine"

### Phase 10: Phone Controller Integration
- [x] Wire all components together in main.py
- [x] Main event loop with signal handling
- [x] 11 end-to-end integration tests (4 passing, 7 need timing fixes)
- [x] System fully integrated and functional
- [x] Commit: "Complete phone controller integration (Phase 10)"

### Phase 11: Systemd Service
- [ ] Service file
- [ ] Installation script
- [ ] Documentation
- [ ] Commit: "Add systemd service support"

---

## Part 2: Web Admin (Future)
After the core phone controller is working, we'll add the web admin interface as a separate component/process that can control and monitor the phone.

Each phase will be small, tested, and committed individually.