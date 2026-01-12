"""Tests for ringer component."""

import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from rotary_phone.hardware import RINGER
from rotary_phone.hardware.gpio_abstraction import GPIO, MockGPIO
from rotary_phone.hardware.ringer import Ringer


# Tests - Basic Functionality


def test_ringer_initial_state(mock_gpio: MockGPIO) -> None:
    """Test ringer starts in off state."""
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.05, ring_off_duration=0.05)

    assert not ringer.is_ringing()
    assert mock_gpio.input(RINGER) == GPIO.LOW


def test_ringer_start_ringing(mock_gpio: MockGPIO) -> None:
    """Test starting the ringer."""
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.05, ring_off_duration=0.05)

    ringer.start_ringing()
    time.sleep(0.01)  # Brief delay to let timer start

    assert ringer.is_ringing()
    assert mock_gpio.input(RINGER) == GPIO.HIGH


def test_ringer_stop_ringing(mock_gpio: MockGPIO) -> None:
    """Test stopping the ringer."""
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.05, ring_off_duration=0.05)

    ringer.start_ringing()
    time.sleep(0.01)
    assert ringer.is_ringing()

    ringer.stop_ringing()

    assert not ringer.is_ringing()
    assert mock_gpio.input(RINGER) == GPIO.LOW


def test_ringer_pattern_timing(mock_gpio: MockGPIO) -> None:
    """Test ring pattern on/off timing."""
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.05, ring_off_duration=0.05)

    ringer.start_ringing()

    # Should be on initially
    time.sleep(0.01)
    assert mock_gpio.input(RINGER) == GPIO.HIGH

    # Should turn off after on_duration
    time.sleep(0.06)
    assert mock_gpio.input(RINGER) == GPIO.LOW

    # Should turn back on after off_duration
    time.sleep(0.06)
    assert mock_gpio.input(RINGER) == GPIO.HIGH

    ringer.stop_ringing()


def test_ringer_multiple_cycles(mock_gpio: MockGPIO) -> None:
    """Test ringer continues cycling through multiple periods."""
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.05, ring_off_duration=0.05)

    ringer.start_ringing()

    # Collect states over time
    states = []
    for _ in range(10):
        states.append(mock_gpio.input(RINGER))
        time.sleep(0.03)

    ringer.stop_ringing()

    # Should have seen both HIGH and LOW states multiple times
    assert GPIO.HIGH in states
    assert GPIO.LOW in states
    # Should have seen at least 2 transitions (changed state at least twice)
    transitions = sum(1 for i in range(1, len(states)) if states[i] != states[i - 1])
    assert transitions >= 2


def test_ringer_multiple_start_stop(mock_gpio: MockGPIO) -> None:
    """Test multiple start/stop cycles."""
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.05, ring_off_duration=0.05)

    # First session
    ringer.start_ringing()
    time.sleep(0.01)
    assert ringer.is_ringing()
    ringer.stop_ringing()
    assert not ringer.is_ringing()

    # Second session
    ringer.start_ringing()
    time.sleep(0.01)
    assert ringer.is_ringing()
    ringer.stop_ringing()
    assert not ringer.is_ringing()


# Tests - Edge Cases


def test_ringer_stop_while_ringing_on(mock_gpio: MockGPIO) -> None:
    """Test stopping during the on phase of ring cycle."""
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.1, ring_off_duration=0.1)

    ringer.start_ringing()
    time.sleep(0.03)  # Stop while still in on phase
    assert mock_gpio.input(RINGER) == GPIO.HIGH

    ringer.stop_ringing()

    assert not ringer.is_ringing()
    assert mock_gpio.input(RINGER) == GPIO.LOW


def test_ringer_stop_while_ringing_off(mock_gpio: MockGPIO) -> None:
    """Test stopping during the off phase of ring cycle."""
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.05, ring_off_duration=0.1)

    ringer.start_ringing()
    time.sleep(0.08)  # Wait until in off phase
    assert mock_gpio.input(RINGER) == GPIO.LOW

    ringer.stop_ringing()

    assert not ringer.is_ringing()
    assert mock_gpio.input(RINGER) == GPIO.LOW


