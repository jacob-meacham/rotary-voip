"""Configuration manager for loading and validating config files."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration is invalid."""

    pass


class ConfigManager:
    """Manages loading and accessing configuration from YAML files."""

    def __init__(self, user_config_path: Optional[str] = None) -> None:
        """Initialize the configuration manager.

        Args:
            user_config_path: Path to user config file (overrides defaults)
        """
        self._config: Dict[str, Any] = {}
        self._user_config_path = user_config_path
        self._load_config()

    def _get_default_config_path(self) -> Path:
        """Get the path to the default configuration file.

        Returns:
            Path to default_config.yaml
        """
        return Path(__file__).parent / "default_config.yaml"

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
            with open(path, "r") as f:
                content = yaml.safe_load(f)
                return content if content is not None else {}
        except FileNotFoundError:
            raise ConfigError(f"Config file not found: {path}")
        except yaml.YAMLError as e:
            raise ConfigError(f"Failed to parse YAML file {path}: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load config file {path}: {e}")

    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge two configuration dictionaries.

        Args:
            base: Base configuration (defaults)
            override: Override configuration (user settings)

        Returns:
            Merged configuration dictionary
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = self._merge_configs(result[key], value)
            else:
                # Override value
                result[key] = value

        return result

    def _validate_config(self) -> None:
        """Validate the loaded configuration.

        Raises:
            ConfigError: If configuration is invalid
        """
        # Check required top-level sections
        required_sections = ["sip", "hardware", "timing", "audio"]
        for section in required_sections:
            if section not in self._config:
                raise ConfigError(f"Missing required config section: {section}")

        # Validate SIP settings
        sip = self._config["sip"]
        if not isinstance(sip, dict):
            raise ConfigError("'sip' section must be a dictionary")

        # Note: server/username/password can be empty in mock mode, so we don't require them
        # They'll be validated at runtime when actually making calls

        # Validate hardware pins are integers
        hardware = self._config["hardware"]
        if not isinstance(hardware, dict):
            raise ConfigError("'hardware' section must be a dictionary")

        for pin_name in [
            "pin_hook",
            "pin_dial_pulse",
            "pin_dial_active",
            "pin_ringer",
            "pin_low_battery",
        ]:
            if pin_name not in hardware:
                raise ConfigError(f"Missing required hardware setting: {pin_name}")
            if not isinstance(hardware[pin_name], int):
                raise ConfigError(f"Hardware '{pin_name}' must be an integer")

        # Validate timing values are positive numbers
        timing = self._config["timing"]
        if not isinstance(timing, dict):
            raise ConfigError("'timing' section must be a dictionary")

        for timing_name in [
            "debounce_time",
            "pulse_timeout",
            "inter_digit_timeout",
            "ring_duration",
            "ring_pause",
        ]:
            if timing_name not in timing:
                raise ConfigError(f"Missing required timing setting: {timing_name}")
            value = timing[timing_name]
            if not isinstance(value, (int, float)):
                raise ConfigError(f"Timing '{timing_name}' must be a number")
            if value <= 0:
                raise ConfigError(f"Timing '{timing_name}' must be positive")

        # Validate speed_dial is a dict (can be empty)
        if "speed_dial" in self._config:
            if not isinstance(self._config["speed_dial"], dict):
                raise ConfigError("'speed_dial' must be a dictionary")

        # Validate whitelist is a list (can be empty)
        if "whitelist" in self._config:
            if not isinstance(self._config["whitelist"], list):
                raise ConfigError("'whitelist' must be a list")

    def _load_config(self) -> None:
        """Load configuration from default and user files."""
        # Load default config
        default_path = self._get_default_config_path()
        logger.debug(f"Loading default config from: {default_path}")
        default_config = self._load_yaml_file(default_path)

        # Try to load user config if path provided
        if self._user_config_path:
            user_path = Path(self._user_config_path)
            if user_path.exists():
                logger.info(f"Loading user config from: {user_path}")
                user_config = self._load_yaml_file(user_path)
                self._config = self._merge_configs(default_config, user_config)
            else:
                logger.warning(f"User config file not found: {user_path}, using defaults only")
                self._config = default_config
        else:
            self._config = default_config

        # Validate the merged configuration
        self._validate_config()
        logger.info("Configuration loaded and validated successfully")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key.

        Supports dot notation for nested values (e.g., 'sip.server')

        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def get_speed_dial(self, code: str) -> Optional[str]:
        """Get the phone number for a speed dial code.

        Args:
            code: Speed dial code (e.g., "11")

        Returns:
            Phone number or None if code not found
        """
        speed_dial = self.get("speed_dial", {})
        return speed_dial.get(code)

    def is_whitelisted(self, number: str) -> bool:
        """Check if a phone number is whitelisted.

        Args:
            number: Phone number to check

        Returns:
            True if number is whitelisted or whitelist contains "*"
        """
        whitelist: List[str] = self.get("whitelist", [])

        # Check for wildcard
        if "*" in whitelist:
            return True

        # Check if number is in whitelist
        return number in whitelist

    def get_sip_config(self) -> Dict[str, Any]:
        """Get SIP configuration.

        Returns:
            SIP configuration dictionary
        """
        return self.get("sip", {})

    def get_hardware_config(self) -> Dict[str, Any]:
        """Get hardware configuration.

        Returns:
            Hardware configuration dictionary
        """
        return self.get("hardware", {})

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
