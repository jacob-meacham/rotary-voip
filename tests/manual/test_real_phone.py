"""Interactive test harness for the rotary phone system with REAL SIP.

This harness allows you to test the full phone system without physical hardware,
but with a real SIP provider connection. It uses MockGPIO to simulate hardware
while connecting to an actual VoIP service.

Configuration:
    Create a .env.test file with your SIP credentials:
        SIP_SERVER=vancouver.voip.ms
        SIP_PORT=5060
        SIP_USERNAME=123456_test
        SIP_PASSWORD=your_password_here
        SIP_DID=+15551234567

    Optional USB audio configuration:
        AUDIO_DEVICE=USB          # Device name filter (default: auto-detect USB)
        AUDIO_AUTO_START=1        # Auto-start USB audio when call connects
        AUDIO_INPUT_GAIN=1.0      # Microphone gain (0.0-2.0)
        AUDIO_OUTPUT_VOLUME=1.0   # Speaker volume (0.0-2.0)

    Optional ringer configuration:
        RINGER_SOUND_FILE=/path/to/ring.wav  # Sound file to play when ringing

Run with:
    python -m tests.manual.test_real_phone

WARNING: This will make actual SIP connections and may incur charges.
"""

import audioop
import os
import struct
import sys
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest.mock import Mock

from dotenv import load_dotenv

from rotary_phone.audio.audio_handler import AudioHandler
from rotary_phone.call_manager import CallManager, PhoneState
from rotary_phone.hardware.dial_reader import DialReader
from rotary_phone.hardware.gpio_abstraction import MockGPIO
from rotary_phone.hardware.hook_monitor import HookMonitor
from rotary_phone.hardware.pins import DIAL_PULSE, HOOK
from rotary_phone.hardware.ringer import Ringer
from rotary_phone.sip.pyvoip_client import PyVoIPClient


# Load from .env.test file if it exists
env_test_file = Path(__file__).parent.parent.parent / ".env.test"
if env_test_file.exists():
    print(f"Loading SIP configuration from {env_test_file}")
    load_dotenv(env_test_file)


def get_sip_config() -> dict[str, str]:
    """Get SIP configuration from environment variables."""
    required = ["SIP_SERVER", "SIP_USERNAME", "SIP_PASSWORD"]

    for var in required:
        value = os.getenv(var)
        if not value:
            print(f"Error: {var} environment variable not set", file=sys.stderr)
            print("\nRequired environment variables:", file=sys.stderr)
            print("  SIP_SERVER     - SIP server hostname", file=sys.stderr)
            print("  SIP_USERNAME   - SIP username", file=sys.stderr)
            print("  SIP_PASSWORD   - SIP password", file=sys.stderr)
            print("\nOptional:", file=sys.stderr)
            print("  SIP_PORT       - SIP port (default: 5060)", file=sys.stderr)
            print("  SIP_DID        - Your DID/phone number", file=sys.stderr)
            sys.exit(1)

    return {
        "server": os.getenv("SIP_SERVER", ""),
        "username": os.getenv("SIP_USERNAME", ""),
        "password": os.getenv("SIP_PASSWORD", ""),
        "port": int(os.getenv("SIP_PORT", "5060")),
        "did": os.getenv("SIP_DID", "Unknown"),
    }


def get_audio_config() -> dict:
    """Get audio configuration from environment variables."""
    return {
        "device_name": os.getenv("AUDIO_DEVICE"),  # None = auto-detect USB
        "auto_start": os.getenv("AUDIO_AUTO_START", "").lower() in ("1", "true", "yes"),
        "input_gain": float(os.getenv("AUDIO_INPUT_GAIN", "1.0")),
        "output_volume": float(os.getenv("AUDIO_OUTPUT_VOLUME", "1.0")),
        "ringer_sound_file": os.getenv("RINGER_SOUND_FILE"),  # None = GPIO toggle only
    }


