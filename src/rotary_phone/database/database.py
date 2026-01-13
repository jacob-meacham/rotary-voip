"""SQLite database operations for call logging."""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from rotary_phone.database.models import CallLog, User

logger = logging.getLogger(__name__)


class Database:
    """SQLite database for storing call logs.

    Thread-safe via connection-per-operation pattern. Each database operation
    creates its own connection, ensuring safe concurrent access from multiple
    threads (e.g., CallManager callbacks).
    """

    def __init__(self, db_path: str) -> None:
        """Initialize the database.

        Args:
            db_path: Path to SQLite database file. Created if doesn't exist.
        """
        self._db_path = db_path
        logger.debug("Database initialized with path: %s", db_path)

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection.

        Creates a new connection per operation for thread safety.
        Uses Row factory for dict-like column access.

        Yields:
            sqlite3 connection
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create tables and indexes if they don't exist."""
        # Ensure parent directory exists
        db_dir = Path(self._db_path).parent
        if db_dir and not db_dir.exists():
            db_dir.mkdir(parents=True, exist_ok=True)

        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS call_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    caller_id TEXT,
                    dialed_number TEXT,
                    destination TEXT,
                    speed_dial_code TEXT,
                    status TEXT NOT NULL,
                    duration_seconds INTEGER DEFAULT 0,
                    answered_at TEXT,
                    ended_at TEXT,
                    error_message TEXT
                )
            """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_call_logs_timestamp ON call_logs(timestamp)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_call_logs_status ON call_logs(status)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_call_logs_direction ON call_logs(direction)"
            )

            # Create users table for authentication
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

            conn.commit()
            logger.info("Database initialized at %s", self._db_path)

    def add_call(self, call: CallLog) -> int:
        """Insert a call record.

        Args:
            call: CallLog to insert (id field is ignored)

        Returns:
            ID of the inserted record
        """

        def format_dt(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO call_logs (
                    timestamp, direction, caller_id, dialed_number, destination,
                    speed_dial_code, status, duration_seconds, answered_at,
                    ended_at, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    call.timestamp.isoformat(),
                    call.direction,
                    call.caller_id,
                    call.dialed_number,
                    call.destination,
                    call.speed_dial_code,
                    call.status,
                    call.duration_seconds,
                    format_dt(call.answered_at),
                    format_dt(call.ended_at),
                    call.error_message,
                ),
            )
            conn.commit()
            call_id = cursor.lastrowid or 0
            logger.debug("Added call log with id=%d", call_id)
            return call_id

    def get_call(self, call_id: int) -> Optional[CallLog]:
        """Get a single call by ID.

        Args:
            call_id: Call record ID

        Returns:
            CallLog if found, None otherwise
        """
        with self._connection() as conn:
            cursor = conn.execute("SELECT * FROM call_logs WHERE id = ?", (call_id,))
            row = cursor.fetchone()
            if row:
                return CallLog.from_row(row)
            return None

    def get_recent_calls(self, limit: int = 50) -> List[CallLog]:
        """Get most recent calls.

        Args:
            limit: Maximum number of calls to return

        Returns:
            List of CallLog, newest first
        """
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM call_logs ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            return [CallLog.from_row(row) for row in cursor.fetchall()]

    def search_calls(  # pylint: disable=too-many-positional-arguments,too-many-arguments
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        direction: Optional[str] = None,
        status: Optional[str] = None,
        number_pattern: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CallLog]:
        """Search calls with filters.

        Args:
            start_date: Only calls on or after this date
            end_date: Only calls on or before this date
            direction: Filter by direction ("inbound" or "outbound")
            status: Filter by status ("completed", "missed", etc.)
            number_pattern: Filter by number (matches caller_id, dialed_number, or destination)
            limit: Maximum number of results
            offset: Number of records to skip (for pagination)

        Returns:
            List of matching CallLog, newest first
        """
        query = "SELECT * FROM call_logs WHERE 1=1"
        params: List[Any] = []

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        if direction:
            query += " AND direction = ?"
            params.append(direction)

        if status:
            query += " AND status = ?"
            params.append(status)

        if number_pattern:
            query += """ AND (
                caller_id LIKE ? OR
                dialed_number LIKE ? OR
                destination LIKE ?
            )"""
            pattern = f"%{number_pattern}%"
            params.extend([pattern, pattern, pattern])

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)

        with self._connection() as conn:
            cursor = conn.execute(query, params)
            return [CallLog.from_row(row) for row in cursor.fetchall()]

    def get_call_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get call statistics for dashboard.

        Args:
            days: Number of days to include in stats

        Returns:
            Dictionary with statistics:
            - total_calls: Total number of calls
            - by_status: Count per status (completed, missed, failed, rejected)
            - by_direction: Count per direction (inbound, outbound)
            - total_duration_seconds: Sum of all call durations
            - avg_duration_seconds: Average call duration (completed calls only)
        """
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        with self._connection() as conn:
            # Total calls
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM call_logs WHERE timestamp >= ?",
                (cutoff,),
            )
            total_calls = cursor.fetchone()["count"]

            # By status
            cursor = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM call_logs
                WHERE timestamp >= ?
                GROUP BY status
            """,
                (cutoff,),
            )
            by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

            # By direction
            cursor = conn.execute(
                """
                SELECT direction, COUNT(*) as count
                FROM call_logs
                WHERE timestamp >= ?
                GROUP BY direction
            """,
                (cutoff,),
            )
            by_direction = {row["direction"]: row["count"] for row in cursor.fetchall()}

            # Duration stats
            cursor = conn.execute(
                """
                SELECT
                    SUM(duration_seconds) as total,
                    AVG(duration_seconds) as avg
                FROM call_logs
                WHERE timestamp >= ? AND status = 'completed'
            """,
                (cutoff,),
            )
            duration_row = cursor.fetchone()
            total_duration = duration_row["total"] or 0
            avg_duration = duration_row["avg"] or 0

            return {
                "total_calls": total_calls,
                "by_status": by_status,
                "by_direction": by_direction,
                "total_duration_seconds": total_duration,
                "avg_duration_seconds": round(avg_duration, 1),
            }

    def cleanup_old_calls(self, days: int = 365) -> int:
        """Delete calls older than specified days.

        Args:
            days: Delete calls older than this many days

        Returns:
            Number of records deleted
        """
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM call_logs WHERE timestamp < ?",
                (cutoff,),
            )
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info("Deleted %d call logs older than %d days", deleted, days)
            return deleted

    def count_calls(self) -> int:
        """Get total number of call records.

        Returns:
            Total count of call logs
        """
        with self._connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as count FROM call_logs")
            result = cursor.fetchone()
            return int(result["count"]) if result else 0

    def delete_call(self, call_id: int) -> bool:
        """Delete a call record by ID.

        Args:
            call_id: ID of the call record to delete

        Returns:
            True if a record was deleted, False if not found
        """
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM call_logs WHERE id = ?", (call_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.debug("Deleted call log with id=%d", call_id)
            return deleted

    # User management methods for authentication

    def add_user(self, user: User) -> int:
        """Insert a user record.

        Args:
            user: User to insert (id field is ignored)

        Returns:
            ID of the inserted record

        Raises:
            sqlite3.IntegrityError: If username already exists
        """
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (username, password_hash, created_at)
                VALUES (?, ?, ?)
            """,
                (user.username, user.password_hash, user.created_at.isoformat()),
            )
            conn.commit()
            user_id = cursor.lastrowid or 0
            logger.info("Added user with id=%d, username=%s", user_id, user.username)
            return user_id

    def get_user(self, user_id: int) -> Optional[User]:
        """Get a single user by ID.

        Args:
            user_id: User record ID

        Returns:
            User if found, None otherwise
        """
        with self._connection() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return User.from_row(row)
            return None

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a single user by username.

        Args:
            username: Username to lookup

        Returns:
            User if found, None otherwise
        """
        with self._connection() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row:
                return User.from_row(row)
            return None

    def list_users(self) -> List[User]:
        """Get all users.

        Returns:
            List of all users
        """
        with self._connection() as conn:
            cursor = conn.execute("SELECT * FROM users ORDER BY created_at ASC")
            return [User.from_row(row) for row in cursor.fetchall()]

    def delete_user(self, username: str) -> bool:
        """Delete a user by username.

        Args:
            username: Username of the user to delete

        Returns:
            True if a user was deleted, False if not found
        """
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info("Deleted user: %s", username)
            return deleted

    def count_users(self) -> int:
        """Get total number of users.

        Returns:
            Total count of users
        """
        with self._connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as count FROM users")
            result = cursor.fetchone()
            return int(result["count"]) if result else 0
