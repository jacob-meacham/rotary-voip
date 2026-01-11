"""Tests for configuration manager."""

import tempfile
from pathlib import Path

import pytest
import yaml

from rotary_phone.config import ConfigManager
from rotary_phone.config.config_manager import ConfigError


def test_load_default_config() -> None:
    """Test that default config can be loaded."""
    config = ConfigManager()

    # Verify required sections exist
    assert config.get("sip") is not None
    assert config.get("timing") is not None
    assert config.get("audio") is not None
    assert config.get("speed_dial") is not None
    assert config.get("allowlist") is not None


def test_get_with_dot_notation() -> None:
    """Test getting nested config values with dot notation."""
    config = ConfigManager()

    # Test accessing nested values
    assert config.get("sip.port") == 5060
    assert config.get("timing.pulse_timeout") == 0.3
    assert config.get("timing.inter_digit_timeout") == 2.0


def test_get_with_default() -> None:
    """Test that get() returns default when key not found."""
    config = ConfigManager()

    assert config.get("nonexistent.key", "default") == "default"
    assert config.get("sip.nonexistent", 999) == 999


def test_merge_user_config() -> None:
    """Test that user config overrides default config."""
    # Create a temporary user config
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        user_config = {
            "sip": {"server": "test.server.com", "username": "testuser", "password": "testpass"},
            "speed_dial": {"11": "+12065551234", "12": "+12065555678"},
        }
        yaml.dump(user_config, f)
        user_config_path = f.name

    try:
        config = ConfigManager(user_config_path=user_config_path)

        # Verify user values override defaults
        assert config.get("sip.server") == "test.server.com"
        assert config.get("sip.username") == "testuser"
        assert config.get("sip.password") == "testpass"

        # Verify default values are still present for non-overridden keys
        assert config.get("sip.port") == 5060  # From default
        assert config.get("timing.pulse_timeout") == 0.3  # From default

        # Verify speed dial was added
        assert config.get("speed_dial.11") == "+12065551234"
    finally:
        Path(user_config_path).unlink()


def test_invalid_yaml_raises_error() -> None:
    """Test that invalid YAML raises ConfigError."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("invalid: yaml: content: [[[")
        invalid_path = f.name

    try:
        with pytest.raises(ConfigError, match="Failed to parse YAML"):
            ConfigManager(user_config_path=invalid_path)
    finally:
        Path(invalid_path).unlink()


def test_invalid_speed_dial_type_raises_error() -> None:
    """Test that speed_dial as non-dict raises ConfigError."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        # Config with speed_dial as a list instead of dict
        bad_config = {"speed_dial": ["11", "12"]}  # Should be dict, not list
        yaml.dump(bad_config, f)
        config_path = f.name

    try:
        with pytest.raises(ConfigError, match="'speed_dial' must be a dictionary"):
            ConfigManager(user_config_path=config_path)
    finally:
        Path(config_path).unlink()


def test_invalid_allowlist_type_raises_error() -> None:
    """Test that allowlist as non-list raises ConfigError."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        # Config with allowlist as a dict instead of list
        bad_config = {"allowlist": {"11": "+12065551234"}}  # Should be list, not dict
        yaml.dump(bad_config, f)
        config_path = f.name

    try:
        with pytest.raises(ConfigError, match="'allowlist' must be a list"):
            ConfigManager(user_config_path=config_path)
    finally:
        Path(config_path).unlink()


def test_negative_timing_raises_error() -> None:
    """Test that negative timing values raise ConfigError."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        bad_config = {
            "timing": {
                "debounce_time": -0.01,  # Invalid (negative)
                "pulse_timeout": 0.3,
                "inter_digit_timeout": 2.0,
                "ring_duration": 2.0,
                "ring_pause": 4.0,
            },
        }
        yaml.dump(bad_config, f)
        config_path = f.name

    try:
        with pytest.raises(ConfigError, match="must be positive"):
            ConfigManager(user_config_path=config_path)
    finally:
        Path(config_path).unlink()


def test_speed_dial_lookup() -> None:
    """Test speed dial number lookup."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        user_config = {"speed_dial": {"11": "+12065551234", "12": "+12065555678"}}
        yaml.dump(user_config, f)
        config_path = f.name

    try:
        config = ConfigManager(user_config_path=config_path)

        # Test successful lookup
        assert config.get_speed_dial("11") == "+12065551234"
        assert config.get_speed_dial("12") == "+12065555678"

        # Test lookup for non-existent code
        assert config.get_speed_dial("99") is None
    finally:
        Path(config_path).unlink()


def test_allowlist_check() -> None:
    """Test allowlist number checking."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        user_config = {"allowlist": ["+12065551234", "+12065555678"]}
        yaml.dump(user_config, f)
        config_path = f.name

    try:
        config = ConfigManager(user_config_path=config_path)

        # Test numbers in allowlist
        assert config.is_allowed("+12065551234") is True
        assert config.is_allowed("+12065555678") is True

        # Test number not in allowlist
        assert config.is_allowed("+19995551111") is False
    finally:
        Path(config_path).unlink()


def test_allowlist_wildcard() -> None:
    """Test that wildcard '*' allows all numbers."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        user_config = {"allowlist": ["*"]}
        yaml.dump(user_config, f)
        config_path = f.name

    try:
        config = ConfigManager(user_config_path=config_path)

        # Any number should be allowed
        assert config.is_allowed("+12065551234") is True
        assert config.is_allowed("+19995551111") is True
        assert config.is_allowed("911") is True
    finally:
        Path(config_path).unlink()


def test_get_section_configs() -> None:
    """Test helper methods for getting config sections."""
    config = ConfigManager()

    sip = config.get_sip_config()
    assert isinstance(sip, dict)
    assert "server" in sip

    timing = config.get_timing_config()
    assert isinstance(timing, dict)
    assert "pulse_timeout" in timing


def test_to_dict() -> None:
    """Test getting entire config as dictionary."""
    config = ConfigManager()

    config_dict = config.to_dict()
    assert isinstance(config_dict, dict)
    assert "sip" in config_dict
    assert "timing" in config_dict
    assert "audio" in config_dict
    assert "speed_dial" in config_dict
    assert "allowlist" in config_dict
