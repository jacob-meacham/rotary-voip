"""Tests for the USB audio handler."""

from unittest.mock import MagicMock, patch

import pytest

from rotary_phone.audio.audio_handler import (
    FRAME_SIZE,
    SAMPLE_RATE,
    AudioDeviceNotFoundError,
    AudioError,
    AudioHandler,
)


class TestAudioHandlerInitialization:
    """Tests for AudioHandler initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        handler = AudioHandler()
        assert handler._device_name is None
        assert handler._input_gain == 1.0
        assert handler._output_volume == 1.0
        assert not handler.is_running()

    def test_init_with_explicit_device(self) -> None:
        """Test initialization with explicit device name."""
        handler = AudioHandler(device_name="USB Audio Device")
        assert handler._device_name == "USB Audio Device"

    def test_init_with_custom_gain_and_volume(self) -> None:
        """Test initialization with custom gain and volume."""
        handler = AudioHandler(input_gain=1.5, output_volume=0.8)
        assert handler._input_gain == 1.5
        assert handler._output_volume == 0.8

    def test_init_with_invalid_gain_raises(self) -> None:
        """Test that invalid gain raises ValueError."""
        with pytest.raises(ValueError, match="input_gain must be between"):
            AudioHandler(input_gain=3.0)

        with pytest.raises(ValueError, match="input_gain must be between"):
            AudioHandler(input_gain=-0.5)

    def test_init_with_invalid_volume_raises(self) -> None:
        """Test that invalid volume raises ValueError."""
        with pytest.raises(ValueError, match="output_volume must be between"):
            AudioHandler(output_volume=2.5)

        with pytest.raises(ValueError, match="output_volume must be between"):
            AudioHandler(output_volume=-1.0)

    def test_init_with_boundary_values(self) -> None:
        """Test initialization with boundary values (0.0 and 2.0)."""
        handler = AudioHandler(input_gain=0.0, output_volume=2.0)
        assert handler._input_gain == 0.0
        assert handler._output_volume == 2.0


class TestAudioDeviceDetection:
    """Tests for audio device detection."""

    @patch("rotary_phone.audio.audio_handler.AudioHandler._find_audio_devices")
    def test_finds_usb_device(self, mock_find_devices: MagicMock) -> None:
        """Test that USB devices are found correctly."""
        mock_find_devices.return_value = (0, 1)

        with patch("pyaudio.PyAudio") as mock_pyaudio:
            mock_pa = MagicMock()
            mock_pyaudio.return_value = mock_pa
            mock_pa.open.return_value = MagicMock()

            handler = AudioHandler()
            mock_call = MagicMock()
            handler.start(mock_call)

            mock_find_devices.assert_called_once()

            handler.stop()

    @patch("pyaudio.PyAudio")
    def test_auto_detect_usb_in_device_name(self, mock_pyaudio: MagicMock) -> None:
        """Test auto-detection of USB devices by name."""
        mock_pa = MagicMock()
        mock_pyaudio.return_value = mock_pa
        mock_pa.get_device_count.return_value = 3
        mock_pa.get_device_info_by_index.side_effect = [
            {"name": "Built-in Audio", "maxInputChannels": 2, "maxOutputChannels": 2},
            {"name": "USB Audio Device", "maxInputChannels": 1, "maxOutputChannels": 2},
            {"name": "HDMI Output", "maxInputChannels": 0, "maxOutputChannels": 8},
        ]
        mock_pa.open.return_value = MagicMock()

        handler = AudioHandler()
        mock_call = MagicMock()

        # Start should auto-detect the USB device
        handler.start(mock_call)

        assert handler._input_device_index == 1
        assert handler._output_device_index == 1

        handler.stop()

    @patch("pyaudio.PyAudio")
    def test_explicit_device_name_match(self, mock_pyaudio: MagicMock) -> None:
        """Test explicit device name matching with full-featured device."""
        mock_pa = MagicMock()
        mock_pyaudio.return_value = mock_pa
        mock_pa.get_device_count.return_value = 2
        mock_pa.get_device_info_by_index.side_effect = [
            {"name": "Built-in Audio", "maxInputChannels": 2, "maxOutputChannels": 2},
            {"name": "Special USB Audio", "maxInputChannels": 1, "maxOutputChannels": 2},
        ]
        mock_pa.open.return_value = MagicMock()

        handler = AudioHandler(device_name="Special USB")
        mock_call = MagicMock()

        handler.start(mock_call)

        # Should match "Special USB Audio" for both input and output
        assert handler._input_device_index == 1
        assert handler._output_device_index == 1

        handler.stop()

    @patch("pyaudio.PyAudio")
    def test_no_usb_device_uses_default(self, mock_pyaudio: MagicMock) -> None:
        """Test fallback to default devices when no USB found."""
        mock_pa = MagicMock()
        mock_pyaudio.return_value = mock_pa
        mock_pa.get_device_count.return_value = 1
        mock_pa.get_device_info_by_index.return_value = {
            "name": "Built-in Audio",
            "maxInputChannels": 2,
            "maxOutputChannels": 2,
        }
        mock_pa.get_default_input_device_info.return_value = {
            "name": "Built-in Audio",
            "index": 0,
        }
        mock_pa.get_default_output_device_info.return_value = {
            "name": "Built-in Audio",
            "index": 0,
        }
        mock_pa.open.return_value = MagicMock()

        handler = AudioHandler()  # Auto-detect
        mock_call = MagicMock()

        handler.start(mock_call)

        # Should fall back to default
        assert handler._input_device_index == 0
        assert handler._output_device_index == 0

        handler.stop()

    @patch("pyaudio.PyAudio")
    def test_explicit_device_not_found_raises(self, mock_pyaudio: MagicMock) -> None:
        """Test that explicit device not found raises error."""
        mock_pa = MagicMock()
        mock_pyaudio.return_value = mock_pa
        mock_pa.get_device_count.return_value = 1
        mock_pa.get_device_info_by_index.return_value = {
            "name": "Built-in Audio",
            "maxInputChannels": 2,
            "maxOutputChannels": 2,
        }

        handler = AudioHandler(device_name="NonexistentDevice")
        mock_call = MagicMock()

        with pytest.raises(AudioDeviceNotFoundError, match="NonexistentDevice"):
            handler.start(mock_call)


class TestAudioLifecycle:
    """Tests for audio handler start/stop lifecycle."""

    @patch("pyaudio.PyAudio")
    def test_start_stop_cycle(self, mock_pyaudio: MagicMock) -> None:
        """Test basic start/stop cycle."""
        mock_pa = MagicMock()
        mock_pyaudio.return_value = mock_pa
        mock_pa.get_device_count.return_value = 1
        mock_pa.get_device_info_by_index.return_value = {
            "name": "USB Audio",
            "maxInputChannels": 1,
            "maxOutputChannels": 2,
        }
        mock_stream = MagicMock()
        mock_pa.open.return_value = mock_stream

        handler = AudioHandler()
        mock_call = MagicMock()

        assert not handler.is_running()

        handler.start(mock_call)
        assert handler.is_running()
        assert handler._voip_call == mock_call

        handler.stop()
        assert not handler.is_running()
        assert handler._voip_call is None

    @patch("pyaudio.PyAudio")
    def test_start_twice_ignored(self, mock_pyaudio: MagicMock) -> None:
        """Test that starting twice is ignored."""
        mock_pa = MagicMock()
        mock_pyaudio.return_value = mock_pa
        mock_pa.get_device_count.return_value = 1
        mock_pa.get_device_info_by_index.return_value = {
            "name": "USB Audio",
            "maxInputChannels": 1,
            "maxOutputChannels": 2,
        }
        mock_pa.open.return_value = MagicMock()

        handler = AudioHandler()
        mock_call = MagicMock()

        handler.start(mock_call)

        # Second start should be ignored (no error)
        handler.start(mock_call)

        assert handler.is_running()

        handler.stop()

    @patch("pyaudio.PyAudio")
    def test_stop_when_not_running(self, mock_pyaudio: MagicMock) -> None:
        """Test that stop when not running does nothing."""
        handler = AudioHandler()

        # Should not raise
        handler.stop()
        assert not handler.is_running()

    @patch("pyaudio.PyAudio")
    def test_stop_cleans_up_resources(self, mock_pyaudio: MagicMock) -> None:
        """Test that stop properly cleans up resources."""
        mock_pa = MagicMock()
        mock_pyaudio.return_value = mock_pa
        mock_pa.get_device_count.return_value = 1
        mock_pa.get_device_info_by_index.return_value = {
            "name": "USB Audio",
            "maxInputChannels": 1,
            "maxOutputChannels": 2,
        }
        mock_stream = MagicMock()
        mock_pa.open.return_value = mock_stream

        handler = AudioHandler()
        mock_call = MagicMock()

        handler.start(mock_call)
        handler.stop()

        # PyAudio should be terminated
        mock_pa.terminate.assert_called_once()


class TestAudioFormatConstants:
    """Tests for audio format constants."""

    def test_sample_rate(self) -> None:
        """Test sample rate constant."""
        assert SAMPLE_RATE == 8000

    def test_frame_size(self) -> None:
        """Test frame size constant."""
        assert FRAME_SIZE == 160


class TestAudioErrors:
    """Tests for audio error handling."""

    def test_audio_error_base(self) -> None:
        """Test AudioError base exception."""
        err = AudioError("test error")
        assert str(err) == "test error"

    def test_audio_device_not_found_error(self) -> None:
        """Test AudioDeviceNotFoundError exception."""
        err = AudioDeviceNotFoundError("device not found")
        assert str(err) == "device not found"
        assert isinstance(err, AudioError)

    @patch("pyaudio.PyAudio", side_effect=ImportError("No module named 'pyaudio'"))
    def test_pyaudio_import_error(self, mock_pyaudio: MagicMock) -> None:
        """Test error when PyAudio is not installed."""
        handler = AudioHandler()
        mock_call = MagicMock()

        with pytest.raises(AudioError, match="PyAudio not installed"):
            handler.start(mock_call)
