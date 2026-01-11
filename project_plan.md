# Rotary Phone VoIP Project - Implementation Plan

## Project Goal
Build a complete rotary phone VoIP system with:
- Rotary dial and hook switch hardware interface
- SIP/VoIP calling functionality
- Web-based admin interface for configuration and call logs
- WiFi provisioning via Access Point mode
- Comprehensive test harness for development without hardware

## Assumptions
- Target platform: Raspberry Pi Zero 2 W (but code should work on any Linux system with mock mode)
- Python 3.9+ available
- Development will use FastAPI for modern web framework
- SQLite for call log database
- PJSUA2 for SIP functionality (with fallback to linphone)
- GPIO operations will be abstracted for testing

## Implementation Phases

### Phase 1: Project Foundation
**Goal**: Set up project structure, dependencies, and development environment

#### 1.1 Project Structure Setup
Create the following directory structure:
```
rotary-voip/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── config_manager.py
│   │   └── default_config.yaml
│   ├── hardware/
│   │   ├── __init__.py
│   │   ├── gpio_abstraction.py
│   │   ├── dial_reader.py
│   │   ├── hook_monitor.py
│   │   └── ringer.py
│   ├── voip/
│   │   ├── __init__.py
│   │   ├── sip_client.py
│   │   └── call_manager.py
│   ├── network/
│   │   ├── __init__.py
│   │   ├── wifi_manager.py
│   │   └── access_point.py
│   ├── web_admin/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── settings.py
│   │   │   ├── calls.py
│   │   │   └── network.py
│   │   ├── static/
│   │   │   ├── css/
│   │   │   ├── js/
│   │   │   └── favicon.ico
│   │   └── templates/
│   │       ├── base.html
│   │       ├── dashboard.html
│   │       ├── settings.html
│   │       ├── calls.html
│   │       └── network.html
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── db.py
│   └── phone_controller.py
├── tests/
│   ├── __init__.py
│   ├── test_harness.py
│   ├── test_dial_reader.py
│   ├── test_hook_monitor.py
│   ├── test_ringer.py
│   ├── test_sip_client.py
│   ├── test_call_manager.py
│   ├── test_phone_controller.py
│   ├── test_web_admin.py
│   └── fixtures/
│       ├── __init__.py
│       └── mock_hardware.py
├── sounds/
│   ├── ring.wav
│   ├── dialtone.wav
│   ├── busy.wav
│   └── error.wav
├── config.yaml
├── requirements.txt
├── requirements-dev.txt
├── setup.py
├── pytest.ini
├── .gitignore
├── README.md
├── CLAUDE.md
└── next-steps.md
```

#### 1.2 Dependencies (requirements.txt)
```
PyYAML>=6.0
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6
jinja2>=3.1.2
sqlalchemy>=2.0.0
bcrypt>=4.1.0
python-dotenv>=1.0.0
```

#### 1.3 Development Dependencies (requirements-dev.txt)
```
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-asyncio>=0.21.0
black>=23.10.0
mypy>=1.6.0
pylint>=3.0.0
httpx>=0.25.0  # for FastAPI testing
```

#### 1.4 Configuration Files
- `.gitignore`: Python, IDE, secrets
- `pytest.ini`: Test configuration
- `setup.py`: Package setup for development install

**Deliverables**:
- [ ] Complete directory structure
- [ ] All dependencies listed
- [ ] Basic configuration files created

---

### Phase 2: Configuration Management
**Goal**: Create flexible configuration system that supports YAML files and runtime updates

#### 2.1 Config Manager (`src/config/config_manager.py`)
- Load default config from YAML
- Load user config with overrides
- Validate configuration values
- Provide type-safe config access
- Support runtime updates
- Merge configs properly

#### 2.2 Default Config (`src/config/default_config.yaml`)
Complete config with all sections:
- SIP settings (server, username, password)
- Speed dial mappings
- Whitelist
- Network settings (WiFi, AP mode)
- Hardware pin assignments
- Timing constants
- Audio file paths
- Web admin settings

#### 2.3 Config Tests (`tests/test_config_manager.py`)
- Test config loading
- Test validation
- Test merging behavior
- Test runtime updates

**Deliverables**:
- [ ] ConfigManager class with full functionality
- [ ] Default configuration file
- [ ] Unit tests passing

---

### Phase 3: Hardware Abstraction Layer
**Goal**: Create GPIO abstraction that works with real hardware AND mocks for testing

#### 3.1 GPIO Abstraction (`src/hardware/gpio_abstraction.py`)
- Abstract interface for GPIO operations
- Real implementation using RPi.GPIO
- Mock implementation for development/testing
- Auto-detect platform and use appropriate implementation
- Support for `MOCK_GPIO=1` environment variable

