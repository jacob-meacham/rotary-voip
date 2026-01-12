"""Tests for configuration manager."""

import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from rotary_phone.config import ConfigManager
from rotary_phone.config.config_manager import ConfigError


def get_minimal_valid_config() -> Dict[str, Any]:
    """Get a minimal valid configuration for testing."""
    return {
        "sip": {
            "server": "",
            "username": "",
            "password": "",
            "port": 5060,
            "stun_server": "stun.voip.ms",
        },
        "speed_dial": {},
        "allowlist": [],
        "timing": {
            "inter_digit_timeout": 2.0,
            "ring_duration": 2.0,
            "ring_pause": 4.0,
        },
        "audio": {
            "ring_sound": "sounds/ring.wav",
            "dial_tone": "sounds/dialtone.wav",
            "busy_tone": "sounds/busy.wav",
            "error_tone": "sounds/error.wav",
        },
        "database": {"path": "calls.db", "cleanup_days": 365},
        "logging": {"level": "INFO", "file": "", "max_bytes": 10485760, "backup_count": 3},
        "web": {"enabled": False, "host": "0.0.0.0", "port": 7474},
    }


def create_temp_config(config_dict: Dict[str, Any]) -> str:
    """Create a temporary config file and return its path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config_dict, f)
        return f.name


def test_missing_config_file_raises_error() -> None:
    """Test that missing config file raises ConfigError."""
    with pytest.raises(ConfigError, match="Configuration file not found"):
        ConfigManager(user_config_path="nonexistent.yaml")


def test_load_valid_config() -> None:
    """Test that valid config can be loaded."""
    config_dict = get_minimal_valid_config()
    config_path = create_temp_config(config_dict)

    try:
        config = ConfigManager(user_config_path=config_path)

        # Verify required sections exist
        assert config.get("sip") is not None
        assert config.get("timing") is not None
        assert config.get("audio") is not None
        assert config.get("speed_dial") is not None
        assert config.get("allowlist") is not None
    finally:
        Path(config_path).unlink()


def test_get_with_dot_notation() -> None:
    """Test getting nested config values with dot notation."""
    config_dict = get_minimal_valid_config()
    config_path = create_temp_config(config_dict)

    try:
        config = ConfigManager(user_config_path=config_path)

        # Test accessing nested values
        assert config.get("sip.port") == 5060
        assert config.get("timing.inter_digit_timeout") == 2.0
        assert config.get("timing.ring_duration") == 2.0
    finally:
        Path(config_path).unlink()


def test_get_with_default() -> None:
    """Test that get() returns default when key not found."""
    config_dict = get_minimal_valid_config()
    config_path = create_temp_config(config_dict)

    try:
        config = ConfigManager(user_config_path=config_path)

        assert config.get("nonexistent.key", "default") == "default"
        assert config.get("sip.nonexistent", 999) == 999
    finally:
        Path(config_path).unlink()


def test_user_config_values() -> None:
    """Test that user config values are loaded correctly."""
    config_dict = get_minimal_valid_config()
    config_dict["sip"]["server"] = "test.server.com"
    config_dict["sip"]["username"] = "testuser"
    config_dict["sip"]["password"] = "testpass"
    config_dict["speed_dial"] = {"11": "+12065551234", "12": "+12065555678"}

    config_path = create_temp_config(config_dict)

    try:
        config = ConfigManager(user_config_path=config_path)

        # Verify user values are loaded
        assert config.get("sip.server") == "test.server.com"
        assert config.get("sip.username") == "testuser"
        assert config.get("sip.password") == "testpass"

        # Verify other values are present
        assert config.get("sip.port") == 5060
        assert config.get("timing.inter_digit_timeout") == 2.0

        # Verify speed dial
        assert config.get("speed_dial.11") == "+12065551234"
    finally:
        Path(config_path).unlink()


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


def test_missing_required_section_raises_error() -> None:
    """Test that missing required section raises ConfigError."""
    config_dict = get_minimal_valid_config()
    del config_dict["sip"]  # Remove required section

    config_path = create_temp_config(config_dict)

    try:
        with pytest.raises(ConfigError, match="Missing required config section: sip"):
            ConfigManager(user_config_path=config_path)
    finally:
        Path(config_path).unlink()


def test_invalid_speed_dial_type_raises_error() -> None:
    """Test that speed_dial as non-dict raises ConfigError."""
    config_dict = get_minimal_valid_config()
    config_dict["speed_dial"] = ["11", "12"]  # Should be dict, not list

    config_path = create_temp_config(config_dict)

    try:
        with pytest.raises(ConfigError, match="'speed_dial' must be a dictionary"):
            ConfigManager(user_config_path=config_path)
    finally:
        Path(config_path).unlink()


def test_invalid_allowlist_type_raises_error() -> None:
    """Test that allowlist as non-list raises ConfigError."""
    config_dict = get_minimal_valid_config()
    config_dict["allowlist"] = {"11": "+12065551234"}  # Should be list, not dict

    config_path = create_temp_config(config_dict)

    try:
        with pytest.raises(ConfigError, match="'allowlist' must be a list"):
            ConfigManager(user_config_path=config_path)
    finally:
        Path(config_path).unlink()


def test_negative_timing_raises_error() -> None:
    """Test that negative timing values raise ConfigError."""
    config_dict = get_minimal_valid_config()
    config_dict["timing"]["inter_digit_timeout"] = -0.01  # Invalid (negative)

    config_path = create_temp_config(config_dict)

    try:
        with pytest.raises(ConfigError, match="must be positive"):
            ConfigManager(user_config_path=config_path)
    finally:
        Path(config_path).unlink()


def test_speed_dial_lookup() -> None:
    """Test speed dial number lookup."""
    config_dict = get_minimal_valid_config()
    config_dict["speed_dial"] = {"11": "+12065551234", "12": "+12065555678"}

    config_path = create_temp_config(config_dict)

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
    config_dict = get_minimal_valid_config()
    config_dict["allowlist"] = ["+12065551234", "+12065555678"]

    config_path = create_temp_config(config_dict)

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
    config_dict = get_minimal_valid_config()
    config_dict["allowlist"] = ["*"]

    config_path = create_temp_config(config_dict)

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
    config_dict = get_minimal_valid_config()
    config_path = create_temp_config(config_dict)

    try:
        config = ConfigManager(user_config_path=config_path)

        sip = config.get_sip_config()
        assert isinstance(sip, dict)
        assert "server" in sip

        timing = config.get_timing_config()
        assert isinstance(timing, dict)
        assert "inter_digit_timeout" in timing
    finally:
        Path(config_path).unlink()


def test_to_dict() -> None:
    """Test getting entire config as dictionary."""
    config_dict = get_minimal_valid_config()
    config_path = create_temp_config(config_dict)

    try:
        config = ConfigManager(user_config_path=config_path)

        config_dict_result = config.to_dict()
        assert isinstance(config_dict_result, dict)
        assert "sip" in config_dict_result
        assert "timing" in config_dict_result
        assert "audio" in config_dict_result
        assert "speed_dial" in config_dict_result
        assert "allowlist" in config_dict_result
    finally:
        Path(config_path).unlink()


def test_to_dict_safe_masks_password() -> None:
    """Test that to_dict_safe() masks sensitive data."""
    config_dict = get_minimal_valid_config()
    config_dict["sip"]["password"] = "supersecret"

    config_path = create_temp_config(config_dict)

    try:
        config = ConfigManager(user_config_path=config_path)

        safe_dict = config.to_dict_safe()
        assert safe_dict["sip"]["password"] == "***MASKED***"

        # Original should still have real password
        regular_dict = config.to_dict()
        assert regular_dict["sip"]["password"] == "supersecret"
    finally:
        Path(config_path).unlink()


def test_update_config() -> None:
    """Test updating configuration values."""
    config_dict = get_minimal_valid_config()
    config_path = create_temp_config(config_dict)

    try:
        config = ConfigManager(user_config_path=config_path)

        # Update some values
        config.update_config({"sip.server": "new.server.com", "sip.port": 5061})

        assert config.get("sip.server") == "new.server.com"
        assert config.get("sip.port") == 5061
    finally:
        Path(config_path).unlink()


def test_save_config() -> None:
    """Test saving configuration to file."""
    config_dict = get_minimal_valid_config()
    config_path = create_temp_config(config_dict)

    try:
        config = ConfigManager(user_config_path=config_path)

        # Update and save
        config.update_config({"sip.server": "saved.server.com"})

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            output_path = f.name

        try:
            config.save_config(output_path)

            # Load the saved file and verify
            config2 = ConfigManager(user_config_path=output_path)
            assert config2.get("sip.server") == "saved.server.com"
        finally:
            Path(output_path).unlink()
    finally:
        Path(config_path).unlink()
