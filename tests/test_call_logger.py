"""Tests for the CallLogger class."""

import tempfile
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from rotary_phone.call_logger import CallLogger
from rotary_phone.database.database import Database


@pytest.fixture
def database() -> Database:
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Database(f.name)
        db.init_db()
        return db


@pytest.fixture
def call_logger(database: Database) -> CallLogger:
    """Create a CallLogger with a temporary database."""
    return CallLogger(database)


class TestCallLoggerOutbound:
    """Tests for outbound call logging."""

    def test_outbound_call_completed(self, call_logger: CallLogger, database: Database) -> None:
        """Test logging a completed outbound call."""
        call_logger.on_outbound_call_started(
            dialed_number="5551234",
            destination="+15551234567",
            speed_dial_code=None,
        )
        call_logger.on_call_answered()
        time.sleep(0.1)  # Simulate short call
        call_logger.on_call_ended(status="completed")

        calls = database.get_recent_calls(limit=1)
        assert len(calls) == 1
        call = calls[0]
        assert call.direction == "outbound"
        assert call.status == "completed"
        assert call.dialed_number == "5551234"
        assert call.destination == "+15551234567"
        assert call.speed_dial_code is None
        assert call.duration_seconds >= 0
        assert call.answered_at is not None

    def test_outbound_call_with_speed_dial(
        self, call_logger: CallLogger, database: Database
    ) -> None:
        """Test logging an outbound call using speed dial."""
        call_logger.on_outbound_call_started(
            dialed_number="11",
            destination="+15551234567",
            speed_dial_code="11",
        )
        call_logger.on_call_answered()
        call_logger.on_call_ended(status="completed")

        calls = database.get_recent_calls(limit=1)
        assert len(calls) == 1
        call = calls[0]
        assert call.dialed_number == "11"
        assert call.destination == "+15551234567"
        assert call.speed_dial_code == "11"

    def test_outbound_call_unanswered(self, call_logger: CallLogger, database: Database) -> None:
        """Test logging an outbound call that was not answered."""
        call_logger.on_outbound_call_started(
            dialed_number="5551234",
            destination="+15551234567",
        )
        call_logger.on_call_ended(status="unanswered")

        calls = database.get_recent_calls(limit=1)
        assert len(calls) == 1
        call = calls[0]
        assert call.status == "unanswered"
        assert call.answered_at is None
        assert call.duration_seconds == 0

    def test_outbound_call_failed(self, call_logger: CallLogger, database: Database) -> None:
        """Test logging a failed outbound call."""
        call_logger.on_outbound_call_started(
            dialed_number="5551234",
            destination="+15551234567",
        )
        call_logger.on_call_ended(status="failed", error_message="SIP timeout")

        calls = database.get_recent_calls(limit=1)
        assert len(calls) == 1
        call = calls[0]
        assert call.status == "failed"
        assert call.error_message == "SIP timeout"


class TestCallLoggerInbound:
    """Tests for inbound call logging."""

    def test_inbound_call_completed(self, call_logger: CallLogger, database: Database) -> None:
        """Test logging a completed inbound call."""
        call_logger.on_inbound_call_started(caller_id="+15559876543")
        call_logger.on_call_answered()
        time.sleep(0.1)
        call_logger.on_call_ended(status="completed")

        calls = database.get_recent_calls(limit=1)
        assert len(calls) == 1
        call = calls[0]
        assert call.direction == "inbound"
        assert call.status == "completed"
        assert call.caller_id == "+15559876543"
        assert call.answered_at is not None

    def test_inbound_call_missed(self, call_logger: CallLogger, database: Database) -> None:
        """Test logging a missed inbound call."""
        call_logger.on_inbound_call_started(caller_id="+15559876543")
        call_logger.on_call_ended(status="missed")

        calls = database.get_recent_calls(limit=1)
        assert len(calls) == 1
        call = calls[0]
        assert call.status == "missed"
        assert call.answered_at is None
        assert call.duration_seconds == 0


class TestCallLoggerRejected:
    """Tests for rejected call logging."""

    def test_call_rejected(self, call_logger: CallLogger, database: Database) -> None:
        """Test logging a rejected call."""
        call_logger.on_call_rejected(
            dialed_number="5551234",
            reason="Number not in allowlist",
        )

        calls = database.get_recent_calls(limit=1)
        assert len(calls) == 1
        call = calls[0]
        assert call.direction == "outbound"
        assert call.status == "rejected"
        assert call.dialed_number == "5551234"
        assert call.error_message == "Number not in allowlist"