def test_ringer_custom_pattern(mock_gpio: MockGPIO) -> None:
    """Test custom ring pattern durations."""
    # Short on, long off pattern
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.05, ring_off_duration=0.1)

    ringer.start_ringing()

    # Verify short on period
    time.sleep(0.01)
    assert mock_gpio.input(RINGER) == GPIO.HIGH
    time.sleep(0.06)
    assert mock_gpio.input(RINGER) == GPIO.LOW

    # Verify long off period (wait for it to turn back on)
    time.sleep(0.11)
    assert mock_gpio.input(RINGER) == GPIO.HIGH

    ringer.stop_ringing()


def test_ringer_rapid_start_stop(mock_gpio: MockGPIO) -> None:
    """Test rapid start/stop calls."""
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.05, ring_off_duration=0.05)

    # Rapid start/stop
    ringer.start_ringing()
    ringer.stop_ringing()
    ringer.start_ringing()
    ringer.stop_ringing()

    assert not ringer.is_ringing()
    assert mock_gpio.input(RINGER) == GPIO.LOW


def test_ringer_start_already_started(mock_gpio: MockGPIO) -> None:
    """Test calling start when already ringing."""
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.05, ring_off_duration=0.05)

    ringer.start_ringing()
    time.sleep(0.01)
    assert ringer.is_ringing()

    # Try to start again (should be idempotent)
    ringer.start_ringing()
    time.sleep(0.01)

    # Should still be ringing normally
    assert ringer.is_ringing()
    assert mock_gpio.input(RINGER) == GPIO.HIGH

    ringer.stop_ringing()


def test_ringer_stop_already_stopped(mock_gpio: MockGPIO) -> None:
    """Test calling stop when already stopped."""
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.05, ring_off_duration=0.05)

    # Stop when never started
    ringer.stop_ringing()
    assert not ringer.is_ringing()

    # Start and stop
    ringer.start_ringing()
    time.sleep(0.01)
    ringer.stop_ringing()

    # Stop again (should be idempotent)
    ringer.stop_ringing()
    assert not ringer.is_ringing()
    assert mock_gpio.input(RINGER) == GPIO.LOW


def test_ringer_no_ringing_after_stop(mock_gpio: MockGPIO) -> None:
    """Test that ringer stays off after being stopped."""
    ringer = Ringer(gpio=mock_gpio, ring_on_duration=0.03, ring_off_duration=0.03)

    ringer.start_ringing()
    time.sleep(0.02)
    ringer.stop_ringing()

    # Wait through what would have been multiple cycles
    time.sleep(0.1)

    # Should still be off
    assert not ringer.is_ringing()
    assert mock_gpio.input(RINGER) == GPIO.LOW


# Tests - Audio Playback Mode


def test_ringer_with_valid_sound_file(mock_gpio: MockGPIO) -> None:
    """Test ringer initialization with a valid sound file."""
    # Create a temporary sound file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sound_file = f.name

    try:
        ringer = Ringer(
            gpio=mock_gpio,
            ring_on_duration=0.05,
            ring_off_duration=0.05,
            sound_file=sound_file,
        )

        # Should initialize successfully
        assert not ringer.is_ringing()
        assert mock_gpio.input(RINGER) == GPIO.LOW

        # Internal state should have the sound file
        assert ringer._sound_file == sound_file
    finally:
        Path(sound_file).unlink()


def test_ringer_with_missing_sound_file(mock_gpio: MockGPIO) -> None:
    """Test ringer falls back to GPIO toggle when sound file is missing."""
    # Use a non-existent sound file path
    missing_file = "/tmp/nonexistent_ring_sound_12345.wav"

    ringer = Ringer(
        gpio=mock_gpio,
        ring_on_duration=0.05,
        ring_off_duration=0.05,
        sound_file=missing_file,
    )

    # Should fall back to GPIO toggle mode (sound_file set to None)
    assert ringer._sound_file is None

    # Should still work in GPIO toggle mode
    ringer.start_ringing()
    time.sleep(0.01)
    assert ringer.is_ringing()
    assert mock_gpio.input(RINGER) == GPIO.HIGH

    ringer.stop_ringing()


