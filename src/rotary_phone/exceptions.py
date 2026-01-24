"""Custom exception hierarchy for the rotary phone system.

This module provides a structured exception hierarchy that enables more
specific error handling throughout the codebase.
"""

from __future__ import annotations


class RotaryPhoneError(Exception):
    """Base exception for all rotary phone errors.

    All custom exceptions in this project should inherit from this class.
    This allows catching all project-specific errors with a single except clause.
    """


class ConfigError(RotaryPhoneError):
    """Configuration-related errors.

    Raised when there are issues with configuration files, validation,
    or config management operations.
    """


class HardwareError(RotaryPhoneError):
    """Hardware-related errors.

    Raised when there are issues with GPIO, dial reader, hook monitor,
    ringer, or other hardware components.
    """


class GPIOError(HardwareError):
    """GPIO-specific errors.

    Raised when there are issues initializing or communicating with GPIO pins.
    """


class DialReaderError(HardwareError):
    """Dial reader errors.

    Raised when there are issues reading pulses from the rotary dial.
    """


class RingerError(HardwareError):
    """Ringer control errors.

    Raised when there are issues controlling the ringer or playing sounds.
    """


class SIPError(RotaryPhoneError):
    """SIP/VoIP-related errors.

    Base class for all SIP client errors.
    """


class SIPRegistrationError(SIPError):
    """SIP registration errors.

    Raised when the SIP client fails to register with the VoIP provider.
    """

    def __init__(self, message: str, server: str | None = None) -> None:
        """Initialize registration error.

        Args:
            message: Error description
            server: SIP server that registration failed with
        """
        self.server = server
        super().__init__(message)


class SIPCallError(SIPError):
    """SIP call errors.

    Raised when there are issues making or receiving calls.
    """

    def __init__(
        self,
        message: str,
        number: str | None = None,
        direction: str | None = None,
    ) -> None:
        """Initialize call error.

        Args:
            message: Error description
            number: Phone number involved in the failed call
            direction: Call direction ('inbound' or 'outbound')
        """
        self.number = number
        self.direction = direction
        super().__init__(message)


class SIPTimeoutError(SIPError):
    """SIP timeout errors.

    Raised when a SIP operation times out.
    """

    def __init__(self, message: str, operation: str | None = None) -> None:
        """Initialize timeout error.

        Args:
            message: Error description
            operation: The operation that timed out (e.g., 'registration', 'call')
        """
        self.operation = operation
        super().__init__(message)


class SIPAuthenticationError(SIPError):
    """SIP authentication errors.

    Raised when SIP credentials are invalid or authentication fails.
    """


class NetworkError(RotaryPhoneError):
    """Network-related errors.

    Raised when there are issues with WiFi, network connectivity,
    or access point operations.
    """


class WiFiError(NetworkError):
    """WiFi-specific errors.

    Raised when there are issues connecting to or managing WiFi networks.
    """


class AccessPointError(NetworkError):
    """Access point errors.

    Raised when there are issues starting or managing the AP mode.
    """


class AudioError(RotaryPhoneError):
    """Audio-related errors.

    Raised when there are issues with audio playback, recording,
    or audio device management.
    """


class DatabaseError(RotaryPhoneError):
    """Database-related errors.

    Raised when there are issues with call log storage or retrieval.
    """
