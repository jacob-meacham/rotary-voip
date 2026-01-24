"""Pydantic models for configuration validation.

These models provide strong type validation and automatic coercion
for all configuration sections.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, SecretStr, field_validator


class SIPConfig(BaseModel):
    """SIP/VoIP connection configuration."""

    server: str = Field(description="SIP server hostname or IP")
    port: int = Field(default=5060, ge=1, le=65535, description="SIP server port")
    username: str = Field(description="SIP username")
    password: SecretStr = Field(description="SIP password")
    stun_server: Optional[str] = Field(default=None, description="STUN server for NAT traversal")


class TimingConfig(BaseModel):
    """Timing configuration for dial and call operations."""

    inter_digit_timeout: float = Field(
        default=2.0, gt=0, description="Seconds to wait between digits"
    )
    pulse_timeout: float = Field(default=0.3, gt=0, description="Seconds for pulse detection")
    hook_debounce_time: float = Field(
        default=0.01, ge=0, description="Seconds for hook switch debounce"
    )
    ring_duration: float = Field(default=2.0, gt=0, description="Seconds to play ring sound")
    ring_pause: float = Field(default=4.0, gt=0, description="Seconds between ring cycles")
    sip_registration_timeout: float = Field(
        default=10.0, gt=0, description="Seconds to wait for SIP registration"
    )
    call_attempt_timeout: float = Field(
        default=60.0, gt=0, description="Seconds before giving up on outgoing call"
    )


class AudioConfig(BaseModel):
    """Audio configuration for sounds and USB audio device."""

    ring_sound: str = Field(default="sounds/ring.wav", description="Path to ring sound file")
    dial_tone: str = Field(default="sounds/dialtone.wav", description="Path to dial tone file")
    busy_tone: str = Field(default="sounds/busy.wav", description="Path to busy tone file")
    error_tone: str = Field(default="sounds/error.wav", description="Path to error tone file")
    usb_device: Optional[str] = Field(default=None, description="USB audio device name")
    input_gain: float = Field(default=1.0, ge=0, le=10.0, description="Microphone input gain")
    output_volume: float = Field(default=1.0, ge=0, le=10.0, description="Speaker output volume")


class DatabaseConfig(BaseModel):
    """Database configuration for call logs."""

    path: str = Field(default="data/data.db", description="Path to SQLite database file")
    cleanup_days: int = Field(
        default=365, gt=0, description="Delete call logs older than this many days"
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)")
    file: str = Field(default="", description="Log file path (empty for console only)")
    max_bytes: int = Field(default=10485760, gt=0, description="Max log file size in bytes")
    backup_count: int = Field(default=3, ge=0, description="Number of backup log files to keep")

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return upper


class WebConfig(BaseModel):
    """Web admin interface configuration."""

    enabled: bool = Field(default=True, description="Enable web admin interface")
    host: str = Field(default="0.0.0.0", description="Web server host address")
    port: int = Field(default=7474, ge=1, le=65535, description="Web server port")
    ssl_certfile: Optional[str] = Field(default=None, description="Path to SSL certificate file")
    ssl_keyfile: Optional[str] = Field(default=None, description="Path to SSL private key file")


class AppConfig(BaseModel):
    """Complete application configuration.

    This model validates the entire config file structure and provides
    sensible defaults for all optional fields.
    """

    sip: SIPConfig
    timing: TimingConfig = Field(default_factory=TimingConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    speed_dial: Dict[str, str] = Field(default_factory=dict, description="Speed dial mappings")
    allowlist: List[str] = Field(default_factory=list, description="Allowed phone numbers")

    @field_validator("speed_dial")
    @classmethod
    def validate_speed_dial(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Validate speed dial codes are 1-2 digits."""
        for code in v.keys():
            if not code.isdigit() or len(code) > 2:
                raise ValueError(f"Invalid speed dial code: {code}. Must be 1-2 digits.")
        return v

    @field_validator("allowlist")
    @classmethod
    def validate_allowlist(cls, v: List[str]) -> List[str]:
        """Validate allowlist entries."""
        for entry in v:
            if entry != "*" and not entry.startswith("+"):
                # Allow numbers without + prefix but warn (could add stricter validation)
                pass
        return v

    def to_dict_safe(self) -> Dict[str, Any]:
        """Convert to dictionary with sensitive data masked."""
        result = self.model_dump()
        # Mask SIP password
        if "sip" in result and "password" in result["sip"]:
            result["sip"]["password"] = "********"
        return result