#### 3.2 Mock Hardware (`tests/fixtures/mock_hardware.py`)
- MockGPIO class that simulates pin states
- Event simulation (pulse sequences, hook state changes)
- Thread-safe state management
- Methods to inject test events

**Deliverables**:
- [ ] GPIO abstraction layer
- [ ] Mock GPIO implementation
- [ ] Tests for both real and mock modes

---

### Phase 4: Test Harness
**Goal**: Create interactive test harness for development without hardware

#### 4.1 Test Harness (`tests/test_harness.py`)
Interactive CLI tool with:
- Command menu for actions:
  - Simulate dial digit
  - Toggle hook switch
  - Trigger incoming call
  - View current state
  - Run automated scenario
- Real-time state display
- Automated test scenarios:
  - Basic call flow
  - Speed dial
  - Whitelist enforcement
  - Hook bouncing
  - Rapid dialing
- Integration with mock hardware

#### 4.2 Test Scenarios
Pre-defined scenarios:
1. **basic_call**: Dial 11, connect, talk, hangup
2. **speed_dial**: Test all speed dial entries
3. **whitelist_allow**: Dial whitelisted number
4. **whitelist_deny**: Dial non-whitelisted number
5. **incoming_call**: Receive call, answer, hangup
6. **hook_bounce**: Test debouncing
7. **rapid_dial**: Stress test pulse counting

**Deliverables**:
- [ ] Interactive test harness working
- [ ] All test scenarios implemented
- [ ] Documentation for using test harness

---

### Phase 5: Hardware Components
**Goal**: Implement dial reader, hook monitor, and ringer with full testing

#### 5.1 Dial Reader (`src/hardware/dial_reader.py`)
- DialReader class
- Background thread for pulse timeout detection
- Thread-safe pulse counting
- Callback on digit complete
- Configurable timing constants
- Proper cleanup on shutdown

#### 5.2 Hook Monitor (`src/hardware/hook_monitor.py`)
- HookMonitor class
- Edge detection with debouncing
- Callbacks for pickup and hangup
- Current state tracking

#### 5.3 Ringer (`src/hardware/ringer.py`)
- Ringer class
- Ring pattern loop (ring/pause cycles)
- GPIO amp control
- Audio playback via aplay or similar
- Start/stop methods
- Background thread management

#### 5.4 Unit Tests
- `tests/test_dial_reader.py`: Test pulse counting, timing, edge cases
- `tests/test_hook_monitor.py`: Test state changes, debouncing
- `tests/test_ringer.py`: Test ring patterns, control

**Deliverables**:
- [ ] DialReader fully implemented and tested
- [ ] HookMonitor fully implemented and tested
- [ ] Ringer fully implemented and tested
- [ ] All unit tests passing

---

### Phase 6: VoIP/SIP Layer
**Goal**: Implement SIP client and call management

#### 6.1 SIP Client (`src/voip/sip_client.py`)
- SIPClient class using PJSUA2
- Account registration
- Outbound call initiation
- Inbound call handling
- Call state callbacks
- Audio device configuration
- Fallback to linphone if PJSUA2 unavailable
- Error handling and reconnection logic

#### 6.2 Call Manager (`src/voip/call_manager.py`)
- CallManager class
- Call state machine (idle, dialing, ringing, connected, disconnected)
- Number validation (speed dial lookup, whitelist check)
- Call logging
- Integration with SIP client

#### 6.3 Mock SIP for Testing (`tests/fixtures/mock_sip.py`)
- MockSIPClient that simulates SIP without network
- Controllable call states
- Simulate successful/failed calls
- Simulate incoming calls

#### 6.4 Unit Tests
- `tests/test_sip_client.py`: Test registration, calls, error handling
- `tests/test_call_manager.py`: Test state machine, validation

**Deliverables**:
- [ ] SIP client implemented with PJSUA2
- [ ] Call manager with state machine
- [ ] Mock SIP client for testing
- [ ] Unit tests passing

---

### Phase 7: Phone Controller
**Goal**: Main orchestrator that coordinates all components

#### 7.1 Phone Controller (`src/phone_controller.py`)
- RotaryPhoneController class
- Initialize all components (dial, hook, ringer, SIP)
- Handle dial digit events
- Handle hook events
- Coordinate call flow:
  - Off-hook → ready to dial
  - Digits accumulated → check speed dial/whitelist → place call
  - Incoming call → start ringer → answer on pickup
  - On-hook → hangup call, stop ringer
- Dial timeout handling
- State management
- Logging

#### 7.2 Integration Tests
- `tests/test_phone_controller.py`: Full call flow scenarios
- Test with mock hardware and mock SIP
- Test all state transitions
- Test error conditions

**Deliverables**:
- [ ] Phone controller implemented
- [ ] Integration tests passing
- [ ] End-to-end call flows working in test harness