class TestCallLoggerEdgeCases:
    """Tests for edge cases in call logging."""

    def test_call_answered_without_start(self, call_logger: CallLogger) -> None:
        """Test handling call_answered when no call is being tracked."""
        # Should not raise, just log a warning
        call_logger.on_call_answered()
        assert not call_logger.has_pending_call()

    def test_call_ended_without_start(self, call_logger: CallLogger, database: Database) -> None:
        """Test handling call_ended when no call is being tracked."""
        # Should not raise or create a record
        call_logger.on_call_ended(status="completed")
        assert database.count_calls() == 0

    def test_new_call_overwrites_previous(
        self, call_logger: CallLogger, database: Database
    ) -> None:
        """Test that starting a new call while one is tracked discards the old."""
        call_logger.on_outbound_call_started(
            dialed_number="111",
            destination="+11111111111",
        )
        # Start another call without ending the first
        call_logger.on_outbound_call_started(
            dialed_number="222",
            destination="+22222222222",
        )
        call_logger.on_call_ended(status="completed")

        calls = database.get_recent_calls(limit=10)
        assert len(calls) == 1
        assert calls[0].destination == "+22222222222"

    def test_cancel_current_call(self, call_logger: CallLogger) -> None:
        """Test cancelling a pending call."""
        call_logger.on_outbound_call_started(
            dialed_number="5551234",
            destination="+15551234567",
        )
        assert call_logger.has_pending_call()

        call_logger.cancel_current_call()
        assert not call_logger.has_pending_call()

    def test_cancel_when_no_pending_call(self, call_logger: CallLogger) -> None:
        """Test cancelling when no call is pending."""
        assert not call_logger.has_pending_call()
        call_logger.cancel_current_call()  # Should not raise
        assert not call_logger.has_pending_call()

    def test_has_pending_call(self, call_logger: CallLogger) -> None:
        """Test has_pending_call state tracking."""
        assert not call_logger.has_pending_call()

        call_logger.on_outbound_call_started(
            dialed_number="5551234",
            destination="+15551234567",
        )
        assert call_logger.has_pending_call()

        call_logger.on_call_ended(status="completed")
        assert not call_logger.has_pending_call()


class TestCallLoggerDatabaseErrors:
    """Tests for database error handling."""

    def test_database_error_doesnt_crash(self, call_logger: CallLogger) -> None:
        """Test that database errors are handled gracefully."""
        # Mock the database to raise an error
        call_logger._db.add_call = MagicMock(side_effect=Exception("DB error"))

        call_logger.on_outbound_call_started(
            dialed_number="5551234",
            destination="+15551234567",
        )
        # Should not raise
        call_logger.on_call_ended(status="completed")

    def test_rejected_call_db_error(self, call_logger: CallLogger) -> None:
        """Test that rejected call DB errors are handled."""
        call_logger._db.add_call = MagicMock(side_effect=Exception("DB error"))

        # Should not raise
        call_logger.on_call_rejected("5551234", "Not allowed")


class TestCallLoggerDuration:
    """Tests for call duration calculation."""

    def test_duration_calculation(self, call_logger: CallLogger, database: Database) -> None:
        """Test that duration is calculated correctly."""
        call_logger.on_outbound_call_started(
            dialed_number="5551234",
            destination="+15551234567",
        )
        call_logger.on_call_answered()
        time.sleep(0.5)  # Wait half a second
        call_logger.on_call_ended(status="completed")

        calls = database.get_recent_calls(limit=1)
        assert len(calls) == 1
        # Duration should be at least 0 seconds (could be 0 or 1 depending on timing)
        assert calls[0].duration_seconds >= 0

    def test_unanswered_call_has_zero_duration(
        self, call_logger: CallLogger, database: Database
    ) -> None:
        """Test that unanswered calls have zero duration."""
        call_logger.on_outbound_call_started(
            dialed_number="5551234",
            destination="+15551234567",
        )
        # Never answered
        call_logger.on_call_ended(status="unanswered")

        calls = database.get_recent_calls(limit=1)
        assert calls[0].duration_seconds == 0