class RealPhoneTestHarness:
    """Interactive test harness for phone system with real SIP."""

    def __init__(self) -> None:
        """Initialize the test harness with mock GPIO and real SIP."""
        self.gpio = MockGPIO()
        self.sip_config = get_sip_config()
        self.audio_config = get_audio_config()

        print(f"SIP Server: {self.sip_config['server']}:{self.sip_config['port']}")
        print(f"SIP Username: {self.sip_config['username']}")
        print(f"DID: {self.sip_config['did']}")
        print()

        # Audio configuration
        print("Audio Configuration:")
        print(f"  Device:       {self.audio_config['device_name'] or 'auto-detect USB'}")
        print(f"  Auto-start:   {'YES' if self.audio_config['auto_start'] else 'NO'}")
        print(f"  Input gain:   {self.audio_config['input_gain']:.1f}")
        print(f"  Output vol:   {self.audio_config['output_volume']:.1f}")
        ringer_sound = self.audio_config['ringer_sound_file']
        print(f"  Ringer sound: {ringer_sound or '(none - GPIO toggle only)'}")
        print()

        # Create mock config
        config = Mock()
        config.get.side_effect = lambda key, default=None: {
            "timing.inter_digit_timeout": 3.0,
            "speed_dial": {},
            "allowlist": ["*"],
        }.get(key, default)
        config.get_speed_dial.return_value = None
        config.is_allowed.return_value = True
        config.get_sip_config.return_value = self.sip_config

        # Create hardware components with MockGPIO
        self.hook_monitor = HookMonitor(gpio=self.gpio)
        self.dial_reader = DialReader(gpio=self.gpio)
        self.ringer = Ringer(
            gpio=self.gpio,
            ring_on_duration=2.0,
            ring_off_duration=4.0,
            sound_file=self.audio_config["ringer_sound_file"],
        )

        # Create REAL SIP client
        self.sip_client = PyVoIPClient()

        # Create call manager
        self.call_manager = CallManager(
            config=config,
            hook_monitor=self.hook_monitor,
            dial_reader=self.dial_reader,
            ringer=self.ringer,
            sip_client=self.sip_client,
        )

        # State monitoring
        self._last_state = PhoneState.IDLE
        self._monitor_thread = None
        self._monitor_running = False

        # Audio file playback control
        self._stop_audio = threading.Event()
        self._audio_thread = None

        # USB audio handler for bidirectional audio during calls
        self._audio_handler = AudioHandler(
            device_name=self.audio_config["device_name"],
            input_gain=self.audio_config["input_gain"],
            output_volume=self.audio_config["output_volume"],
        )
        self._usb_audio_auto_start = self.audio_config["auto_start"]

        # Audio recording state
        self._recording = False
        self._recording_thread: Optional[threading.Thread] = None
        self._recording_file: Optional[str] = None

        # Start the system
        print("Starting phone system...")
        self.call_manager.start()
        time.sleep(0.5)  # Give system time to register with SIP server

        # Start state monitor
        self._start_state_monitor()

    def _start_state_monitor(self) -> None:
        """Start background thread to monitor state changes."""
        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._state_monitor, daemon=True)
        self._monitor_thread.start()

    def _state_monitor(self) -> None:
        """Background thread that monitors for incoming calls."""
        while self._monitor_running:
            current_state = self.call_manager.get_state()

            # Detect incoming call (transition to RINGING)
            if current_state == PhoneState.RINGING and self._last_state != PhoneState.RINGING:
                print("\n")
                print("=" * 60)
                print("📞 INCOMING CALL!")
                print("=" * 60)
                print("Type 'u' to pick up the phone and answer")
                print("=" * 60)
                print()

            # Detect call answered
            elif current_state == PhoneState.CONNECTED and self._last_state == PhoneState.RINGING:
                print("\n✓ Call answered and connected!")
                if self._usb_audio_auto_start:
                    self._auto_start_usb_audio()
                print()

            # Detect call connected (outgoing)
            elif current_state == PhoneState.CONNECTED and self._last_state == PhoneState.CALLING:
                print("\n✓ Outgoing call connected!")
                if self._usb_audio_auto_start:
                    self._auto_start_usb_audio()
                print()

            # Detect call ended
            elif current_state == PhoneState.IDLE and self._last_state in (
                PhoneState.CONNECTED,
                PhoneState.CALLING,
                PhoneState.RINGING,
            ):
                # Stop recording if in progress
                if self._recording:
                    self._recording = False
                    if self._recording_thread:
                        self._recording_thread.join(timeout=2.0)
                        self._recording_thread = None
                # Stop USB audio if running
                if self._audio_handler.is_running():
                    self._audio_handler.stop()
                    print("  USB audio stopped")
                print("\n✓ Call ended")
                print()

            self._last_state = current_state
            time.sleep(0.1)  # Check 10 times per second

    def stop(self) -> None:
        """Stop the phone system."""
        self._monitor_running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)
        # Stop recording if in progress
        if self._recording:
            self._recording = False
            if self._recording_thread:
                self._recording_thread.join(timeout=2.0)
        # Stop USB audio if running
        if self._audio_handler.is_running():
            self._audio_handler.stop()
        self.call_manager.stop()

    def _auto_start_usb_audio(self) -> None:
        """Auto-start USB audio when call connects (if enabled)."""
        voip_call = self.sip_client.get_current_call()
        if voip_call and not self._audio_handler.is_running():
            try:
                self._audio_handler.start(voip_call)
                print("  USB audio auto-started (mic + speaker)")
            except Exception as e:
                print(f"  ✗ Failed to auto-start USB audio: {e}")

    def start_usb_audio(self) -> None:
        """Start USB audio for the current call (bidirectional mic + speaker)."""
        if self._audio_handler.is_running():
            print("  USB audio already running")
            return

        state = self.call_manager.get_state()
        if state != PhoneState.CONNECTED:
            print(f"  ✗ Cannot start USB audio - not in a call (state: {state.value})")
            return

        voip_call = self.sip_client.get_current_call()
        if not voip_call:
            print("  ✗ No active VoIP call found")
            return

        try:
            print("→ Starting USB audio (mic + speaker)...")
            self._audio_handler.start(voip_call)
            print("✓ USB audio started - you can now speak and listen")
        except Exception as e:
            print(f"✗ Failed to start USB audio: {e}")

    def stop_usb_audio(self) -> None:
        """Stop USB audio."""
        if not self._audio_handler.is_running():
            print("  USB audio not running")
            return

        print("→ Stopping USB audio...")
        self._audio_handler.stop()
        print("✓ USB audio stopped")

    def start_recording(self, output_file: Optional[str] = None) -> None:
        """Start recording incoming audio to a WAV file.

        Records the raw audio from the VoIP call (before any resampling/playback)
        for debugging purposes.

        Args:
            output_file: Optional path for output WAV file. If not provided,
                         generates a timestamped filename in current directory.
        """
        if self._recording:
            print("  Recording already in progress")
            return

        state = self.call_manager.get_state()
        if state != PhoneState.CONNECTED:
            print(f"  ✗ Cannot record - not in a call (state: {state.value})")
            return

        voip_call = self.sip_client.get_current_call()
        if not voip_call:
            print("  ✗ No active VoIP call found")
            return

        # Generate filename if not provided
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"call_recording_{timestamp}.wav"

        self._recording_file = output_file
        self._recording = True

        def _record_loop() -> None:
            """Background thread that records audio from VoIP to WAV file."""
            frames = []
            raw_bytes = []  # Also capture raw bytes for debugging
            voip_sample_rate = 8000
            frame_size = 160  # 160 bytes = 160 samples at 8-bit = 20ms at 8kHz

            print(f"→ Recording to: {self._recording_file}")
            print("  Recording 8kHz 8-bit unsigned linear PCM from pyVoIP...")

            while self._recording:
                try:
                    # read_audio returns 8-bit unsigned linear PCM (0x80 = silence)
                    unsigned_8bit = voip_call.read_audio(frame_size, blocking=True)
                    if unsigned_8bit:
                        raw_bytes.append(unsigned_8bit)
                        # Convert 8-bit unsigned -> 16-bit signed for WAV file
                        # Subtract 128 to convert unsigned to signed
                        signed_8bit = audioop.bias(unsigned_8bit, 1, -128)
                        # Convert 8-bit to 16-bit
                        pcm_16bit = audioop.lin2lin(signed_8bit, 1, 2)
                        frames.append(pcm_16bit)
                except Exception as e:
                    if self._recording:  # Only log if we weren't stopping
                        print(f"  Recording error: {e}")
                    break

            # Write WAV file
            if frames:
                try:
                    with wave.open(self._recording_file, "wb") as wf:
                        wf.setnchannels(1)  # Mono
                        wf.setsampwidth(2)  # 16-bit
                        wf.setframerate(voip_sample_rate)  # 8kHz
                        wf.writeframes(b"".join(frames))

                    duration = len(frames) * 0.02  # 20ms per frame
                    print(f"✓ Recording saved: {self._recording_file}")
                    print(f"  Duration: {duration:.1f}s, Frames: {len(frames)}")

                    # Also save raw bytes for debugging
                    raw_file = self._recording_file.replace(".wav", "_raw.bin")
                    with open(raw_file, "wb") as rf:
                        rf.write(b"".join(raw_bytes))
                    print(f"  Raw 8-bit unsigned bytes saved to: {raw_file}")

                    # Analyze raw bytes
                    all_raw = b"".join(raw_bytes)
                    from collections import Counter
                    byte_counts = Counter(all_raw)
                    print(f"\n  === Raw byte analysis (8-bit unsigned, 0x80=silence) ===")
                    print(f"  Total bytes: {len(all_raw)}")
                    print(f"  Unique byte values: {len(byte_counts)}")
                    print(f"  Top 5 most common bytes:")
                    for byte_val, count in byte_counts.most_common(5):
                        pct = count / len(all_raw) * 100
                        # Show signed equivalent (subtract 128)
                        signed_val = byte_val - 128
                        print(f"    0x{byte_val:02X} ({byte_val:3d}): {count:6d} ({pct:5.1f}%) = signed {signed_val:+4d}")

                except Exception as e:
                    print(f"✗ Failed to save recording: {e}")
            else:
                print("  No audio was captured")

        self._recording_thread = threading.Thread(target=_record_loop, daemon=True)
        self._recording_thread.start()

    def stop_recording(self) -> None:
        """Stop recording and save the WAV file."""
        if not self._recording:
            print("  No recording in progress")
            return

        print("→ Stopping recording...")
        self._recording = False

        if self._recording_thread:
            self._recording_thread.join(timeout=2.0)
            self._recording_thread = None

    def hook_off(self) -> None:
        """Simulate picking up the phone."""
        print("→ Picking up phone (hook off)")
        self.gpio.set_input(HOOK, MockGPIO.LOW)
        time.sleep(0.1)

    def hook_on(self) -> None:
        """Simulate hanging up the phone."""
        print("→ Hanging up phone (hook on)")
        self.gpio.set_input(HOOK, MockGPIO.HIGH)
        time.sleep(0.1)

    def dial_digit(self, digit: str) -> None:
        """Simulate dialing a digit.

        Args:
            digit: Digit to dial (0-9)
        """
        if not digit.isdigit():
            print(f"✗ Invalid digit: {digit}")
            return

        print(f"→ Dialing digit: {digit}")
        pulses = 10 if digit == "0" else int(digit)
        for _ in range(pulses):
            self.gpio.set_input(DIAL_PULSE, MockGPIO.LOW)
            time.sleep(0.02)
            self.gpio.set_input(DIAL_PULSE, MockGPIO.HIGH)
            time.sleep(0.02)
        # Wait longer than pulse_timeout (0.2s) to ensure digit is registered
        time.sleep(0.3)

    def dial_number(self, number: str) -> None:
        """Dial a complete phone number.

        Args:
            number: Phone number to dial (digits only)
        """
        for digit in number:
            if digit.isdigit():
                self.dial_digit(digit)
            else:
                print(f"✗ Skipping non-digit: {digit}")
        # Wait for inter-digit timeout to trigger the call
        print("→ Waiting for inter-digit timeout...")

    def send_audio(self, file_path: str) -> None:
        """Send audio from a WAV file through the current call.

        Args:
            file_path: Path to WAV file
        """
        # Stop any currently playing audio
        if self._audio_thread and self._audio_thread.is_alive():
            print("→ Stopping current audio playback...")
            self._stop_audio.set()
            self._audio_thread.join(timeout=1.0)

        # Reset stop flag
        self._stop_audio.clear()

        # Start audio in background thread
        def _play_audio():
            try:
                print(f"→ Sending audio file: {file_path}")
                print("  (Press any key to stop)")
                completed = self.sip_client.send_audio_file(
                    file_path, stop_check=lambda: self._stop_audio.is_set()
                )
                if completed:
                    print("✓ Audio completed successfully")
                else:
                    print("⏸ Audio stopped")
            except Exception as e:
                print(f"✗ Error sending audio: {e}")

        self._audio_thread = threading.Thread(target=_play_audio, daemon=True)
        self._audio_thread.start()

    def stop_audio(self) -> None:
        """Stop currently playing audio."""
        if self._audio_thread and self._audio_thread.is_alive():
            print("→ Stopping audio playback...")
            self._stop_audio.set()
            self._audio_thread.join(timeout=1.0)
            print("✓ Audio stopped")
        else:
            print("  No audio currently playing")

    def show_status(self) -> None:
        """Display current system status."""
        state = self.call_manager.get_state()
        dialed = self.call_manager.get_dialed_number()
        error = self.call_manager.get_error_message()
        sip_state = self.sip_client.get_call_state()
        hook_state = self.hook_monitor.get_state()
        ringing = self.ringer.is_ringing()
        usb_audio_running = self._audio_handler.is_running()

        print("\n" + "=" * 60)
        print("PHONE SYSTEM STATUS")
        print("=" * 60)
        print(f"Phone State:    {state.value}")
        print(f"Hook State:     {hook_state.value}")
        print(f"SIP State:      {sip_state.value}")
        print(f"Dialed Number:  {dialed or '(none)'}")
        print(f"Ringing:        {'YES' if ringing else 'NO'}")
        print(f"USB Audio:      {'ACTIVE (mic + speaker)' if usb_audio_running else 'OFF'}")
        if self._recording:
            print(f"Recording:      ACTIVE -> {self._recording_file}")
        else:
            print("Recording:      OFF")
        if error:
            print(f"Error:          {error}")
        print("=" * 60 + "\n")