@patch("rotary_phone.hardware.ringer.subprocess.run")
def test_ringer_audio_playback_mode(mock_subprocess_run: MagicMock, mock_gpio: MockGPIO) -> None:
    """Test ringer plays audio file using aplay."""
    # Create a temporary sound file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sound_file = f.name

    try:
        # Mock subprocess.run to simulate successful aplay execution
        mock_subprocess_run.return_value = MagicMock(returncode=0)

        ringer = Ringer(
            gpio=mock_gpio,
            ring_on_duration=0.05,
            ring_off_duration=0.05,
            sound_file=sound_file,
        )

        ringer.start_ringing()
        time.sleep(0.01)  # Let ring loop start

        # Give time for audio playback to execute
        time.sleep(0.06)

        # Verify subprocess.run was called with aplay command
        assert mock_subprocess_run.called
        call_args = mock_subprocess_run.call_args
        assert call_args[0][0] == ["aplay", "-q", sound_file]
        assert call_args[1]["timeout"] == 0.05 + 1.0  # ring_on_duration + 1.0

        # GPIO should have been toggled HIGH for amplifier
        # (May already be LOW if ring cycle completed)

        ringer.stop_ringing()
    finally:
        Path(sound_file).unlink()


@patch("rotary_phone.hardware.ringer.subprocess.run")
def test_ringer_audio_playback_multiple_cycles(
    mock_subprocess_run: MagicMock, mock_gpio: MockGPIO
) -> None:
    """Test ringer audio playback continues for multiple cycles."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sound_file = f.name

    try:
        mock_subprocess_run.return_value = MagicMock(returncode=0)

        ringer = Ringer(
            gpio=mock_gpio,
            ring_on_duration=0.02,
            ring_off_duration=0.02,
            sound_file=sound_file,
        )

        ringer.start_ringing()

        # Wait for multiple cycles
        time.sleep(0.15)

        # Should have called aplay multiple times
        assert mock_subprocess_run.call_count >= 2

        ringer.stop_ringing()
    finally:
        Path(sound_file).unlink()


@patch("rotary_phone.hardware.ringer.subprocess.run")
def test_ringer_audio_timeout_handling(mock_subprocess_run: MagicMock, mock_gpio: MockGPIO) -> None:
    """Test ringer handles subprocess timeout gracefully."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sound_file = f.name

    try:
        # Simulate timeout
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(
            cmd=["aplay", "-q", sound_file], timeout=1.0
        )

        ringer = Ringer(
            gpio=mock_gpio,
            ring_on_duration=0.05,
            ring_off_duration=0.05,
            sound_file=sound_file,
        )

        ringer.start_ringing()
        time.sleep(0.07)

        # Should handle timeout gracefully and turn off GPIO
        assert mock_gpio.input(RINGER) == GPIO.LOW

        ringer.stop_ringing()
    finally:
        Path(sound_file).unlink()


@patch("rotary_phone.hardware.ringer.subprocess.run")
def test_ringer_aplay_not_found(mock_subprocess_run: MagicMock, mock_gpio: MockGPIO) -> None:
    """Test ringer falls back to GPIO toggle when aplay is not found."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sound_file = f.name

    try:
        # Simulate aplay command not found
        mock_subprocess_run.side_effect = FileNotFoundError("aplay not found")

        ringer = Ringer(
            gpio=mock_gpio,
            ring_on_duration=0.05,
            ring_off_duration=0.05,
            sound_file=sound_file,
        )

        ringer.start_ringing()
        time.sleep(0.08)

        # Should fall back to GPIO toggle mode
        # After first error, _sound_file should be set to None
        assert ringer._sound_file is None

        # Should still be able to ring using GPIO toggle
        # GPIO should toggle HIGH/LOW
        assert ringer.is_ringing()

        ringer.stop_ringing()
    finally:
        Path(sound_file).unlink()
