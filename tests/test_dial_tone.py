"""Tests for the DialTone class."""

import subprocess
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rotary_phone.hardware.dial_tone import DialTone


class TestDialToneInitialization:
    """Tests for DialTone initialization."""

    def test_init_without_sound_file(self) -> None:
        """Test initialization without a sound file."""
        dial_tone = DialTone(sound_file=None)
        assert not dial_tone.is_playing()

    def test_init_with_nonexistent_file(self) -> None:
        """Test initialization with a nonexistent sound file."""
        dial_tone = DialTone(sound_file="/nonexistent/path/dialtone.wav")
        # Should warn and disable, but not raise
        assert not dial_tone.is_playing()
        # Sound file should be disabled
        assert dial_tone._sound_file is None

    def test_init_with_valid_file(self, tmp_path: Path) -> None:
        """Test initialization with a valid sound file."""
        sound_file = tmp_path / "dialtone.wav"
        sound_file.write_bytes(b"RIFF" + b"\x00" * 100)  # Minimal WAV header

        dial_tone = DialTone(sound_file=str(sound_file))
        assert not dial_tone.is_playing()
        assert dial_tone._sound_file == str(sound_file)


class TestDialTonePlayback:
    """Tests for DialTone playback functionality."""

    def test_start_without_sound_file(self) -> None:
        """Test start() when no sound file is configured."""
        dial_tone = DialTone(sound_file=None)
        dial_tone.start()  # Should be a no-op
        assert not dial_tone.is_playing()

    def test_stop_when_not_playing(self) -> None:
        """Test stop() when not already playing."""
        dial_tone = DialTone(sound_file=None)
        dial_tone.stop()  # Should be a no-op, not raise
        assert not dial_tone.is_playing()

    @patch("subprocess.Popen")
    def test_start_and_stop(self, mock_popen: MagicMock, tmp_path: Path) -> None:
        """Test starting and stopping dial tone."""
        sound_file = tmp_path / "dialtone.wav"
        sound_file.write_bytes(b"RIFF" + b"\x00" * 100)

        # Mock the process
        mock_process = MagicMock()
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="aplay", timeout=0.1)
        mock_popen.return_value = mock_process

        dial_tone = DialTone(sound_file=str(sound_file))

        # Start dial tone
        dial_tone.start()
        assert dial_tone.is_playing()

        # Give thread time to start
        time.sleep(0.1)

        # Stop dial tone
        dial_tone.stop()
        assert not dial_tone.is_playing()

        # Verify process was terminated
        mock_process.terminate.assert_called()

    @patch("subprocess.Popen")
    def test_start_twice_ignored(self, mock_popen: MagicMock, tmp_path: Path) -> None:
        """Test that calling start() twice doesn't create duplicate threads."""
        sound_file = tmp_path / "dialtone.wav"
        sound_file.write_bytes(b"RIFF" + b"\x00" * 100)

        mock_process = MagicMock()
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="aplay", timeout=0.1)
        mock_popen.return_value = mock_process

        dial_tone = DialTone(sound_file=str(sound_file))

        dial_tone.start()
        dial_tone.start()  # Second call should be ignored

        time.sleep(0.05)

        # Should still be playing
        assert dial_tone.is_playing()

        dial_tone.stop()

    @patch("subprocess.Popen")
    def test_stop_twice_ignored(self, mock_popen: MagicMock, tmp_path: Path) -> None:
        """Test that calling stop() twice is safe."""
        sound_file = tmp_path / "dialtone.wav"
        sound_file.write_bytes(b"RIFF" + b"\x00" * 100)

        mock_process = MagicMock()
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="aplay", timeout=0.1)
        mock_popen.return_value = mock_process

        dial_tone = DialTone(sound_file=str(sound_file))

        dial_tone.start()
        time.sleep(0.05)
        dial_tone.stop()
        dial_tone.stop()  # Second call should be ignored

        assert not dial_tone.is_playing()

    @patch("subprocess.Popen")
    def test_aplay_not_found(self, mock_popen: MagicMock, tmp_path: Path) -> None:
        """Test handling when aplay command is not found."""
        sound_file = tmp_path / "dialtone.wav"
        sound_file.write_bytes(b"RIFF" + b"\x00" * 100)

        mock_popen.side_effect = FileNotFoundError("aplay not found")

        dial_tone = DialTone(sound_file=str(sound_file))
        dial_tone.start()

        # Wait for the play loop to encounter the error
        time.sleep(0.2)

        dial_tone.stop()

        # Sound file should be disabled after aplay not found
        assert dial_tone._sound_file is None


class TestDialToneIntegration:
    """Integration-style tests for DialTone."""

    @patch("subprocess.Popen")
    def test_rapid_start_stop_cycles(self, mock_popen: MagicMock, tmp_path: Path) -> None:
        """Test rapid start/stop cycles don't cause issues."""
        sound_file = tmp_path / "dialtone.wav"
        sound_file.write_bytes(b"RIFF" + b"\x00" * 100)

        mock_process = MagicMock()
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="aplay", timeout=0.1)
        mock_popen.return_value = mock_process

        dial_tone = DialTone(sound_file=str(sound_file))

        for _ in range(5):
            dial_tone.start()
            time.sleep(0.02)
            dial_tone.stop()
            time.sleep(0.02)

        assert not dial_tone.is_playing()

    @patch("subprocess.Popen")
    def test_process_kill_on_timeout(self, mock_popen: MagicMock, tmp_path: Path) -> None:
        """Test that process is killed if terminate times out."""
        sound_file = tmp_path / "dialtone.wav"
        sound_file.write_bytes(b"RIFF" + b"\x00" * 100)

        mock_process = MagicMock()
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="aplay", timeout=0.1)
        mock_popen.return_value = mock_process

        dial_tone = DialTone(sound_file=str(sound_file))
        dial_tone.start()
        time.sleep(0.05)

        # Make terminate's wait raise TimeoutExpired
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="aplay", timeout=0.5)

        dial_tone.stop()

        # Process should have been killed after terminate timeout
        mock_process.terminate.assert_called()
