# Rotary Phone VoIP Controller

[![Coverage Status](https://coveralls.io/repos/github/GITHUB_USERNAME/REPO_NAME/badge.svg?branch=main)](https://coveralls.io/github/GITHUB_USERNAME/REPO_NAME?branch=main)
[![CI](https://github.com/GITHUB_USERNAME/REPO_NAME/actions/workflows/ci.yml/badge.svg)](https://github.com/GITHUB_USERNAME/REPO_NAME/actions/workflows/ci.yml)
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

- Raspberry Pi (Raspberry Pi Zero 2 W recommended)
- Vintage rotary phone with:
  - Rotary dial mechanism
  - Hook switch
- Speaker for ringing (amplified speaker or buzzer)
- GPIO wiring to connect:
  - Hook switch to GPIO pin
  - Dial pulse contact to GPIO pin
  - Speaker/ringer to GPIO pin (via amplifier circuit)

## Software Requirements

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- Access to a SIP VoIP provider (voip.ms, Twilio, etc.)

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd rotary-voip
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Create configuration file:**
   ```bash
   cp config.yaml.example config.yaml
   ```

4. **Edit configuration** with your SIP credentials and GPIO pins:
   ```yaml
   sip:
     server: vancouver.voip.ms
     port: 5060
     username: 123456_test
     password: your_password_here

   hardware:
     hook_pin: 17      # GPIO pin for hook switch
     dial_pin: 27      # GPIO pin for rotary dial pulse
     ringer_pin: 22    # GPIO pin for ringer control

   speed_dial:
     "1": "+15551234567"      # Mom
     "2": "+15557654321"      # Dad

   allowlist:
     - "*"  # Allow all numbers (or list specific allowed numbers)

   timing:
     inter_digit_timeout: 3.0  # Seconds to wait after last digit
     pulse_timeout: 0.15       # Max time between pulses in a digit
     debounce_time: 0.05       # Hook switch debounce time
   ```

## Usage

### Running the Phone System

```bash
# On Raspberry Pi with real hardware
uv run rotary-phone --config config.yaml

# For testing without hardware (mock GPIO)
uv run rotary-phone --mock-gpio --config config.yaml

# With debug logging
uv run rotary-phone --debug --config config.yaml
```

### Making a Call

1. Pick up the phone (hook off)
2. Wait for dial tone (indicated by REGISTERED state)
3. Dial the number using the rotary dial
4. Wait 3 seconds after the last digit
5. The call will automatically be placed

### Receiving a Call

1. Phone will ring when someone calls your DID
2. Pick up the phone to answer
3. Hang up when done

### Speed Dial

Configure short codes in `config.yaml` that expand to full numbers:
- Dial `1` to call `+15551234567` (Mom)
- Dial `2` to call `+15557654321` (Dad)

## Testing

### Running Unit Tests

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

# Hardware

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     ROTARY PHONE                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│  │  Rotary  │  │   Hook   │  │ Handset  │  │   Ringer    │ │
│  │   Dial   │  │  Switch  │  │ Speaker  │  │   (bell)    │ │
│  │          │  │          │  │   +Mic   │  │             │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬──────┘ │
│       │             │             │               │         │
└───────┼─────────────┼─────────────┼───────────────┼─────────┘
        │             │             │               │
        │ GPIO        │ GPIO        │ USB Audio     │ GPIO+Amp
        │             │             │               │
┌───────┴─────────────┴─────────────┴───────────────┴─────────┐
│                    RASPBERRY PI ZERO 2 W                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Python Control Software                 │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────┐  │   │
│  │  │  Dial   │ │  Hook   │ │  Audio  │ │    SIP    │  │   │
│  │  │ Reader  │ │ Monitor │ │ Router  │ │  Client   │  │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────┬─────┘  │   │
│  └────────────────────────────────────────────┼────────┘   │
│                                               │             │
│                                          WiFi │             │
└───────────────────────────────────────────────┼─────────────┘
                                                │
                                                ▼
                                    ┌───────────────────┐
                                    │     VoIP.ms       │
                                    │   SIP Server      │
                                    │                   │
                                    │  ──────────────── │
                                    │        │          │
                                    │        ▼          │
                                    │      PSTN         │
                                    │  (Real phones)    │
                                    └───────────────────┘
```

---

## Bill of Materials

### Core Electronics (~$55-65)

| Component | Model | Est. Cost | Notes |
|-----------|-------|-----------|-------|
| Single-board computer | Raspberry Pi Zero 2 W | $15 | WiFi built-in, fits in most phone cases |
| MicroSD card | 16GB+ Class 10 | $8 | For Raspberry Pi OS |
| USB audio adapter | Sabrent AU-MMSA or similar | $8 | Must be USB-A; get a micro-USB OTG adapter |
| Ringer speaker | 3W 4Ω speaker + PAM8403 amp | $5 | Small class-D amp module |
| USB-C breakout | Panel-mount USB-C to bare wires | $3 | For clean charging port |

### Connectors & Wiring (~$10-15)

| Component | Qty | Notes |
|-----------|-----|-------|
| Dupont jumper wires | 20 | Female-to-female for GPIO |
| 22 AWG hookup wire | 10 ft | For internal wiring |
| 10kΩ resistors | 4 | Pull-ups for GPIO inputs |
| 3.5mm audio jack (optional) | 1 | If handset uses standard plug |
| Heat shrink tubing | Assorted | For clean connections |
| JST connectors (optional) | 4 pairs | For easy disconnect during service |

### Tools Needed

- Soldering iron + solder
- Wire strippers
- Multimeter
- Small screwdrivers (phone disassembly)
- Hot glue gun (mounting components)

### Total Estimated Cost: **$65-80 per phone**

---

## Wiring Guide

### Understanding Your Rotary Phone

Most rotary phones have these internal connections:

1. **Hook switch**: Opens/closes when handset is lifted/replaced
2. **Rotary dial**: Pulses a switch N times for digit N (0 = 10 pulses)
3. **Handset**: Contains speaker + carbon/dynamic microphone
4. **Ringer**: Electromagnetic bell (we'll bypass this—needs 90V AC)

**Before wiring**: Open your phone, take photos, and trace the existing wires. Use a multimeter in continuity mode to identify:
- Which wires go to the hook switch
- Which wires pulse when you dial
- Which wires go to the handset speaker/mic

### GPIO Pin Assignments

| Function | GPIO (BCM) | Physical Pin | Notes |
|----------|------------|--------------|-------|
| Hook switch | GPIO 17 | Pin 11 | HIGH = on-hook, LOW = off-hook |
| Dial pulse | GPIO 27 | Pin 13 | Pulses LOW for each digit |
| Dial active | GPIO 22 | Pin 15 | LOW while dial is rotating (optional but helpful) |
| Ringer amp enable | GPIO 23 | Pin 16 | HIGH to enable ringer speaker |
| Ground | GND | Pin 6, 9, 14, etc. | Common ground |

### Wiring Diagram

```
                                    RASPBERRY PI ZERO 2 W
                                    ┌────────────────────┐
                                    │ (USB/Power on left)│
                                    │                    │
HOOK SWITCH ─────┬──── 10kΩ ───────│─ 3.3V (Pin 1)     │
                 │                  │                    │
                 └─────────────────│─ GPIO17 (Pin 11)   │
                 │                  │                    │
                 └── (other leg) ──│─ GND (Pin 9)       │
                                    │                    │
DIAL PULSE ──────┬──── 10kΩ ───────│─ 3.3V (Pin 1)     │
                 │                  │                    │
                 └─────────────────│─ GPIO27 (Pin 13)   │
                 │                  │                    │
                 └── (other leg) ──│─ GND               │
                                    │                    │
DIAL ACTIVE ─────┬──── 10kΩ ───────│─ 3.3V             │
(optional)       │                  │                    │
                 └─────────────────│─ GPIO22 (Pin 15)   │
                 │                  │                    │
                 └── (other leg) ──│─ GND               │
                                    │                    │
                              ┌────│─ GPIO23 (Pin 16)   │
                              │     │                    │
                              │     │      ┌── USB ─────│─ USB (for audio adapter)
                              │     │      │            │
                              │     └──────┴────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   PAM8403 Amp   │
                    │                 │
                    │  VCC ◄──────────┼─── 5V from PowerBoost
                    │  GND ◄──────────┼─── GND
                    │  EN  ◄──────────┘ (GPIO23 accent enable)
                    │                 │
                    │  L+/L- ─────────┼───► Speaker (3W 4Ω)
                    │                 │
                    │  R IN ◄─────────┼─── 3.5mm from Pi headphone
                    └─────────────────┘


HANDSET ────────────────────────────────────────────────────────
                                                                
  Speaker (+) ──────────► USB Audio "Headphone" left channel    
  Speaker (-) ──────────► USB Audio "Headphone" ground          
                                                                
  Mic (+) ──────────────► USB Audio "Mic" signal                
  Mic (-) ──────────────► USB Audio "Mic" ground                


POWER SYSTEM ───────────────────────────────────────────────────

  USB-C Input ──────────► PowerBoost 1000C "USB" input
  
  LiPo Battery ─────────► PowerBoost 1000C "BAT" JST connector
  
  PowerBoost "5V" ──────► Pi Zero "5V" (Pin 2 or 4)
  PowerBoost "GND" ─────► Pi Zero "GND" (Pin 6)
  
  PowerBoost "LBO" ─────► GPIO24 (optional: low battery warning)
```

### Hook Switch Wiring Detail

The hook switch is typically a simple SPST switch. When the handset is **on the hook** (hung up), the switch is **open**. When **off hook** (lifted), it's **closed**.

```
        ┌─────────────┐
        │ Hook Switch │
  ──────┤             ├──────
   (A)  │   ┌───┐     │  (B)
        │   │   │     │
        │   └───┘     │
        │  (plunger)  │
        └─────────────┘
        
  Wire A ──► GPIO17
  Wire B ──► GND
  
  Plus: 10kΩ pull-up from GPIO17 to 3.3V
  
  Result: GPIO17 reads HIGH when on-hook, LOW when off-hook
```

### Rotary Dial Wiring Detail

The rotary dial has two switches:
1. **Pulse switch**: Opens/closes rapidly as dial returns (10 pulses/sec)
2. **Off-normal switch**: Closes while dial is pulled away from rest position

```
  When you dial "5":
  
  Off-normal: ___________/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\___________
                         ↑ dial pulled                  ↑ dial returns to rest
                         
  Pulse:      ___________/‾\_/‾\_/‾\_/‾\_/‾\___________________________
                           1   2   3   4   5  (5 pulses = digit 5)
              
  Time:       |──────────|─────────────────────|──────────────────────|
              0ms      ~100ms               ~600ms                  ~800ms
```

Wire the pulse switch to GPIO27 with a 10kΩ pull-up. The software will:
1. Detect dial activity (GPIO27 going LOW)
2. Count pulses
3. After ~300ms of no pulses, register the digit


## Assembly Tips

### Phone Disassembly Notes

**Common US phones** (Western Electric 500/554, ITT):
- Remove 4 screws on bottom
- Housing lifts off, exposing internals
- Bell gongs are held by a single screw
- Network block (where wires terminate) usually has screw terminals

**UK phones** (GPO 746):
- Slightly different dial mechanism (may need pulse timing adjustment)
- Same general approach

### Fitting Components

1. **Remove the bell gongs** (we're replacing with a speaker)
   - Keep them if you want to attempt high-voltage ringer later

2. **Pi Zero 2 W placement**: Fits easily where the bell coil was
   - Use standoffs or hot glue on non-conductive surface
   - Ensure GPIO pins are accessible

3. **PowerBoost placement**: Near the Pi, on the base
   - USB input should be accessible for charging
   - Consider mounting USB-C port where the original phone cord exited

4. **Battery**: LiPo pack tucks into empty space
   - Secure with double-sided tape or velcro
   - Keep away from any remaining metal contacts

5. **Speaker**: Mount where bell was, facing downward through vents
   - 3W is plenty loud for ringing

### Handset Wiring

The handset typically has 4 wires (2 for speaker, 2 for mic):

1. Use multimeter to identify which pair is speaker (lower resistance, ~8-32Ω)
2. Mic pair will show higher/variable resistance

Connect to USB audio adapter:
- Speaker wires → 3.5mm headphone output (may need to split a 3.5mm cable)
- Mic wires → 3.5mm mic input

**Carbon mics** (older phones): May need a small DC bias circuit
**Dynamic mics** (newer phones): Usually work directly

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome! Please feel free to submit pull requests or open issues.

## Acknowledgments

- Built with [pyVoIP](https://github.com/tayler6000/pyVoIP) library
- Uses [uv](https://github.com/astral-sh/uv) for dependency management
