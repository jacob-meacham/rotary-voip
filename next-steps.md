# Next Steps - Rotary Phone VoIP Project

## Current Status
**Core Phone Controller**: Complete (Phases 1-13)
**Web Admin Interface**: In Progress

---

## Web Admin Interface - Project Plan

### Already Implemented
- FastAPI app with basic endpoints ([app.py](src/rotary_phone/web/app.py))
- Dashboard showing phone state with auto-refresh (2s polling)
- Raw YAML config editor with validation
- Sound file listing and WAV upload with RIFF validation
- Dark theme single-page app with tabs
- Integration with CallManager and ConfigManager

### Features to Build

---

## Phase W1: Allowlist Management API & UI - COMPLETE

### Goal
Provide a user-friendly interface to manage which phone numbers can be dialed.

### Backend Tasks
- [x] `GET /api/allowlist` - Return current allowlist from config
- [x] `PUT /api/allowlist` - Update allowlist (array of patterns or `["*"]`)
- [x] Validation: Ensure patterns are valid (phone numbers, `*`, `+` prefix)
- [x] Update ConfigManager in-memory after save
- [x] Atomic write to config.yml

### Frontend Tasks
- [x] Add "Allowlist" tab to UI
- [x] Display current allowlist entries in a list
- [x] Add/remove individual entries
- [x] Toggle between "Allow All" (`*`) and specific numbers
- [x] Input validation for phone number format
- [x] Success/error feedback

### Config Structure
```yaml
allowlist:
  - "+12065551234"
  - "+12065555678"
  # OR
  - "*"  # Allow any number
```

---

## Phase W2: Speed Dial Management API & UI - COMPLETE

### Goal
Allow users to create and manage speed dial shortcuts.

### Backend Tasks
- [x] `GET /api/speed-dial` - Return current speed dial mappings
- [x] `PUT /api/speed-dial` - Update entire speed dial config
- [x] `POST /api/speed-dial` - Add single speed dial entry
- [x] `DELETE /api/speed-dial/{code}` - Remove speed dial entry
- [x] Validation: Code must be 1-2 digits, destination must be valid phone number
- [x] Update ConfigManager in-memory after save

### Frontend Tasks
- [x] Add Speed Dial section in Settings page with collapsible accordion
- [x] List showing: Code → Destination with inline editing
- [x] Add new speed dial form (code input, phone number input)
- [x] Edit existing entries inline
- [x] Delete entries
- [ ] Import/export as JSON/CSV (optional enhancement)

### Config Structure
```yaml
speed_dial:
  "1": "+12065551234"   # Mom
  "2": "+12065555678"   # Dad
  "11": "+18005551234"  # Work
```

---

## Phase W3: Sound File Management Enhancement - COMPLETE

### Goal
Complete sound management with playback, deletion, and assignment.

### Backend Tasks
- [x] `GET /api/sounds/{filename}` - Stream audio file for playback
- [x] `DELETE /api/sounds/{filename}` - Delete a sound file
- [x] `GET /api/sound-assignments` - Get current sound assignments from config
- [x] `PUT /api/sound-assignments` - Update sound assignments

### Frontend Tasks
- [x] Add playback button for each sound (HTML5 audio)
- [x] Add delete button with confirmation
- [x] Sound assignment section showing:
  - Ring sound -> dropdown of available .wav files
  - Dial tone -> dropdown
  - Busy tone -> dropdown
  - Error tone -> dropdown
- [x] Preview sounds via playback button

### Config Structure
```yaml
audio:
  ring_sound: "sounds/ring.wav"
  dial_tone: "sounds/dialtone.wav"
  busy_tone: "sounds/busy.wav"
  error_tone: "sounds/error.wav"
```

---

## Phase W4: Ring Settings UI - COMPLETE

### Goal
Allow configuration of ring timing and behavior.

### Backend Tasks
- [x] `GET /api/ring-settings` - Get ring configuration
- [x] `PUT /api/ring-settings` - Update ring settings
- [x] Validation: Values must be positive numbers within reasonable ranges

### Frontend Tasks
- [x] Add Ring Settings to Sounds section (not separate tab)
- [x] Configurable fields:
  - Ring duration (seconds) - how long the ring plays
  - Ring pause (seconds) - silence between rings