---

### Phase 8: Database Layer
**Goal**: Call logging and persistent storage

#### 8.1 Database Models (`src/database/models.py`)
- SQLAlchemy models:
  - CallLog: timestamp, direction, number, duration, status
  - ConfigHistory: track config changes
- Indexes for efficient queries

#### 8.2 Database Manager (`src/database/db.py`)
- Database connection management
- CRUD operations for call logs
- Query methods (recent calls, call by number, date range)
- Migration support

#### 8.3 Integration with Call Manager
- Log call start, end, duration
- Log call direction (inbound/outbound)
- Log call status (completed, missed, failed)

**Deliverables**:
- [ ] Database models defined
- [ ] Database manager implemented
- [ ] Call logging integrated
- [ ] Tests for database operations

---

### Phase 9: Network Management
**Goal**: WiFi connection and AP provisioning

#### 9.1 WiFi Manager (`src/network/wifi_manager.py`)
- WiFiManager class
- Connect to configured network
- Check connection status
- Scan for available networks
- Save network credentials
- Handle connection failures

#### 9.2 Access Point Mode (`src/network/access_point.py`)
- AccessPoint class
- Start AP mode with hostapd
- Configure dnsmasq for DHCP
- Captive portal detection
- Stop AP and return to client mode

#### 9.3 Boot-time Network Logic (`src/main.py`)
- On startup:
  1. Try to connect to configured WiFi (30s timeout)
  2. If fails → start AP mode
  3. Wait for configuration via web interface
  4. Switch to client mode with new credentials

#### 9.4 Network Configuration Files
- Template for hostapd.conf
- Template for dnsmasq.conf
- Scripts for starting/stopping AP mode

**Considerations**:
- Root permissions needed for hostapd/dnsmasq
- May need to run as systemd service
- Handle race conditions during network switching

**Deliverables**:
- [ ] WiFi manager implemented
- [ ] AP mode implemented
- [ ] Boot-time provisioning flow working
- [ ] Network switching tested

---

### Phase 10: Web Admin Interface
**Goal**: Modern web UI for configuration and monitoring

#### 10.1 FastAPI App (`src/web_admin/app.py`)
- FastAPI application setup
- Static file serving
- Template rendering with Jinja2
- Basic authentication middleware
- CORS configuration
- Error handlers

#### 10.2 API Routes

**Settings Routes** (`src/web_admin/routes/settings.py`):
- GET `/api/settings` - Get current config
- PUT `/api/settings/sip` - Update SIP settings
- GET `/api/settings/speed-dial` - Get speed dials
- POST `/api/settings/speed-dial` - Add speed dial
- DELETE `/api/settings/speed-dial/{code}` - Remove speed dial
- GET `/api/settings/whitelist` - Get whitelist
- POST `/api/settings/whitelist` - Add to whitelist
- DELETE `/api/settings/whitelist/{number}` - Remove from whitelist

**Call Routes** (`src/web_admin/routes/calls.py`):
- GET `/api/calls` - Get call log (with pagination, filters)
- GET `/api/calls/{id}` - Get specific call
- DELETE `/api/calls/{id}` - Delete call record
- GET `/api/calls/stats` - Get call statistics

**Network Routes** (`src/web_admin/routes/network.py`):
- GET `/api/network/status` - Current network status
- GET `/api/network/scan` - Scan for WiFi networks
- POST `/api/network/connect` - Connect to network
- POST `/api/network/ap/start` - Start AP mode
- POST `/api/network/ap/stop` - Stop AP mode

**System Routes** (`src/web_admin/routes/system.py`):
- GET `/api/system/status` - System status (CPU, memory, uptime)
- GET `/api/system/logs` - Recent logs
- POST `/api/system/restart` - Restart service
- GET `/api/system/battery` - Battery status

#### 10.3 Frontend Templates

**Dashboard** (`templates/dashboard.html`):
- Call statistics (today, week, month)
- Recent calls table
- System status widgets
- Quick actions

**Settings** (`templates/settings.html`):
- SIP configuration form
- Speed dial management table
- Whitelist management table
- Audio settings
- Hardware settings

**Call Log** (`templates/calls.html`):
- Searchable/filterable call log
- Export to CSV
- Call details modal

**Network** (`templates/network.html`):
- Current connection status
- Available networks list
- Connect form
- AP mode toggle

#### 10.4 Frontend Assets
- Modern CSS framework (Bootstrap or Tailwind)
- JavaScript for interactive features
- AJAX calls to API endpoints
- Real-time updates (optional: WebSocket for live status)

#### 10.5 Web Admin Tests
- `tests/test_web_admin.py`: Test all API endpoints
- Test authentication
- Test config updates
- Test call log queries

