"""Tests for the authentication module."""

import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import bcrypt
import pytest
from fastapi import HTTPException

from rotary_phone.database.database import Database
from rotary_phone.database.models import User
from rotary_phone.web.auth import AuthManager, SessionStore, require_auth


@pytest.fixture
def temp_db() -> Database:
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Database(f.name)
        db.init_db()
        return db


@pytest.fixture
def test_user(temp_db: Database) -> User:
    """Create a test user in the database."""
    password = "testpassword123"
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(
        username="testuser",
        password_hash=password_hash,
        created_at=datetime.utcnow(),
    )
    user_id = temp_db.add_user(user)
    user.id = user_id
    return user


class TestSessionStore:
    """Tests for the SessionStore class."""

    def test_init_default_timeout(self) -> None:
        """Test SessionStore initialization with default timeout."""
        store = SessionStore()
        assert store._timeout == timedelta(minutes=60)

    def test_init_custom_timeout(self) -> None:
        """Test SessionStore initialization with custom timeout."""
        store = SessionStore(timeout_minutes=30)
        assert store._timeout == timedelta(minutes=30)

    def test_create_session(self) -> None:
        """Test creating a new session."""
        store = SessionStore()
        session_id = store.create_session(user_id=1)

        assert session_id is not None
        assert len(session_id) > 20  # Secure token should be long
        assert session_id in store._sessions

    def test_create_session_stores_user_id(self) -> None:
        """Test that session stores correct user ID."""
        store = SessionStore()
        session_id = store.create_session(user_id=42)

        user_id, _ = store._sessions[session_id]
        assert user_id == 42

    def test_get_user_id_valid_session(self) -> None:
        """Test getting user ID from valid session."""
        store = SessionStore()
        session_id = store.create_session(user_id=1)

        user_id = store.get_user_id(session_id)
        assert user_id == 1

    def test_get_user_id_invalid_session(self) -> None:
        """Test getting user ID from invalid session returns None."""
        store = SessionStore()
        user_id = store.get_user_id("invalid-session-id")
        assert user_id is None

    def test_get_user_id_expired_session(self) -> None:
        """Test that expired sessions return None."""
        store = SessionStore(timeout_minutes=1)
        session_id = store.create_session(user_id=1)

        # Manually expire the session
        _, _ = store._sessions[session_id]
        store._sessions[session_id] = (1, datetime.utcnow() - timedelta(minutes=5))

        user_id = store.get_user_id(session_id)
        assert user_id is None
        assert session_id not in store._sessions  # Should be removed

    def test_get_user_id_renews_session(self) -> None:
        """Test that getting user ID renews session expiry."""
        store = SessionStore(timeout_minutes=60)
        session_id = store.create_session(user_id=1)

        original_expiry = store._sessions[session_id][1]

        # Wait a tiny bit and access again
        import time

        time.sleep(0.01)
        store.get_user_id(session_id)

        new_expiry = store._sessions[session_id][1]
        assert new_expiry >= original_expiry

    def test_delete_session(self) -> None:
        """Test deleting a session."""
        store = SessionStore()
        session_id = store.create_session(user_id=1)

        store.delete_session(session_id)
        assert session_id not in store._sessions

    def test_delete_session_nonexistent(self) -> None:
        """Test deleting a nonexistent session doesn't raise."""
        store = SessionStore()
        store.delete_session("nonexistent-session")  # Should not raise

    def test_cleanup_expired(self) -> None:
        """Test cleanup of expired sessions."""
        store = SessionStore(timeout_minutes=60)

        # Create some sessions
        session1 = store.create_session(user_id=1)
        session2 = store.create_session(user_id=2)
        session3 = store.create_session(user_id=3)

        # Manually expire session1 and session2
        store._sessions[session1] = (1, datetime.utcnow() - timedelta(minutes=5))
        store._sessions[session2] = (2, datetime.utcnow() - timedelta(minutes=10))

        store.cleanup_expired()

        assert session1 not in store._sessions
        assert session2 not in store._sessions
        assert session3 in store._sessions

    def test_cleanup_expired_no_expired(self) -> None:
        """Test cleanup when no sessions are expired."""
        store = SessionStore(timeout_minutes=60)
        session_id = store.create_session(user_id=1)

        store.cleanup_expired()

        assert session_id in store._sessions