- [x] Input validation with min/max
- [x] Test ring button (plays ring sound for configured duration)
- [x] System Information shows full redacted config

### Config Structure
```yaml
timing:
  ring_duration: 2.0   # Ring on time
  ring_pause: 4.0      # Ring off time
```

---

## Phase W5: Call Log API & UI - COMPLETE

### Goal
Display call history with search and filtering.

### Backend Tasks
- [x] `GET /api/calls` - List recent calls (with pagination)
  - Query params: `limit`, `offset`, `direction`, `status`, `search`
- [x] `GET /api/calls/stats` - Get call statistics for dashboard
- [x] `GET /api/calls/{id}` - Get single call details
- [x] `DELETE /api/calls/{id}` - Delete a call record
- [x] Wire up existing Database class methods

### Frontend Tasks
- [x] Add "Call Log" tab
- [x] Table columns: Date/Time | Direction | Number | Duration | Status
- [x] Direction icons: incoming/outgoing
- [x] Status badges: completed (green), missed (yellow), failed (red)
- [x] Search box (filters by phone number)
- [x] Filter dropdowns (direction, status)
- [x] Pagination (Previous/Next page buttons)
- [x] Click to view details modal
- [x] Call statistics widget (total calls, completed, missed, failed, avg duration)

### Database (Already Exists)
- `Database.get_recent_calls(limit)`
- `Database.search_calls(start_date, end_date, direction, status, number_pattern)`
- `Database.get_call_stats(days)`

---

## Phase W6: WebSocket Real-Time Updates - COMPLETE

### Goal
Replace polling with WebSocket for instant status updates.

### Backend Tasks
- [x] Add WebSocket endpoint: `ws://host:port/ws`
- [x] Create event types:
  - `phone_state_changed` - When state changes (idle -> off_hook, etc.)
  - `call_started` - New outbound/inbound call
  - `call_ended` - Call terminated
  - `digit_dialed` - Real-time digit display
  - `config_changed` - Config was updated
  - `call_log_updated` - Call log was updated
- [x] Pub/sub system for broadcasting events (ConnectionManager)
- [x] Connection management (heartbeat, reconnection with exponential backoff)
- [x] Hook CallManager callbacks to emit WebSocket events

### Frontend Tasks
- [x] WebSocket client with auto-reconnect
- [x] Update dashboard in real-time (no more polling)
- [x] Show live dialing as digits come in
- [x] Toast notifications for incoming calls
- [x] Connection status indicator (dot changes color)

### Event Format
```json
{
  "type": "phone_state_changed",
  "timestamp": "2024-01-15T10:30:00Z",
  "data": {
    "old_state": "idle",
    "new_state": "ringing",
    "caller_id": "+12065551234"
  }
}
```

---

## Phase W7: WiFi Provisioning & Captive Portal - COMPLETE

### Goal
Allow network configuration when phone isn't connected to WiFi.

### Architecture
When the phone boots and can't connect to WiFi:
1. Creates Access Point (AP): `RotaryPhone-XXXX`
2. Runs captive portal on 192.168.4.1
3. User connects and configures WiFi
4. Phone saves credentials and reboots into client mode

### Backend Tasks - Network Module
- [x] Create `src/rotary_phone/network/wifi_manager.py`
  - Scan available networks
  - Connect to network
  - Get connection status
  - Get current IP address
- [x] Create `src/rotary_phone/network/access_point.py`
  - Start/stop hostapd for AP mode
  - Configure dnsmasq for DHCP/DNS
  - Captive portal redirect

### Backend Tasks - API
- [x] `GET /api/network/status` - Current connection status
- [x] `GET /api/network/scan` - List available WiFi networks
- [x] `POST /api/network/connect` - Connect to a network
- [x] `POST /api/network/disconnect` - Disconnect from current network
- [x] `GET /api/network/ap/status` - AP mode status
- [x] `POST /api/network/ap/start` - Start AP mode manually
- [x] `POST /api/network/ap/stop` - Stop AP mode

### Frontend Tasks - Captive Portal
- [x] Minimal HTML page (works without external resources)
- [x] Network list with signal strength
- [x] Password input for protected networks
- [x] Connect button with progress indicator
- [x] Success/failure message
- [x] Auto-redirect to main UI after connection

