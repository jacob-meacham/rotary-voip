# Rotary Phone VoIP Conversion Guide

A complete guide to converting a vintage rotary phone into a battery-powered, WiFi-connected VoIP phone with speed dial and number whitelisting—perfect for kids.

---

## Table of Contents

1. [Overview](#overview)
2. [Bill of Materials](#bill-of-materials)
3. [Architecture](#architecture)
4. [Wiring Guide](#wiring-guide)
5. [Software Setup](#software-setup)
6. [VoIP Provider Setup (VoIP.ms)](#voip-provider-setup)
7. [Configuration](#configuration)
8. [Assembly Tips](#assembly-tips)
9. [Replication Kit for Friends](#replication-kit-for-friends)
10. [Troubleshooting](#troubleshooting)

---

## Overview

### What We're Building

- **Input**: Rotary dial pulses + hook switch
- **Output**: Real phone calls over WiFi via SIP/VoIP
- **Features**:
  - 2-digit speed dials (e.g., "12" calls Dad)
  - Number whitelist (longer numbers work if pre-approved)
  - Incoming calls ring a small speaker
  - Runs on battery or USB-C power
  - ~8-12 hour battery life (idle with occasional calls)

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
| Power management | Adafruit PowerBoost 1000C | $20 | Charge + boost + load sharing in one |
| Battery | 3.7V LiPo 2500-3500mAh | $12 | JST-PH connector; fits PowerBoost |
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

---

## Software Setup

### 1. Prepare the Raspberry Pi

```bash
# Flash Raspberry Pi OS Lite (64-bit) to SD card using Raspberry Pi Imager
# Enable SSH and configure WiFi in the imager's settings

# After first boot, SSH in and update:
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3-pip python3-venv git alsa-utils pulseaudio

# Install PJSIP (SIP library) - this takes a while on Pi Zero
sudo apt install -y python3-pjsua2

# Alternative: use the lighter-weight 'baresip' or 'linphone' CLI
# We'll use PJSUA2 for better Python integration
```

### 2. Create Project Structure

```bash
mkdir -p ~/rotary-phone
cd ~/rotary-phone

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install RPi.GPIO pjsua2 python-dotenv pyyaml
```

### 3. Main Application Code

Create `~/rotary-phone/phone.py`:

```python
#!/usr/bin/env python3
"""
Rotary Phone VoIP Controller
Handles dial input, hook switch, and SIP calling via PJSUA2
"""

import RPi.GPIO as GPIO
import time
import threading
import yaml
import os
import subprocess
from pathlib import Path

# Try to import pjsua2; fall back to subprocess+linphone if unavailable
try:
    import pjsua2 as pj
    USE_PJSUA = True
except ImportError:
    USE_PJSUA = False
    print("PJSUA2 not available, falling back to linphonec")

# =============================================================================
# CONFIGURATION
# =============================================================================

CONFIG_FILE = Path(__file__).parent / "config.yaml"

# GPIO Pins (BCM numbering)
PIN_HOOK = 17       # Hook switch (HIGH = on-hook)
PIN_DIAL_PULSE = 27 # Dial pulse output
PIN_DIAL_ACTIVE = 22  # Dial off-normal (optional)
PIN_RINGER = 23     # Ringer amplifier enable
PIN_LOW_BATTERY = 24  # PowerBoost LBO pin (optional)

# Timing constants (in seconds)
DEBOUNCE_TIME = 0.01        # 10ms debounce
PULSE_TIMEOUT = 0.3         # Max time between pulses in same digit
INTER_DIGIT_TIMEOUT = 2.0   # Time to wait for next digit before dialing
RING_DURATION = 2.0         # Ring on time
RING_PAUSE = 4.0            # Ring off time

# =============================================================================
# LOAD CONFIGURATION
# =============================================================================

def load_config():
    """Load configuration from YAML file"""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_FILE}")
    
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)

config = load_config()

# =============================================================================
# DIAL READER
# =============================================================================

class DialReader:
    """Reads rotary dial pulses and converts to digits"""
    
    def __init__(self, pulse_pin, callback):
        self.pulse_pin = pulse_pin
        self.callback = callback  # Called with each digit
        self.pulse_count = 0
        self.last_pulse_time = 0
        self.dialing = False
        self._lock = threading.Lock()
        
        # Setup GPIO
        GPIO.setup(pulse_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(pulse_pin, GPIO.FALLING, 
                              callback=self._pulse_detected,
                              bouncetime=int(DEBOUNCE_TIME * 1000))
        
        # Start timeout checker thread
        self._running = True
        self._thread = threading.Thread(target=self._check_timeout, daemon=True)
        self._thread.start()
    
    def _pulse_detected(self, channel):
        """Called on each falling edge (pulse)"""
        with self._lock:
            self.pulse_count += 1
            self.last_pulse_time = time.time()
            self.dialing = True
    
    def _check_timeout(self):
        """Background thread to detect end of digit"""
        while self._running:
            time.sleep(0.05)  # Check every 50ms
            
            with self._lock:
                if self.dialing and self.pulse_count > 0:
                    elapsed = time.time() - self.last_pulse_time
                    if elapsed > PULSE_TIMEOUT:
                        # Digit complete
                        digit = self.pulse_count % 10  # 10 pulses = 0
                        self.pulse_count = 0
                        self.dialing = False
                        
                        # Call callback outside lock
                        threading.Thread(target=self.callback, 
                                         args=(digit,), daemon=True).start()
    
    def stop(self):
        self._running = False

# =============================================================================
# HOOK SWITCH MONITOR
# =============================================================================

class HookMonitor:
    """Monitors hook switch state"""
    
    def __init__(self, hook_pin, on_pickup, on_hangup):
        self.hook_pin = hook_pin
        self.on_pickup = on_pickup
        self.on_hangup = on_hangup
        self.is_off_hook = False
        
        GPIO.setup(hook_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(hook_pin, GPIO.BOTH,
                              callback=self._hook_changed,
                              bouncetime=50)
        
        # Check initial state
        self._check_state()
    
    def _check_state(self):
        """Read current hook state"""
        # LOW = off-hook (handset lifted)
        self.is_off_hook = GPIO.input(self.hook_pin) == GPIO.LOW
    
    def _hook_changed(self, channel):
        """Called when hook switch changes"""
        time.sleep(0.05)  # Extra debounce
        was_off_hook = self.is_off_hook
        self._check_state()
        
        if self.is_off_hook and not was_off_hook:
            self.on_pickup()
        elif not self.is_off_hook and was_off_hook:
            self.on_hangup()

# =============================================================================
# RINGER
# =============================================================================

class Ringer:
    """Controls the ringer speaker"""
    
    def __init__(self, enable_pin, sound_file=None):
        self.enable_pin = enable_pin
        self.sound_file = sound_file or "/home/pi/rotary-phone/sounds/ring.wav"
        self._ringing = False
        self._thread = None
        
        GPIO.setup(enable_pin, GPIO.OUT)
        GPIO.output(enable_pin, GPIO.LOW)
    
    def start(self):
        """Start ringing"""
        if self._ringing:
            return
        self._ringing = True
        self._thread = threading.Thread(target=self._ring_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop ringing"""
        self._ringing = False
        GPIO.output(self.enable_pin, GPIO.LOW)
    
    def _ring_loop(self):
        """Ring pattern loop"""
        while self._ringing:
            # Enable amp and play sound
            GPIO.output(self.enable_pin, GPIO.HIGH)
            subprocess.run(["aplay", "-q", self.sound_file], 
                          capture_output=True, timeout=RING_DURATION + 1)
            GPIO.output(self.enable_pin, GPIO.LOW)
            
            if not self._ringing:
                break
            
            # Pause between rings
            time.sleep(RING_PAUSE)

# =============================================================================
# SIP CLIENT (PJSUA2)
# =============================================================================

class SIPPhone:
    """Handles SIP registration and calls"""
    
    def __init__(self, sip_config, on_incoming_call, on_call_ended):
        self.config = sip_config
        self.on_incoming_call = on_incoming_call
        self.on_call_ended = on_call_ended
        
        self.endpoint = None
        self.account = None
        self.current_call = None
        
        if USE_PJSUA:
            self._init_pjsua()
        else:
            self._init_linphone()
    
    def _init_pjsua(self):
        """Initialize PJSUA2 library"""
        # Create endpoint
        self.endpoint = pj.Endpoint()
        self.endpoint.libCreate()
        
        # Configure endpoint
        ep_cfg = pj.EpConfig()
        ep_cfg.logConfig.level = 3
        self.endpoint.libInit(ep_cfg)
        
        # Create UDP transport
        transport_cfg = pj.TransportConfig()
        transport_cfg.port = 5060
        self.endpoint.transportCreate(pj.PJSIP_TRANSPORT_UDP, transport_cfg)
        
        # Start library
        self.endpoint.libStart()
        
        # Configure account
        acc_cfg = pj.AccountConfig()
        acc_cfg.idUri = f"sip:{self.config['username']}@{self.config['server']}"
        acc_cfg.regConfig.registrarUri = f"sip:{self.config['server']}"
        
        cred = pj.AuthCredInfo("digest", "*", 
                               self.config['username'], 
                               0, 
                               self.config['password'])
        acc_cfg.sipConfig.authCreds.append(cred)
        
        # Create and register account
        self.account = RotaryAccount(self)
        self.account.create(acc_cfg)
    
    def _init_linphone(self):
        """Initialize linphonec subprocess fallback"""
        # We'll use subprocess calls to linphonec
        pass
    
    def make_call(self, number):
        """Initiate outbound call"""
        if self.current_call:
            print("Already in a call")
            return False
        
        # Format number for SIP URI
        uri = f"sip:{number}@{self.config['server']}"
        
        if USE_PJSUA:
            call = RotaryCall(self, self.account)
            call_param = pj.CallOpParam(True)
            call.makeCall(uri, call_param)
            self.current_call = call
        else:
            # Linphone fallback
            subprocess.Popen(["linphonec", "-c", "/etc/linphonerc", 
                            "call", uri])
        
        return True
    
    def answer_call(self):
        """Answer incoming call"""
        if self.current_call and USE_PJSUA:
            call_param = pj.CallOpParam()
            call_param.statusCode = 200
            self.current_call.answer(call_param)
    
    def hangup(self):
        """End current call"""
        if self.current_call:
            if USE_PJSUA:
                call_param = pj.CallOpParam()
                self.current_call.hangup(call_param)
            else:
                subprocess.run(["linphonec", "-c", "/etc/linphonerc", 
                               "terminate"])
            self.current_call = None

class RotaryAccount(pj.Account):
    """PJSUA2 Account with callbacks"""
    
    def __init__(self, phone):
        super().__init__()
        self.phone = phone
    
    def onIncomingCall(self, prm):
        """Handle incoming call"""
        call = RotaryCall(self.phone, self, prm.callId)
        self.phone.current_call = call
        
        # Get caller info
        ci = call.getInfo()
        caller = ci.remoteUri
        
        # Notify main app
        self.phone.on_incoming_call(caller)

class RotaryCall(pj.Call):
    """PJSUA2 Call with callbacks"""
    
    def __init__(self, phone, account, call_id=pj.PJSUA_INVALID_ID):
        super().__init__(account, call_id)
        self.phone = phone
    
    def onCallState(self, prm):
        """Handle call state changes"""
        ci = self.getInfo()
        
        if ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            self.phone.current_call = None
            self.phone.on_call_ended()

# =============================================================================
# MAIN PHONE CONTROLLER
# =============================================================================

class RotaryPhoneController:
    """Main controller coordinating all components"""
    
    def __init__(self):
        self.config = config
        
        # State
        self.dialed_digits = ""
        self.dial_timer = None
        self.state = "idle"  # idle, dialing, ringing, in_call
        
        # Initialize GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Initialize components
        self.ringer = Ringer(PIN_RINGER)
        self.dial = DialReader(PIN_DIAL_PULSE, self._on_digit)
        self.hook = HookMonitor(PIN_HOOK, self._on_pickup, self._on_hangup)
        self.sip = SIPPhone(
            self.config['sip'],
            self._on_incoming_call,
            self._on_call_ended
        )
        
        print("Rotary Phone Controller initialized")
        print(f"Speed dials: {list(self.config.get('speed_dial', {}).keys())}")
        print(f"Whitelist entries: {len(self.config.get('whitelist', []))}")
    
    def _on_digit(self, digit):
        """Handle dialed digit"""
        if self.state not in ("dialing", "idle") or not self.hook.is_off_hook:
            return
        
        self.state = "dialing"
        self.dialed_digits += str(digit)
        print(f"Digit: {digit}, Accumulated: {self.dialed_digits}")
        
        # Reset dial timer
        if self.dial_timer:
            self.dial_timer.cancel()
        self.dial_timer = threading.Timer(INTER_DIGIT_TIMEOUT, self._dial_complete)
        self.dial_timer.start()
    
    def _dial_complete(self):
        """Called when dialing is complete (timeout)"""
        number = self.dialed_digits
        self.dialed_digits = ""
        
        if not number:
            return
        
        # Check speed dial first
        speed_dials = self.config.get('speed_dial', {})
        if number in speed_dials:
            target = speed_dials[number]
            print(f"Speed dial {number} -> {target}")
            self._place_call(target)
            return
        
        # Check whitelist
        whitelist = self.config.get('whitelist', [])
        if number in whitelist or '*' in whitelist:
            print(f"Whitelisted number: {number}")
            self._place_call(number)
            return
        
        print(f"Number not allowed: {number}")
        # Could play error tone here
    
    def _place_call(self, number):
        """Place outbound call"""
        print(f"Calling: {number}")
        self.state = "in_call"
        self.sip.make_call(number)
    
    def _on_pickup(self):
        """Handle handset pickup"""
        print("Off-hook (picked up)")
        
        if self.state == "ringing":
            # Answer incoming call
            self.ringer.stop()
            self.sip.answer_call()
            self.state = "in_call"
        elif self.state == "idle":
            # Ready to dial
            self.state = "dialing"
            self.dialed_digits = ""
            # Could play dial tone here
    
    def _on_hangup(self):
        """Handle handset hangup"""
        print("On-hook (hung up)")
        
        # Cancel any pending dial
        if self.dial_timer:
            self.dial_timer.cancel()
        self.dialed_digits = ""
        
        # End call if active
        if self.state == "in_call":
            self.sip.hangup()
        
        # Stop ringer if ringing
        if self.state == "ringing":
            self.ringer.stop()
        
        self.state = "idle"
    
    def _on_incoming_call(self, caller):
        """Handle incoming call"""
        print(f"Incoming call from: {caller}")
        self.state = "ringing"
        self.ringer.start()
    
    def _on_call_ended(self):
        """Handle call ended"""
        print("Call ended")
        if self.state != "idle":
            self.state = "idle"
    
    def run(self):
        """Main loop"""
        print("Phone ready. Waiting for activity...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        self.dial.stop()
        self.ringer.stop()
        GPIO.cleanup()

# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    phone = RotaryPhoneController()
    phone.run()
```

### 4. Configuration File

Create `~/rotary-phone/config.yaml`:

```yaml
# Rotary Phone Configuration

# SIP/VoIP Settings (VoIP.ms example)
sip:
  server: "seattle.voip.ms"      # Your assigned server
  username: "123456"             # Your VoIP.ms main account or sub-account
  password: "your_sip_password"  # SIP password (not web password)
  
# Speed Dial Mappings
# Kids dial a short number, phone calls the full number
speed_dial:
  "11": "+12065551234"    # Dad's cell
  "12": "+12065555678"    # Mom's cell
  "13": "+12065559999"    # Grandma
  "14": "+12065551111"    # Grandpa
  "20": "+12065550000"    # Home landline
  "99": "+19195551212"    # Time & temperature (fun for kids)

# Whitelist - numbers that can be dialed directly
# Use '*' to allow any number (not recommended for kids)
whitelist:
  - "+12065551234"        # Can also dial Dad directly
  - "+12065555678"        # Can also dial Mom directly
  # Add 911 if you want emergency access (consider carefully)
  # - "911"
  
# Audio settings
audio:
  ring_sound: "/home/pi/rotary-phone/sounds/ring.wav"
  dial_tone: "/home/pi/rotary-phone/sounds/dialtone.wav"
  busy_tone: "/home/pi/rotary-phone/sounds/busy.wav"
  error_tone: "/home/pi/rotary-phone/sounds/error.wav"
```

### 5. Systemd Service (Auto-start)

Create `/etc/systemd/system/rotary-phone.service`:

```ini
[Unit]
Description=Rotary Phone VoIP Service
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/rotary-phone
ExecStart=/home/pi/rotary-phone/venv/bin/python /home/pi/rotary-phone/phone.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable rotary-phone
sudo systemctl start rotary-phone
```

---

## VoIP Provider Setup

### Why VoIP.ms?

- **Cost**: ~$0.85/month for a phone number + ~$0.01/min for calls
- **No contracts**: Pay-as-you-go
- **Standard SIP**: Works with any SIP client
- **Reliable**: Been around since 2007
- **No webhooks needed**: Unlike Twilio, no server required for basic calling

### Setup Steps

1. **Create Account**: Go to [voip.ms](https://voip.ms) and sign up

2. **Add Funds**: Add $10-25 to start (will last months for light use)

3. **Get a Phone Number**:
   - Go to DID Numbers → Order DID
   - Choose your area code
   - Select "Per Minute" plan (~$0.85/month)
   - Complete purchase

4. **Configure SIP Credentials**:
   - Go to Main Menu → Account Settings
   - Note your **Account number** (e.g., 123456)
   - Go to Sub Accounts → Create Sub Account (recommended for security)
   - Set a **SIP Password** (different from web login)

5. **Find Your Server**:
   - Go to Main Menu → Account Settings → Advanced Settings
   - Note your **Server/POP** (e.g., seattle.voip.ms)

6. **Configure Routing**:
   - Go to DID Numbers → Manage DIDs
   - Click your number → Edit
   - Set "Routing" to your sub-account
   - Set "POP" to your chosen server

7. **Update config.yaml**:

```yaml
sip:
  server: "seattle.voip.ms"    # Your POP
  username: "123456_subacct"   # Account_subaccount or just account number
  password: "your_sip_pass"    # SIP password
```

### Test Registration

```bash
# Test SIP registration manually
sudo apt install linphone
linphonec

# In linphonec:
> register sip:123456@seattle.voip.ms seattle.voip.ms password
> status
# Should show "registered"
> call sip:+12065551234@seattle.voip.ms
# Should initiate call
> quit
```

---

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

## Replication Kit for Friends

### "Kit" Contents for Easy Replication

1. **Pre-configured SD card image** (back up your working setup)
   ```bash
   sudo dd if=/dev/mmcblk0 of=rotary-phone-image.img bs=4M status=progress
   # Shrink with PiShrink before distributing
   ```

2. **Pre-made wiring harness** with labeled JST connectors:
   - Hook switch cable (2-pin)
   - Dial pulse cable (2-pin)
   - Handset audio cable (4-pin or 2x 3.5mm)
   - Power board cable (2-pin to Pi)

3. **Component bundle**:
   - Pi Zero 2 W + headers (pre-soldered)
   - USB audio adapter + OTG cable
   - PowerBoost 1000C
   - 2500mAh LiPo
   - PAM8403 amp board + speaker
   - USB-C panel mount
   - Heat shrink, wire, resistors

4. **Documentation**:
   - One-page quick start
   - Wiring photo reference for common phones
   - VoIP.ms setup checklist
   - Troubleshooting guide

### Estimated Kit Cost Breakdown

| Component | Unit Cost | Bulk (10+) |
|-----------|-----------|------------|
| Pi Zero 2 W | $15 | $15 |
| SD Card 16GB | $8 | $5 |
| USB Audio | $8 | $5 |
| PowerBoost 1000C | $20 | $18 |
| LiPo 2500mAh | $12 | $10 |
| Amp + Speaker | $5 | $3 |
| USB-C mount | $3 | $2 |
| Wiring/connectors | $10 | $5 |
| **Total** | **~$81** | **~$63** |

---

## Troubleshooting

### Common Issues

| Problem | Likely Cause | Solution |
|---------|--------------|----------|
| No dial tone | Pi not booted, or SIP not registered | Check `systemctl status rotary-phone`, verify WiFi |
| Dial reads wrong digit | Pulse timing off | Adjust `PULSE_TIMEOUT` in code, or dial slower |
| Can't hear caller | USB audio not selected | Run `alsamixer`, set USB as default |
| Caller can't hear us | Mic wiring reversed or too quiet | Check polarity, adjust mic gain |
| Ringer too quiet | Speaker/amp issue | Check amp wiring, increase GPIO drive |
| Won't register to VoIP | Credentials wrong | Double-check SIP password vs web password |
| Calls drop after 30s | Firewall/NAT issue | Enable STUN in SIP config, check router |

### Useful Debug Commands

```bash
# Check service status
sudo systemctl status rotary-phone
sudo journalctl -u rotary-phone -f

# Test GPIO manually
gpio readall
gpio read 17  # Hook switch

# Test audio
arecord -l   # List capture devices
aplay -l     # List playback devices
speaker-test -D plughw:1,0  # Test USB audio out

# Test SIP
linphonec
> register sip:user@server.voip.ms server.voip.ms password
> status
> quit
```

### Log Files

- Service log: `journalctl -u rotary-phone`
- Application log: `~/rotary-phone.log` (if configured)
- SIP debug: Add `ep_cfg.logConfig.level = 5` in code for verbose SIP logging

---

## Next Steps & Enhancements

Once the basic phone works, consider:

1. **Visual indicator**: LED that shows registration status / battery level
2. **Dial tone**: Play audio when off-hook using PulseAudio
3. **Call history**: Log calls to a file
4. **Remote config**: Web UI to update speed dials
5. **Original bell ringer**: Boost converter to 90V AC (advanced!)
6. **Battery gauge**: Read PowerBoost LBO pin, announce low battery

---

## License & Credits

This project guide is provided as-is for personal/hobby use. 

Inspired by numerous rotary phone hacking projects including:
- Voidon's original Pi rotary phone
- Trandi's VoIP SIP rotary
- Grandstream HT801 pulse-dial community

---

*Happy hacking! There's something magical about rotary phones—enjoy bringing this vintage hardware back to life.*
