# Rotary Phone VoIP Controller

[![Coverage Status](https://coveralls.io/repos/github/jacob-meacham/rotary-voip/badge.svg?branch=main)](https://coveralls.io/github/jacob-meacham/rotary-voip?branch=main)
[![CI](https://github.com/jacob-meacham/rotary-voip/actions/workflows/ci.yml/badge.svg)](https://github.com/jacob-meacham/rotary-voip/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-blue)

Convert a vintage rotary phone into a fully functional WiFi VoIP phone

## Features

- **Full Rotary Dial Support** - Reads pulse dial input from vintage rotary phones
- **Hook Detection** - Detects when the phone is picked up or hung up
- **Real VoIP Calls** - Make and receive calls through SIP providers (voip.ms, Twilio, etc.)
- **Speed Dial** - Map short codes to full phone numbers
- **Call Allowlist** - Restrict which numbers can be called
- **Extensive Testing** - Unit tests, mock GPIO testing, and real SIP provider testing

## Hardware Requirements

- **Raspberry Pi Zero 2 W** - Recommended for WiFi and compact size
- **Vintage rotary phone** - With working dial and hook switch
- **USB audio adapter** - For handset speaker/microphone
- **Speaker + amplifier** - For ringer (3W 4Ω speaker with PAM8403 amp)
- **GPIO wiring** - Connect hook switch, dial, and ringer to Pi

For complete build instructions, wiring diagrams, and bill of materials, see **[HARDWARE.md](HARDWARE.md)**

## Installation (Raspberry Pi)

Install directly on a fresh Raspberry Pi OS Lite:

```bash
# One-liner install from GitHub
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/jacob-meacham/rotary-voip/main/install.sh)"
```

Or clone and install manually:

```bash
git clone https://github.com/jacob-meacham/rotary-voip.git
cd rotary-voip
sudo ./install.sh
```

The installer will:
- Install all system dependencies (Python, audio tools, etc.)
- Clone the repository to `/opt/rotary-phone`
- Set up Python virtual environment and dependencies
- Install as a systemd service
- Install the `rotary-voip` CLI tool
- Add your user to required groups (gpio, audio, dialout)

After installation:

```bash
# Edit configuration with your SIP credentials
sudo rotary-voip config

# Start the service
sudo rotary-voip start

# View logs
sudo rotary-voip logs
```

To update to the latest version:

```bash
sudo rotary-voip update
```

## Configuration

Edit `/opt/rotary-phone/config.yml` (or `config.yml` for development):

```yaml
sip:
  server: vancouver.voip.ms
  port: 5060
  username: 123456_test
  password: your_password_here

speed_dial:
  "1": "+15551234567"      # Mom
  "2": "+15557654321"      # Dad

allowlist:
  - "*"  # Allow all numbers (or list specific allowed numbers)
```

See `config.yml.example` for all available options.

## Usage

### Making a Call

1. Pick up the phone (hook off)
2. Wait for dial tone
3. Dial the number using the rotary dial
4. Wait 3 seconds after the last digit
5. The call will automatically be placed

### Receiving a Call

1. Phone will ring when someone calls your DID
2. Pick up the phone to answer
3. Hang up when done

### Speed Dial

Configure short codes in `config.yml` that expand to full numbers:
- Dial `1` to call `+15551234567` (Mom)
- Dial `2` to call `+15557654321` (Dad)

## Development

### Setup

```bash
git clone https://github.com/jacob-meacham/rotary-voip.git
cd rotary-voip
uv sync
cp config.yml.example config.yml
```

### Running Locally

```bash
# With mock GPIO (for development on non-Pi systems)
uv run rotary-phone --mock-gpio --config config.yml

# With debug logging
uv run rotary-phone --debug --config config.yml
```

### Testing

```bash
# Run all unit tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Run specific test file
uv run pytest tests/test_dial_reader.py
```

### Interactive Mock Testing (No Hardware Required)

Test the complete system without physical hardware:

```bash
uv run python -m tests.manual.test_harness
```

Commands:
- `u` - Pick up phone (hook off)
- `d` - Hang up phone (hook on)
- `0-9` - Dial a digit
- `i` - Simulate incoming call
- `a` - Simulate remote party answered
- `e` - Simulate remote party hung up
- `s` - Show status
- `q` - Quit

### Real SIP Provider Testing

Test with an actual SIP provider using mock GPIO:

1. **Create `.env.test` file:**
   ```bash
   SIP_SERVER=vancouver.voip.ms
   SIP_PORT=5060
   SIP_USERNAME=123456_test
   SIP_PASSWORD=your_password_here
   SIP_DID=+15551234567
   ```

2. **Run the real phone test harness:**
   ```bash
   uv run python -m tests.manual.test_real_phone
   ```

Commands:
- `u` - Pick up phone
- `d` - Hang up phone
- `0-9` - Dial single digit
- `c` - Call a number (automatically picks up, dials, and places call)
- `a` - Send audio file (WAV) during active call
- `x` - Stop audio playback
- `s` - Show status
- `h` - Help
- `q` - Quit

3. **Generate test audio files:**
   ```bash
   uv run python -m tests.manual.create_test_audio
   ```

   This creates:
   - `test_tone.wav` - Simple 440 Hz tone
   - `test_speech.wav` - Multi-frequency speech-like tone

### Code Quality

```bash
# Run linter
uv run pylint src/rotary_phone

# Run type checker
uv run mypy src/rotary_phone

# Format code
uv run black src tests

# Run all checks
./check.sh
```

## Architecture

### Components

- **CallManager** - Coordinates all components with a state machine
- **HookMonitor** - Detects when phone is picked up/hung up
- **DialReader** - Reads rotary dial pulses and converts to digits
- **Ringer** - Controls the ringer (plays sound files via `aplay` or toggles GPIO for buzzers)
- **SIPClient** - Handles VoIP registration and calls
  - `PyVoIPClient` - Real SIP implementation using pyVoIP library
  - `InMemorySIPClient` - Mock for testing

### State Machine

Phone states:
- **IDLE** - On hook, no activity
- **OFF_HOOK_WAITING** - Picked up, waiting for first digit
- **DIALING** - User is dialing digits
- **VALIDATING** - Checking speed dial and allowlist
- **CALLING** - Outbound call in progress
- **RINGING** - Incoming call, phone ringing
- **CONNECTED** - Active call
- **ERROR** - Error state (blocked number, call failed)

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome! Please feel free to submit pull requests or open issues.

## Acknowledgments

- Built with [pyVoIP](https://github.com/tayler6000/pyVoIP) library
- Uses [uv](https://github.com/astral-sh/uv) for dependency management