**Deliverables**:
- [ ] FastAPI app with all routes
- [ ] All HTML templates created
- [ ] Frontend styled and functional
- [ ] API tests passing
- [ ] Web admin accessible and working

---

### Phase 11: Main Application
**Goal**: Application entry point and service setup

#### 11.1 Main Entry Point (`src/main.py`)
- Parse command-line arguments (--debug, --mock-gpio)
- Initialize logging
- Load configuration
- Network provisioning logic
- Start web admin server (background thread)
- Initialize phone controller
- Run main loop
- Handle signals (SIGTERM, SIGINT)
- Cleanup on shutdown

#### 11.2 Systemd Service
Create `/etc/systemd/system/rotary-phone.service`:
- Service configuration
- Auto-restart on failure
- Logging to journald
- Network dependency

#### 11.3 Installation Script
Create `install.sh`:
- Install system dependencies
- Create Python virtual environment
- Install Python packages
- Create systemd service
- Set up audio configuration
- Create initial config file

**Deliverables**:
- [ ] Main application working
- [ ] Systemd service configured
- [ ] Installation script tested
- [ ] Full system integration working

---

### Phase 12: Audio Assets
**Goal**: Create or source audio files for phone tones

#### 12.1 Required Audio Files
- `sounds/ring.wav` - Ring tone
- `sounds/dialtone.wav` - Dial tone (350+440 Hz)
- `sounds/busy.wav` - Busy signal
- `sounds/error.wav` - Error tone

#### 12.2 Audio Generation
- Use Python library (e.g., pydub) to generate tones
- Or source from free audio libraries
- Ensure correct format (WAV, mono, appropriate sample rate)

**Deliverables**:
- [ ] All audio files created
- [ ] Audio files tested with aplay

---

### Phase 13: Documentation
**Goal**: Complete documentation for users and developers

#### 13.1 README.md
- Project overview
- Features list
- Quick start guide
- Installation instructions
- Basic usage
- Links to other docs

#### 13.2 Hardware Setup Guide
- GPIO wiring diagrams
- Bill of materials
- Assembly instructions
- References to rotary-voip-guide.md

#### 13.3 Configuration Guide
- Explain all config options
- VoIP provider setup (VoIP.ms example)
- Speed dial setup
- Whitelist configuration

#### 13.4 Troubleshooting Guide
- Common issues and solutions
- Debug commands
- Log locations
- Testing procedures

**Deliverables**:
- [ ] All documentation complete
- [ ] Documentation reviewed and clear

---

### Phase 14: Testing & Refinement
**Goal**: End-to-end testing and bug fixes

#### 14.1 Test Harness Validation
- Run all automated scenarios
- Verify all components work together
- Test error conditions
- Test edge cases

#### 14.2 Hardware Testing (if available)
- Test with real rotary phone
- Verify dial pulse reading
- Verify hook switch detection
- Test ringer output
- Verify handset audio

#### 14.3 Network Testing
- Test WiFi connection
- Test AP provisioning flow
- Test network switching
- Test web admin access

#### 14.4 VoIP Testing
- Test SIP registration
- Test outbound calls
- Test inbound calls
- Test audio quality
- Test call reliability

#### 14.5 Web Admin Testing
- Test all web UI features
- Test on different browsers
- Test on mobile devices
- Test authentication

#### 14.6 Bug Fixes
- Document all issues in next-steps.md
- Prioritize fixes
- Fix critical bugs
- Re-test after fixes

**Deliverables**:
- [ ] All tests passing
- [ ] Critical bugs fixed
- [ ] System stable and reliable

---

## Success Criteria

The project is complete when:
1. ✅ All unit tests pass
2. ✅ Test harness runs all scenarios successfully
3. ✅ Phone controller coordinates all components correctly
4. ✅ Web admin interface is functional and accessible
5. ✅ WiFi provisioning works from AP mode
6. ✅ SIP calls can be placed and received (tested with real VoIP provider or in test harness)
7. ✅ Call logs are recorded and viewable
8. ✅ Configuration changes via web UI work correctly
9. ✅ System runs on Raspberry Pi with real hardware (or simulated for initial development)
10. ✅ Documentation is complete and clear

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| PJSUA2 difficult to work with | High | Implement abstraction layer, provide linphone fallback |
| Hardware timing issues | Medium | Make timing configurable, provide test harness to debug |
| Network provisioning complex | High | Test thoroughly with mock GPIO first, use proven libraries |
| Web admin security | Medium | Implement proper authentication, run on local network only |
| GPIO access requires root | Medium | Use udev rules for GPIO access, or run service as root with caution |
| Audio routing issues | Medium | Test audio config separately, provide troubleshooting guide |

## Next Steps

See `next-steps.md` for current status and immediate next actions.