### Frontend Tasks - Settings Page
- [x] Network section showing current connection
- [x] WiFi settings (SSID, signal, IP)
- [x] Scan and connect to networks
- [x] AP mode controls (start/stop)

### Config Structure
```yaml
network:
  wifi_ssid: "MyNetwork"
  wifi_password: "password123"
  ap_ssid: "RotaryPhone"
  ap_password: "rotaryphone"
```

### System Dependencies
- `hostapd` - Access point daemon
- `dnsmasq` - DHCP and DNS for AP mode
- `wpa_supplicant` - WiFi client

---

## Phase W8: Authentication & Security - COMPLETE

### Goal
Protect the admin interface with authentication.

### Backend Tasks
- [x] Session-based authentication (in-memory sessions with 60min timeout)
- [x] Login endpoint: `POST /api/auth/login`
- [x] Logout endpoint: `POST /api/auth/logout`
- [x] Auth status endpoint: `GET /api/auth/status`
- [x] Password hashing with bcrypt (cost factor 12)
- [x] User database model with username/password_hash
- [x] User management CLI script (`scripts/manage_users.py`)
- [x] Login page route at `/login` (not `/login.html`)

### Frontend Tasks
- [x] Login page (username/password form)
- [x] Session persistence via httponly cookies
- [x] Auto-redirect to login when not authenticated
- [x] Logout button in gear menu
- [x] Fixed infinite redirect loop between login and dashboard

### User Management
```bash
# Add a new user
python scripts/manage_users.py add username

# Delete a user
python scripts/manage_users.py delete username

# List all users
python scripts/manage_users.py list
```

---

## Phase W9: Advanced Settings & Log Viewer - COMPLETE

### Goal
Provide access to advanced configuration options and real-time log viewing for debugging.

### Backend Tasks
- [x] `GET /api/logs` - Stream or fetch recent log entries
- [x] `GET /api/logs/stream` - SSE endpoint for real-time log streaming
- [x] `GET /api/settings/timing` - Get all timing settings
- [x] `PUT /api/settings/timing` - Update timing settings
- [x] `GET /api/settings/logging` - Get logging configuration
- [x] `PUT /api/settings/logging` - Update logging settings
- [x] Log buffer/ring buffer for recent entries (in-memory)
- [x] `DELETE /api/logs` - Clear in-memory log buffer

### Frontend Tasks
- [x] Add "Advanced" section in Settings (collapsed by default)
- [x] Timing settings form:
  - `inter_digit_timeout` - Time to wait for next digit before dialing
  - `hook_debounce_time` - Debounce time for hook switch
  - `pulse_timeout` - Time after last pulse before digit complete
  - `sip_registration_timeout` - SIP registration timeout
  - `call_attempt_timeout` - Outbound call timeout
- [x] Logging settings:
  - Log level selector (DEBUG, INFO, WARNING, ERROR)
  - Log file path (optional)
  - Max file size / rotation settings
- [x] Log Viewer panel:
  - Real-time log stream (auto-scroll)
  - Start/stop streaming toggle
  - Filter by log level
  - Search/filter logs
  - Clear log display

### Config Structure
```yaml
timing:
  hook_debounce_time: 0.01
  pulse_timeout: 0.3
  sip_registration_timeout: 10.0
  call_attempt_timeout: 60.0

logging:
  level: "INFO"
  file: ""
  max_bytes: 10485760
  backup_count: 3
```

---

## Phase W10: Deep Linking & URL Routing - COMPLETE

### Goal
Enable direct URL access to specific pages and preserve navigation state.

### Backend Tasks
- [x] Serve index.html for all non-API routes (SPA catch-all)

### Frontend Tasks
- [x] Implement client-side routing with History API
- [x] URL structure:
  - `/` or `/dashboard` - Dashboard page
  - `/calls` - Call log page
  - `/calls/:id` - Call detail modal (auto-open)
  - `/settings` - Settings page
  - `/allowlist` - Allowlist page
  - `/speed-dial` - Speed dial page
  - `/settings/sounds` - Settings with Sounds section open
  - `/settings/advanced` - Settings with Advanced section open
  - `/logs` - Logs
- [x] Update navigation to use `pushState`
- [x] Handle browser back/forward buttons
- [x] Parse URL on page load and navigate accordingly
- [x] Update page title based on current route
- [x] Shareable URLs (copy link to current view)

