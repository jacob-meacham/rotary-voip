"""Tests for the database module."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rotary_phone.database.database import Database
from rotary_phone.database.models import CallLog


@pytest.fixture
def temp_db() -> Database:
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Database(f.name)
        db.init_db()
        return db


class TestCallLogModel:
    """Tests for the CallLog dataclass."""

    def test_create_call_log(self) -> None:
        """Test creating a CallLog instance."""
        now = datetime.utcnow()
        call = CallLog(
            timestamp=now,
            direction="outbound",
            status="completed",
            dialed_number="5551234",
            destination="+15551234567",
            duration_seconds=120,
        )
        assert call.timestamp == now
        assert call.direction == "outbound"
        assert call.status == "completed"
        assert call.duration_seconds == 120
        assert call.id is None

    def test_call_log_to_dict(self) -> None:
        """Test converting CallLog to dictionary."""
        now = datetime.utcnow()
        call = CallLog(
            id=1,
            timestamp=now,
            direction="inbound",
            status="completed",
            caller_id="+15551234567",
            duration_seconds=60,
            answered_at=now,
            ended_at=now + timedelta(seconds=60),
        )
        d = call.to_dict()

        assert d["id"] == 1
        assert d["direction"] == "inbound"
        assert d["status"] == "completed"
        assert d["caller_id"] == "+15551234567"
        assert d["duration_seconds"] == 60
        assert d["timestamp"] == now.isoformat()
        assert d["answered_at"] == now.isoformat()

    def test_call_log_to_dict_with_none_values(self) -> None:
        """Test to_dict with None optional fields."""
        call = CallLog(
            timestamp=datetime.utcnow(),
            direction="outbound",
            status="failed",
        )
        d = call.to_dict()

        assert d["caller_id"] is None
        assert d["answered_at"] is None
        assert d["error_message"] is None


class TestDatabase:
    """Tests for the Database class."""

    def test_init_creates_tables(self, temp_db: Database) -> None:
        """Test that init_db creates the required tables."""
        # Just verify we can add a call without error
        call = CallLog(
            timestamp=datetime.utcnow(),
            direction="outbound",
            status="completed",
        )
        call_id = temp_db.add_call(call)
        assert call_id > 0

    def test_init_creates_parent_directory(self, tmp_path: Path) -> None:
        """Test that init_db creates parent directories."""
        db_path = tmp_path / "subdir" / "calls.db"
        db = Database(str(db_path))
        db.init_db()
        assert db_path.parent.exists()

    def test_add_call(self, temp_db: Database) -> None:
        """Test adding a call record."""
        now = datetime.utcnow()
        call = CallLog(
            timestamp=now,
            direction="outbound",
            status="completed",
            dialed_number="11",
            destination="+15551234567",
            speed_dial_code="11",
            duration_seconds=120,
            answered_at=now,
            ended_at=now + timedelta(seconds=120),
        )
        call_id = temp_db.add_call(call)
        assert call_id > 0

    def test_get_call(self, temp_db: Database) -> None:
        """Test retrieving a call by ID."""
        now = datetime.utcnow()
        call = CallLog(
            timestamp=now,
            direction="inbound",
            status="completed",
            caller_id="+15559876543",
            duration_seconds=60,
        )
        call_id = temp_db.add_call(call)

        retrieved = temp_db.get_call(call_id)
        assert retrieved is not None
        assert retrieved.id == call_id
        assert retrieved.direction == "inbound"
        assert retrieved.caller_id == "+15559876543"

    def test_get_call_not_found(self, temp_db: Database) -> None:
        """Test retrieving a non-existent call."""
        result = temp_db.get_call(999)
        assert result is None

    def test_get_recent_calls(self, temp_db: Database) -> None:
        """Test getting recent calls."""
        # Add 5 calls
        for i in range(5):
            call = CallLog(
                timestamp=datetime.utcnow() - timedelta(hours=i),
                direction="outbound",
                status="completed",
            )
            temp_db.add_call(call)

        recent = temp_db.get_recent_calls(limit=3)
        assert len(recent) == 3
        # Should be in reverse chronological order
        assert recent[0].timestamp > recent[1].timestamp

    def test_get_recent_calls_empty(self, temp_db: Database) -> None:
        """Test getting recent calls when none exist."""
        recent = temp_db.get_recent_calls()
        assert len(recent) == 0

    def test_search_calls_by_direction(self, temp_db: Database) -> None:
        """Test searching calls by direction."""
        # Add mixed calls
        for direction in ["inbound", "outbound", "inbound"]:
            call = CallLog(
                timestamp=datetime.utcnow(),
                direction=direction,
                status="completed",
            )
            temp_db.add_call(call)

        inbound = temp_db.search_calls(direction="inbound")
        assert len(inbound) == 2

        outbound = temp_db.search_calls(direction="outbound")
        assert len(outbound) == 1

    def test_search_calls_by_status(self, temp_db: Database) -> None:
        """Test searching calls by status."""
        for status in ["completed", "missed", "failed", "completed"]:
            call = CallLog(
                timestamp=datetime.utcnow(),
                direction="inbound",
                status=status,
            )
            temp_db.add_call(call)

        completed = temp_db.search_calls(status="completed")
        assert len(completed) == 2

        missed = temp_db.search_calls(status="missed")
        assert len(missed) == 1

    def test_search_calls_by_date_range(self, temp_db: Database) -> None:
        """Test searching calls by date range."""
        now = datetime.utcnow()

        # Add calls over multiple days
        for days_ago in [0, 1, 3, 7]:
            call = CallLog(
                timestamp=now - timedelta(days=days_ago),
                direction="outbound",
                status="completed",
            )
            temp_db.add_call(call)

        # Search last 2 days
        results = temp_db.search_calls(
            start_date=now - timedelta(days=2),
            end_date=now,
        )
        assert len(results) == 2

    def test_search_calls_by_number_pattern(self, temp_db: Database) -> None:
        """Test searching calls by number pattern."""
        calls = [
            CallLog(
                timestamp=datetime.utcnow(),
                direction="outbound",
                status="completed",
                destination="+15551234567",
            ),
            CallLog(
                timestamp=datetime.utcnow(),
                direction="inbound",
                status="completed",
                caller_id="+15559876543",
            ),
            CallLog(
                timestamp=datetime.utcnow(),
                direction="outbound",
                status="completed",
                destination="+14441234567",
            ),
        ]
        for call in calls:
            temp_db.add_call(call)

        # Search for 555
        results = temp_db.search_calls(number_pattern="555")
        assert len(results) == 2

    def test_get_call_stats(self, temp_db: Database) -> None:
        """Test getting call statistics."""
        now = datetime.utcnow()

        # Add various calls
        calls = [
            CallLog(
                timestamp=now,
                direction="outbound",
                status="completed",
                duration_seconds=120,
            ),
            CallLog(
                timestamp=now,
                direction="inbound",
                status="completed",
                duration_seconds=60,
            ),
            CallLog(
                timestamp=now,
                direction="inbound",
                status="missed",
            ),
            CallLog(
                timestamp=now - timedelta(days=10),  # Outside 7 day window
                direction="outbound",
                status="completed",
                duration_seconds=300,
            ),
        ]
        for call in calls:
            temp_db.add_call(call)

        stats = temp_db.get_call_stats(days=7)

        assert stats["total_calls"] == 3  # Excludes the old call
        assert stats["by_status"].get("completed", 0) == 2
        assert stats["by_status"].get("missed", 0) == 1
        assert stats["by_direction"].get("inbound", 0) == 2
        assert stats["by_direction"].get("outbound", 0) == 1
        assert stats["total_duration_seconds"] == 180  # 120 + 60

    def test_cleanup_old_calls(self, temp_db: Database) -> None:
        """Test cleaning up old calls."""
        now = datetime.utcnow()

        # Add old and new calls
        old_call = CallLog(
            timestamp=now - timedelta(days=400),
            direction="outbound",
            status="completed",
        )
        new_call = CallLog(
            timestamp=now,
            direction="outbound",
            status="completed",
        )
        temp_db.add_call(old_call)
        temp_db.add_call(new_call)

        # Cleanup calls older than 365 days
        deleted = temp_db.cleanup_old_calls(days=365)
        assert deleted == 1

        # Verify only new call remains
        assert temp_db.count_calls() == 1

    def test_count_calls(self, temp_db: Database) -> None:
        """Test counting total calls."""
        assert temp_db.count_calls() == 0

        for _ in range(3):
            call = CallLog(
                timestamp=datetime.utcnow(),
                direction="outbound",
                status="completed",
            )
            temp_db.add_call(call)

        assert temp_db.count_calls() == 3


class TestDatabaseThreadSafety:
    """Tests for database thread safety."""

    def test_concurrent_writes(self, temp_db: Database) -> None:
        """Test that concurrent writes don't cause errors."""
        import threading

        errors: list[Exception] = []

        def add_calls() -> None:
            try:
                for _ in range(10):
                    call = CallLog(
                        timestamp=datetime.utcnow(),
                        direction="outbound",
                        status="completed",
                    )
                    temp_db.add_call(call)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_calls) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert temp_db.count_calls() == 50