class TestAuthManager:
    """Tests for the AuthManager class."""

    def test_init(self, temp_db: Database) -> None:
        """Test AuthManager initialization."""
        auth = AuthManager(temp_db, session_timeout_minutes=30)

        assert auth.database == temp_db
        assert auth.sessions._timeout == timedelta(minutes=30)

    def test_verify_password_correct(self) -> None:
        """Test password verification with correct password."""
        auth = AuthManager(MagicMock())
        password = "correctpassword"
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        assert auth.verify_password(password, password_hash) is True

    def test_verify_password_incorrect(self) -> None:
        """Test password verification with incorrect password."""
        auth = AuthManager(MagicMock())
        password_hash = bcrypt.hashpw(b"correctpassword", bcrypt.gensalt()).decode("utf-8")

        assert auth.verify_password("wrongpassword", password_hash) is False

    def test_verify_password_invalid_hash(self) -> None:
        """Test password verification with invalid hash."""
        auth = AuthManager(MagicMock())

        assert auth.verify_password("password", "invalid-hash") is False

    def test_login_success(self, temp_db: Database, test_user: User) -> None:
        """Test successful login."""
        auth = AuthManager(temp_db)

        session_id = auth.login("testuser", "testpassword123")

        assert session_id is not None
        assert len(session_id) > 20

    def test_login_user_not_found(self, temp_db: Database) -> None:
        """Test login with non-existent user."""
        auth = AuthManager(temp_db)

        session_id = auth.login("nonexistent", "password")

        assert session_id is None

    def test_login_wrong_password(self, temp_db: Database, test_user: User) -> None:
        """Test login with wrong password."""
        auth = AuthManager(temp_db)

        session_id = auth.login("testuser", "wrongpassword")

        assert session_id is None

    def test_login_user_without_id(self, temp_db: Database) -> None:
        """Test login when user has no ID (edge case)."""
        auth = AuthManager(temp_db)

        # Mock get_user_by_username to return a user without ID
        password_hash = bcrypt.hashpw(b"password", bcrypt.gensalt()).decode("utf-8")
        user_without_id = User(
            username="noIdUser",
            password_hash=password_hash,
            created_at=datetime.utcnow(),
            id=None,
        )
        auth.database.get_user_by_username = MagicMock(return_value=user_without_id)

        session_id = auth.login("noIdUser", "password")

        assert session_id is None

    def test_logout(self, temp_db: Database, test_user: User) -> None:
        """Test logout."""
        auth = AuthManager(temp_db)
        session_id = auth.login("testuser", "testpassword123")

        auth.logout(session_id)

        # Session should be gone
        assert auth.sessions.get_user_id(session_id) is None

    def test_get_current_user_valid_session(self, temp_db: Database, test_user: User) -> None:
        """Test getting current user with valid session."""
        auth = AuthManager(temp_db)
        session_id = auth.login("testuser", "testpassword123")

        user = auth.get_current_user(session_id)

        assert user is not None
        assert user.username == "testuser"

    def test_get_current_user_no_session(self, temp_db: Database) -> None:
        """Test getting current user with no session."""
        auth = AuthManager(temp_db)

        user = auth.get_current_user(None)

        assert user is None

    def test_get_current_user_invalid_session(self, temp_db: Database) -> None:
        """Test getting current user with invalid session."""
        auth = AuthManager(temp_db)

        user = auth.get_current_user("invalid-session")

        assert user is None

    def test_get_current_user_expired_session(self, temp_db: Database, test_user: User) -> None:
        """Test getting current user with expired session."""
        auth = AuthManager(temp_db, session_timeout_minutes=1)
        session_id = auth.login("testuser", "testpassword123")

        # Manually expire the session
        auth.sessions._sessions[session_id] = (
            test_user.id,
            datetime.utcnow() - timedelta(minutes=5),
        )

        user = auth.get_current_user(session_id)

        assert user is None


class TestRequireAuth:
    """Tests for the require_auth dependency."""

    @pytest.mark.asyncio
    async def test_require_auth_valid_session(self, temp_db: Database, test_user: User) -> None:
        """Test require_auth with valid session."""
        auth = AuthManager(temp_db)
        session_id = auth.login("testuser", "testpassword123")

        dependency = require_auth(auth)
        user = await dependency(session_id=session_id)

        assert user.username == "testuser"

    @pytest.mark.asyncio
    async def test_require_auth_no_session(self, temp_db: Database) -> None:
        """Test require_auth with no session raises HTTPException."""
        auth = AuthManager(temp_db)

        dependency = require_auth(auth)

        with pytest.raises(HTTPException) as exc_info:
            await dependency(session_id=None)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Not authenticated"

    @pytest.mark.asyncio
    async def test_require_auth_invalid_session(self, temp_db: Database) -> None:
        """Test require_auth with invalid session raises HTTPException."""
        auth = AuthManager(temp_db)

        dependency = require_auth(auth)

        with pytest.raises(HTTPException) as exc_info:
            await dependency(session_id="invalid-session")

        assert exc_info.value.status_code == 401