def print_menu() -> None:
    """Print the interactive menu."""
    print("\n" + "─" * 60)
    print("COMMANDS:")
    print("  u     - Pick up phone (hook off)")
    print("  d     - Hang up phone (hook on)")
    print("  0-9   - Dial single digit")
    print("  c     - Call a number (dial complete number)")
    print()
    print("USB AUDIO (bidirectional mic + speaker):")
    print("  m     - Start USB audio (mic + speaker for real conversation)")
    print("  n     - Stop USB audio")
    print()
    print("RECORDING (capture raw VoIP audio for debugging):")
    print("  r     - Start recording incoming audio to WAV file")
    print("  t     - Stop recording and save file")
    print()
    print("AUDIO FILE PLAYBACK:")
    print("  a     - Send audio file (WAV) to call")
    print("  x     - Stop audio file playback")
    print()
    print("OTHER:")
    print("  s     - Show status")
    print("  h     - Show this help")
    print("  q     - Quit")
    print()
    print("NOTES:")
    print("  - To receive calls, have someone call your DID")
    print("  - To make calls, pick up (u), dial digits, then wait 3 seconds")
    print("  - Or use 'c' command to dial a complete number at once")
    print("  - Set AUDIO_AUTO_START=1 in .env.test to auto-start USB audio")
    print("─" * 60)


