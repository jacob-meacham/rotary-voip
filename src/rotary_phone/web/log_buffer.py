"""In-memory log buffer for web admin interface.

This module provides a ring buffer for storing recent log entries
and a custom logging handler to capture logs.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, List, Optional


@dataclass
class LogEntry:
    """A single log entry."""

    timestamp: float
    level: str
    logger_name: str
    message: str
    filename: str
    lineno: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "iso_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.timestamp)),
            "level": self.level,
            "logger": self.logger_name,
            "message": self.message,
            "location": f"{self.filename}:{self.lineno}",
        }


class LogBuffer:
    """Thread-safe ring buffer for log entries.

    Stores recent log entries in memory and supports callbacks for
    real-time streaming.
    """

    def __init__(self, max_entries: int = 1000) -> None:
        """Initialize the log buffer.

        Args:
            max_entries: Maximum number of entries to store
        """
        self._buffer: Deque[LogEntry] = deque(maxlen=max_entries)
        self._lock = threading.RLock()
        self._subscribers: List[Callable[[LogEntry], None]] = []
        self._subscriber_lock = threading.RLock()

    def add(self, entry: LogEntry) -> None:
        """Add a log entry to the buffer.

        Args:
            entry: Log entry to add
        """
        with self._lock:
            self._buffer.append(entry)

        # Notify subscribers (outside lock to prevent deadlocks)
        self._notify_subscribers(entry)

    def get_entries(
        self,
        limit: int = 100,
        level: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[LogEntry]:
        """Get recent log entries.

        Args:
            limit: Maximum number of entries to return
            level: Filter by minimum log level (DEBUG, INFO, WARNING, ERROR)
            search: Filter by message content (case-insensitive)

        Returns:
            List of log entries (most recent first)
        """
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_level = level_order.get(level.upper(), 0) if level else 0

        with self._lock:
            entries = list(self._buffer)

        # Filter by level
        if level:
            entries = [e for e in entries if level_order.get(e.level, 0) >= min_level]

        # Filter by search term
        if search:
            search_lower = search.lower()
            entries = [
                e
                for e in entries
                if search_lower in e.message.lower() or search_lower in e.logger_name.lower()
            ]

        # Return most recent entries first
        entries.reverse()
        return entries[:limit]

    def clear(self) -> None:
        """Clear all entries from the buffer."""
        with self._lock:
            self._buffer.clear()

    def subscribe(self, callback: Callable[[LogEntry], None]) -> None:
        """Subscribe to new log entries.

        Args:
            callback: Function to call when new entry is added
        """
        with self._subscriber_lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[LogEntry], None]) -> None:
        """Unsubscribe from log entries.

        Args:
            callback: Previously registered callback
        """
        with self._subscriber_lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def _notify_subscribers(self, entry: LogEntry) -> None:
        """Notify all subscribers of a new entry."""
        with self._subscriber_lock:
            subscribers = list(self._subscribers)

        for callback in subscribers:
            try:
                callback(entry)
            except Exception:  # pylint: disable=broad-except
                # Don't let subscriber errors break logging
                pass

    def __len__(self) -> int:
        """Return number of entries in buffer."""
        with self._lock:
            return len(self._buffer)


class BufferHandler(logging.Handler):
    """Logging handler that writes to a LogBuffer."""

    def __init__(self, buffer: LogBuffer) -> None:
        """Initialize the handler.

        Args:
            buffer: LogBuffer instance to write to
        """
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the buffer.

        Args:
            record: Log record to emit
        """
        entry = LogEntry(
            timestamp=record.created,
            level=record.levelname,
            logger_name=record.name,
            message=self.format(record) if self.formatter else record.getMessage(),
            filename=record.filename,
            lineno=record.lineno,
        )
        self._buffer.add(entry)


# Global log buffer instance (mutable, not constants)
_log_buffer: Optional[LogBuffer] = None  # pylint: disable=invalid-name
_buffer_handler: Optional[BufferHandler] = None  # pylint: disable=invalid-name


def get_log_buffer() -> LogBuffer:
    """Get or create the global log buffer.

    Returns:
        Global LogBuffer instance
    """
    global _log_buffer  # pylint: disable=global-statement
    if _log_buffer is None:
        _log_buffer = LogBuffer(max_entries=1000)
    return _log_buffer


def install_log_handler(level: int = logging.DEBUG) -> BufferHandler:
    """Install the buffer handler on the root logger.

    Args:
        level: Minimum log level to capture

    Returns:
        The installed BufferHandler
    """
    global _buffer_handler  # pylint: disable=global-statement

    if _buffer_handler is not None:
        return _buffer_handler

    buffer = get_log_buffer()
    handler = BufferHandler(buffer)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))

    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    _buffer_handler = handler
    return handler


def uninstall_log_handler() -> None:
    """Remove the buffer handler from the root logger."""
    global _buffer_handler  # pylint: disable=global-statement

    if _buffer_handler is not None:
        root_logger = logging.getLogger()
        root_logger.removeHandler(_buffer_handler)
        _buffer_handler = None