### Technical Approach
```javascript
// Use History API (cleaner URLs, needs server catch-all)
history.pushState({page: 'calls'}, 'Call Log', '/calls');
```

---

## Implementation Order & Dependencies

```
Phase W1: Allowlist ─────────────────┐
Phase W2: Speed Dial ────────────────┼──► COMPLETE (W1-W10)
Phase W3: Sound Management ──────────┤
Phase W4: Ring Settings ─────────────┤
Phase W5: Call Log ──────────────────┤
Phase W6: WebSocket ─────────────────┤
Phase W7: WiFi Provisioning ─────────┘
                                     │
                                     ▼
Phase W8: Authentication ────────────► COMPLETE - Session-based auth with bcrypt
                                     │
                                     ▼
Phase W9: Advanced Settings ─────────► COMPLETE - Log viewer, timing config
                                     │
                                     ▼
Phase W10: Deep Linking ─────────────► COMPLETE - URL routing with History API
```

---

## Technical Notes

### Config Hot-Reload Strategy
For Phases W1-W4, after saving config:
1. Write to config.yml atomically (temp file + rename)
2. Update ConfigManager in-memory state
3. Notify relevant components via callback
4. No restart required for most settings

### Database Integration (Phase W5)
The Database class already exists at [database.py](src/rotary_phone/database/database.py):
- Thread-safe connection-per-operation
- Full CallLog model with serialization
- Search and stats methods ready to use

### WebSocket (Phase W6)
FastAPI has built-in WebSocket support:
```python
from fastapi import WebSocket

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # ...
```

### WiFi/AP Mode (Phase W7)
Requires root access for:
- `hostapd` control
- `wpa_supplicant` control
- Network interface configuration

Consider running web server as root or using sudo for specific operations.

---

## File Structure After All Phases

```
src/rotary_phone/web/
├── __init__.py
├── app.py                    # Main FastAPI app (extended)
├── auth.py                   # Authentication middleware
├── api/
│   ├── __init__.py
│   ├── allowlist.py          # Phase W1
│   ├── speed_dial.py         # Phase W2
│   ├── sounds.py             # Phase W3 (moved from app.py)
│   ├── ring_settings.py      # Phase W4
│   └── calls.py              # Phase W5
├── websocket/
│   ├── __init__.py
│   ├── manager.py            # Connection manager
│   └── events.py             # Event types
└── static/
    ├── index.html            # Main SPA (extended)
    └── captive.html          # Captive portal (Phase W7)

src/rotary_phone/network/
├── __init__.py
├── wifi_manager.py           # Phase W7
└── access_point.py           # Phase W7
```

---

## Testing Strategy

Each phase should include:
1. **Unit tests** for new API endpoints (mock dependencies)
2. **Integration tests** for database operations
3. **Manual testing** via the UI

Test files:
- `tests/test_web_allowlist.py`
- `tests/test_web_speed_dial.py`
- `tests/test_web_sounds.py`
- `tests/test_web_calls.py`
- `tests/test_web_websocket.py`
- `tests/test_network.py`

---

## Previous Phases (Completed)

<details>
<summary>Core Phone Controller (Phases 1-13) - COMPLETE</summary>

### Phase 1: Foundation
- [x] uv project setup
- [x] pytest configuration
- [x] Basic project structure

### Phase 2: Configuration Management
- [x] ConfigManager class
- [x] YAML config loading

### Phase 3: GPIO Abstraction Layer
- [x] MockGPIO + RealGPIO
- [x] Auto-detection

### Phase 4: Test Harness
- [x] Interactive CLI simulator

### Phase 5: Dial Reader
- [x] Pulse counting with timeout

### Phase 6: Hook Monitor
- [x] Debounced hook detection

### Phase 7: Ringer
- [x] Audio playback with patterns

### Phase 8: SIP Client
- [x] Abstract SIP interface
- [x] InMemorySIPClient for tests
- [x] PyVoIPClient for real calls

### Phase 9: Call Manager
- [x] State machine
- [x] Speed dial / allowlist

### Phase 10: Phone Controller Integration
- [x] All components wired together

### Phase 11: Systemd Service
- [x] Service file and install script

### Phase 12: Dial Tone
- [x] Play dial tone when off-hook

### Phase 13: Call Logging
- [x] SQLite database
- [x] CallLog model
- [x] Full CRUD operations

</details>
