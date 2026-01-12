"""Configuration manager for loading and validating config files."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeVar, Union

import yaml

T = TypeVar("T")


logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration is invalid."""


class ConfigManager:
    """Manages loading and accessing configuration from YAML files."""

    def __init__(self, user_config_path: str) -> None:
        """Initialize the configuration manager.

        Args:
            user_config_path: Path to user config file (required)

        Raises:
            ConfigError: If config file doesn't exist or is invalid
        """
        self._config: Dict[str, Any] = {}
        self._user_config_path = user_config_path
        self._load_config()

    def _load_yaml_file(self, path: Path) -> Dict[str, Any]:
        """Load a YAML file and return its contents.

        Args:
            path: Path to YAML file

        Returns:
            Dictionary containing the YAML contents

        Raises:
            ConfigError: If file cannot be read or parsed
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
                return content if content is not None else {}
        except FileNotFoundError as e:
            raise ConfigError(f"Config file not found: {path}") from e
        except yaml.YAMLError as e:
            raise ConfigError(f"Failed to parse YAML file {path}: {e}") from e
        except OSError as e:
            raise ConfigError(f"Failed to load config file {path}: {e}") from e

    def _validate_config(self) -> None:  # pylint: disable=too-many-branches
        """Validate the loaded configuration.

        Raises:
            ConfigError: If configuration is invalid
        """
        # Check required top-level sections
        required_sections = ["sip", "timing", "audio"]
        for section in required_sections:
            if section not in self._config:
                raise ConfigError(f"Missing required config section: {section}")

        # Validate SIP settings
        sip = self._config["sip"]
        if not isinstance(sip, dict):
            raise ConfigError("'sip' section must be a dictionary")

        # Note: server/username/password can be empty in mock mode, so we don't require them
        # They'll be validated at runtime when actually making calls

        # Validate timing values are positive numbers
        timing = self._config["timing"]
        if not isinstance(timing, dict):
            raise ConfigError("'timing' section must be a dictionary")

        # Required timing values
        required_timings = [
            "inter_digit_timeout",
            "ring_duration",
            "ring_pause",
        ]
        for timing_name in required_timings:
            if timing_name not in timing:
                raise ConfigError(f"Missing required timing setting: {timing_name}")
            value = timing[timing_name]
            if not isinstance(value, (int, float)):
                raise ConfigError(f"Timing '{timing_name}' must be a number")
            if value <= 0:
                raise ConfigError(f"Timing '{timing_name}' must be positive")

        # Optional timing values (validated if present)
        optional_timings = [
            "pulse_timeout",
            "hook_debounce_time",
            "sip_registration_timeout",
            "call_attempt_timeout",
        ]
        for timing_name in optional_timings:
            if timing_name in timing:
                value = timing[timing_name]
                if not isinstance(value, (int, float)):
                    raise ConfigError(f"Timing '{timing_name}' must be a number")
                if value <= 0:
                    raise ConfigError(f"Timing '{timing_name}' must be positive")

        # Validate speed_dial is a dict (can be empty)
        if "speed_dial" in self._config:
            if not isinstance(self._config["speed_dial"], dict):
                raise ConfigError("'speed_dial' must be a dictionary")

        # Validate allowlist is a list (can be empty)
        if "allowlist" in self._config:
            if not isinstance(self._config["allowlist"], list):
                raise ConfigError("'allowlist' must be a list")

    def _load_config(self) -> None:
        """Load configuration from user config file.

        Raises:
            ConfigError: If config file doesn't exist or is invalid
        """
        config_path = Path(self._user_config_path)

        # Check if file exists first
        if not config_path.exists():
            raise ConfigError(
                f"Configuration file not found: {config_path}\n"
                f"Please create a config file. See config.yml.example for reference."
            )

        logger.info("Loading configuration from: %s", config_path)
        self._config = self._load_yaml_file(config_path)

        # Validate the configuration
        self._validate_config()
        logger.info("Configuration loaded and validated successfully")

    def get(self, key: str, default: Optional[T] = None) -> Union[Any, T]:
        """Get a configuration value by key.

        Supports dot notation for nested values (e.g., 'sip.server')

        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found

        Returns:
            Configuration value or default (type matches default when provided)
        """
        keys = key.split(".")
        value: Any = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default  # type: ignore[return-value]

        return value

    def get_speed_dial(self, code: str) -> Optional[str]:
        """Get the phone number for a speed dial code.

        Args:
            code: Speed dial code (e.g., "11")

        Returns:
            Phone number or None if code not found
        """
        speed_dial: Dict[str, str] = self.get("speed_dial", {})
        return speed_dial.get(code)

    def is_allowed(self, number: str) -> bool:
        """Check if a phone number is in the allowlist.

        Args:
            number: Phone number to check

        Returns:
            True if number is in allowlist or allowlist contains "*"
        """
        allowlist: List[str] = self.get("allowlist", [])

        # Check for wildcard
        if "*" in allowlist:
            return True

        # Check if number is in allowlist
        return number in allowlist

    def get_sip_config(self) -> Dict[str, Any]:
        """Get SIP configuration.

        Returns:
            SIP configuration dictionary
        """
        return self.get("sip", {})

    def get_timing_config(self) -> Dict[str, Any]:
        """Get timing configuration.

        Returns:
            Timing configuration dictionary
        """
        return self.get("timing", {})

    def to_dict(self) -> Dict[str, Any]:
        """Get the entire configuration as a dictionary.

        Returns:
            Complete configuration dictionary
        """
        return self._config.copy()

    def update_config(self, updates: Dict[str, Any]) -> None:
        """Update configuration values with validation.

        Args:
            updates: Dictionary of config updates (dot notation keys)

        Raises:
            ConfigError: If updates would make config invalid
        """
        # Apply updates to _config
        for key, value in updates.items():
            keys = key.split(".")
            d = self._config
            for k in keys[:-1]:
                d = d.setdefault(k, {})
            d[keys[-1]] = value

        # Validate before accepting changes
        self._validate_config()

    def save_config(self, output_path: str) -> None:
        """Save current configuration to YAML file (atomic write).

        Args:
            output_path: Path to save configuration file

        Raises:
            ConfigError: If save fails
        """
        # pylint: disable=import-outside-toplevel
        import os
        import shutil
        import tempfile

        tmp_path = None
        try:
            # Write to temp file first (atomic operation)
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".yaml", encoding="utf-8"
            ) as tmp:
                yaml.dump(self._config, tmp, default_flow_style=False, allow_unicode=True)
                tmp_path = tmp.name

            # Atomic rename
            shutil.move(tmp_path, output_path)
            logger.info("Configuration saved to %s", output_path)

        except Exception as e:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise ConfigError(f"Failed to save config: {e}") from e

    def to_dict_safe(self) -> Dict[str, Any]:
        """Export config with sensitive data masked.

        Returns:
            Config dict with passwords masked
        """
        # pylint: disable=import-outside-toplevel
        import copy

        config = copy.deepcopy(self._config)
        # Mask SIP password
        if "sip" in config and "password" in config["sip"]:
            config["sip"]["password"] = "***MASKED***"
        return config
