"""Pydantic models for web API request/response validation."""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Sound Settings Models
# =============================================================================


class SoundAssignments(BaseModel):
    """Sound file assignments for different phone events."""

    ring_sound: str = ""
    dial_tone: str = ""
    busy_tone: str = ""
    error_tone: str = ""


class SoundAssignmentsUpdate(BaseModel):
    """Request body for updating sound assignments."""

    assignments: SoundAssignments


# =============================================================================
# Ring & Audio Settings Models
# =============================================================================


class RingSettingsUpdate(BaseModel):
    """Request body for updating ring timing settings."""

    ring_duration: Optional[float] = Field(default=None, gt=0, le=30)
    ring_pause: Optional[float] = Field(default=None, gt=0, le=60)


class AudioGainUpdate(BaseModel):
    """Request body for updating audio gain settings."""

    input_gain: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    output_volume: Optional[float] = Field(default=None, ge=0.0, le=2.0)


# =============================================================================
# Timing Settings Models
# =============================================================================


class TimingSettingsUpdate(BaseModel):
    """Request body for updating timing settings."""

    inter_digit_timeout: Optional[float] = Field(default=None, ge=0.5, le=30.0)
    ring_duration: Optional[float] = Field(default=None, ge=0.5, le=30.0)
    ring_pause: Optional[float] = Field(default=None, ge=0.5, le=60.0)
    pulse_timeout: Optional[float] = Field(default=None, ge=0.05, le=2.0)
    hook_debounce_time: Optional[float] = Field(default=None, ge=0.001, le=1.0)
    sip_registration_timeout: Optional[float] = Field(default=None, ge=1.0, le=120.0)
    call_attempt_timeout: Optional[float] = Field(default=None, ge=5.0, le=300.0)


# =============================================================================
# Logging Settings Models
# =============================================================================

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class LoggingSettingsUpdate(BaseModel):
    """Request body for updating logging settings."""

    level: Optional[LogLevel] = None
    file: Optional[str] = None
    max_bytes: Optional[int] = Field(default=None, ge=1024, le=1073741824)
    backup_count: Optional[int] = Field(default=None, ge=0, le=100)

    @field_validator("level", mode="before")
    @classmethod
    def uppercase_level(cls, v: Optional[str]) -> Optional[str]:
        """Convert level to uppercase."""
        return v.upper() if isinstance(v, str) else v


class LogLevelUpdate(BaseModel):
    """Request body for changing runtime log level."""

    level: LogLevel

    @field_validator("level", mode="before")
    @classmethod
    def uppercase_level(cls, v: str) -> str:
        """Convert level to uppercase."""
        return v.upper() if isinstance(v, str) else v


# =============================================================================
# Allowlist Models
# =============================================================================


def _is_valid_phone_pattern(pattern: str) -> bool:
    """Validate a phone number pattern."""
    if not pattern:
        return False
    cleaned = pattern.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    if not cleaned:
        return False
    if cleaned[0] == "+":
        return len(cleaned) >= 3 and cleaned[1:].isdigit()
    return cleaned.isdigit()


class AllowlistUpdate(BaseModel):
    """Request body for updating the allowlist."""

    allowlist: List[str]

    @field_validator("allowlist")
    @classmethod
    def validate_entries(cls, v: List[str]) -> List[str]:
        """Validate each allowlist entry."""
        for i, entry in enumerate(v):
            if entry != "*" and not _is_valid_phone_pattern(entry):
                raise ValueError(f"Invalid phone pattern at index {i}: '{entry}'")
        return v


# =============================================================================
# Speed Dial Models
# =============================================================================


def _is_valid_speed_dial_code(code: str) -> bool:
    """Validate a speed dial code (1-2 digits)."""
    return len(code) in (1, 2) and code.isdigit()


class SpeedDialEntry(BaseModel):
    """Request body for adding a single speed dial entry."""

    code: str
    number: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        """Validate speed dial code."""
        v = str(v)
        if not _is_valid_speed_dial_code(v):
            raise ValueError(f"Invalid speed dial code '{v}': must be 1-2 digits")
        return v

    @field_validator("number")
    @classmethod
    def validate_number(cls, v: str) -> str:
        """Validate phone number."""
        v = str(v)
        if not _is_valid_phone_pattern(v):
            raise ValueError(f"Invalid phone number: '{v}'")
        return v


class SpeedDialUpdate(BaseModel):
    """Request body for updating entire speed dial configuration."""

    speed_dial: Dict[str, str]

    @field_validator("speed_dial")
    @classmethod
    def validate_entries(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Validate each speed dial entry."""
        for code, number in v.items():
            if not _is_valid_speed_dial_code(code):
                raise ValueError(f"Invalid speed dial code '{code}': must be 1-2 digits")
            if not _is_valid_phone_pattern(number):
                raise ValueError(f"Invalid phone number for speed dial '{code}': '{number}'")
        return v
