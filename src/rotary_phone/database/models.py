"""Data models for call logging."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class CallLog:  # pylint: disable=too-many-instance-attributes
    """Represents a logged phone call.

    Attributes:
        id: Database primary key (None for new records)
        timestamp: When the call started (UTC)
        direction: "inbound" or "outbound"
        caller_id: Caller ID for inbound calls
        dialed_number: Original number dialed (before speed dial expansion)
        destination: Final destination number (after speed dial expansion)
        speed_dial_code: Speed dial code used (e.g., "11"), or None
        status: Final call status (completed/missed/failed/rejected)
        duration_seconds: Call duration in seconds (0 if not answered)
        answered_at: When call was answered (None if not answered)
        ended_at: When call ended
        error_message: Error description if call failed
    """

    timestamp: datetime
    direction: str
    status: str
    id: Optional[int] = None
    caller_id: Optional[str] = None
    dialed_number: Optional[str] = None
    destination: Optional[str] = None
    speed_dial_code: Optional[str] = None
    duration_seconds: int = 0
    answered_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    error_message: Optional[str] = None

    @classmethod
    def from_row(cls, row: Any) -> "CallLog":
        """Create CallLog from a sqlite3.Row or similar mapping.

        Args:
            row: Database row with column access by name

        Returns:
            CallLog instance
        """

        def parse_datetime(value: Optional[str]) -> Optional[datetime]:
            if value is None:
                return None
            return datetime.fromisoformat(value)

        return cls(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            direction=row["direction"],
            caller_id=row["caller_id"],
            dialed_number=row["dialed_number"],
            destination=row["destination"],
            speed_dial_code=row["speed_dial_code"],
            status=row["status"],
            duration_seconds=row["duration_seconds"] or 0,
            answered_at=parse_datetime(row["answered_at"]),
            ended_at=parse_datetime(row["ended_at"]),
            error_message=row["error_message"],
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary with all fields, datetimes as ISO strings
        """

        def format_datetime(dt: Optional[datetime]) -> Optional[str]:
            if dt is None:
                return None
            return dt.isoformat()

        return {
            "id": self.id,
            "timestamp": format_datetime(self.timestamp),
            "direction": self.direction,
            "caller_id": self.caller_id,
            "dialed_number": self.dialed_number,
            "destination": self.destination,
            "speed_dial_code": self.speed_dial_code,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "answered_at": format_datetime(self.answered_at),
            "ended_at": format_datetime(self.ended_at),
            "error_message": self.error_message,
        }


@dataclass
class User:
    """Represents a user account for web admin authentication.

    Attributes:
        id: Database primary key (None for new records)
        username: Unique username
        password_hash: Bcrypt hashed password
        created_at: When the account was created
    """

    username: str
    password_hash: str
    created_at: datetime
    id: Optional[int] = None

    @classmethod
    def from_row(cls, row: Any) -> "User":
        """Create User from a sqlite3.Row or similar mapping.

        Args:
            row: Database row with column access by name

        Returns:
            User instance
        """
        return cls(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def to_dict(self, include_password_hash: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Args:
            include_password_hash: Whether to include the password hash
                (should be False for API responses)

        Returns:
            Dictionary with user fields
        """
        result = {
            "id": self.id,
            "username": self.username,
            "created_at": self.created_at.isoformat(),
        }
        if include_password_hash:
            result["password_hash"] = self.password_hash
        return result