def main() -> None:
    """Run the interactive test harness."""
    print("=" * 60)
    print("ROTARY PHONE TEST HARNESS - REAL SIP MODE")
    print("=" * 60)
    print()
    print("WARNING: This connects to a REAL SIP provider!")
    print("Make sure your credentials in .env.test are correct.")
    print()

    harness = RealPhoneTestHarness()

    print("✓ System initialized and registered with SIP server")
    harness.show_status()
    print_menu()

    try:
        while True:
            try:
                cmd = input("\nCommand> ").strip().lower()

                # Stop any playing audio when user types something (except empty input)
                if cmd and harness._audio_thread and harness._audio_thread.is_alive():
                    harness._stop_audio.set()

                if cmd == "q":
                    print("Shutting down...")
                    break
                elif cmd == "u":
                    harness.hook_off()
                    harness.show_status()
                elif cmd == "d":
                    harness.hook_on()
                    harness.show_status()
                elif cmd.isdigit() and len(cmd) == 1:
                    harness.dial_digit(cmd)
                    harness.show_status()
                elif cmd == "c":
                    number = input("  Enter number to call: ").strip()
                    if number:
                        print("  Picking up phone...")
                        harness.hook_off()
                        time.sleep(0.5)
                        print(f"  Dialing {number}...")
                        harness.dial_number(number)
                        harness.show_status()
                    else:
                        print("  ✗ No number entered")
                elif cmd == "m":
                    harness.start_usb_audio()
                elif cmd == "n":
                    harness.stop_usb_audio()
                elif cmd == "r":
                    file_path = input("  Output file (Enter for auto): ").strip()
                    harness.start_recording(file_path if file_path else None)
                elif cmd == "t":
                    harness.stop_recording()
                elif cmd == "a":
                    file_path = input("  Enter WAV file path: ").strip()
                    if file_path:
                        harness.send_audio(file_path)
                    else:
                        print("  ✗ No file path entered")
                elif cmd == "x":
                    harness.stop_audio()
                elif cmd == "s":
                    harness.show_status()
                elif cmd == "h":
                    print_menu()
                elif cmd == "":
                    continue
                else:
                    print(f"✗ Unknown command: {cmd}")
                    print("  Type 'h' for help")

            except KeyboardInterrupt:
                print("\n\nShutting down...")
                break
            except EOFError:
                print("\n\nShutting down...")
                break

    finally:
        harness.stop()
        print("✓ Shutdown complete")


if __name__ == "__main__":
    main()
