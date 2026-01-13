"""Authentication and session management for web admin."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Callable, Coroutine, Dict, Optional, Any

import bcrypt
from fastapi import Cookie, HTTPException, status

from rotary_phone.database.database import Database
from rotary_phone.database.models import User

logger = logging.getLogger(__name__)


class SessionStore:
    """In-memory session store with expiry.

    Sessions are stored in memory and expire after a configurable timeout.
    This is simple and sufficient for a single-user admin interface.
    """

    def __init__(self, timeout_minutes: int = 60) -> None:
        """Initialize session store.

        Args:
            timeout_minutes: Session timeout in minutes (default: 60)
        """
        self._sessions: Dict[str, tuple[int, datetime]] = {}  # session_id -> (user_id, expiry)
        self._timeout = timedelta(minutes=timeout_minutes)
        logger.debug("Session store initialized with %d minute timeout", timeout_minutes)

    def create_session(self, user_id: int) -> str:
        """Create a new session.

        Args:
            user_id: User ID to associate with session

        Returns:
            Session ID (secure random token)
        """
        session_id = secrets.token_urlsafe(32)
        expiry = datetime.utcnow() + self._timeout
        self._sessions[session_id] = (user_id, expiry)
        logger.info("Created session for user_id=%d", user_id)
        return session_id

    def get_user_id(self, session_id: str) -> Optional[int]:
        """Get user ID from session.

        Args:
            session_id: Session ID to lookup

        Returns:
            User ID if session valid and not expired, None otherwise
        """
        if session_id not in self._sessions:
            return None

        user_id, expiry = self._sessions[session_id]

        # Check if expired
        if datetime.utcnow() > expiry:
            del self._sessions[session_id]
            logger.debug("Session expired: %s", session_id)
            return None

        # Renew session (sliding window)
        new_expiry = datetime.utcnow() + self._timeout
        self._sessions[session_id] = (user_id, new_expiry)

        return user_id

    def delete_session(self, session_id: str) -> None:
        """Delete a session (logout).

        Args:
            session_id: Session ID to delete
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.debug("Deleted session: %s", session_id)

    def cleanup_expired(self) -> None:
        """Remove all expired sessions."""
        now = datetime.utcnow()
        expired = [sid for sid, (_, expiry) in self._sessions.items() if now > expiry]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.debug("Cleaned up %d expired sessions", len(expired))


class AuthManager:
    """Manages authentication and sessions."""

    def __init__(self, database: Database, session_timeout_minutes: int = 60) -> None:
        """Initialize auth manager.

        Args:
            database: Database instance
            session_timeout_minutes: Session timeout in minutes
        """
        self.database = database
        self.sessions = SessionStore(timeout_minutes=session_timeout_minutes)

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash.

        Args:
            password: Plain text password
            password_hash: Bcrypt hashed password

        Returns:
            True if password matches, False otherwise
        """
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except Exception as e:
            logger.warning("Password verification error: %s", e)
            return False

    def login(self, username: str, password: str) -> Optional[str]:
        """Authenticate user and create session.

        Args:
            username: Username
            password: Plain text password

        Returns:
            Session ID if authentication successful, None otherwise
        """
        # Get user from database
        user = self.database.get_user_by_username(username)
        if not user:
            logger.warning("Login failed: user not found: %s", username)
            return None

        # Verify password
        if not self.verify_password(password, user.password_hash):
            logger.warning("Login failed: invalid password for user: %s", username)
            return None

        # User from database always has an id
        if user.id is None:
            logger.error("User %s has no id", username)
            return None

        # Create session
        session_id = self.sessions.create_session(user.id)
        logger.info("User logged in: %s (user_id=%d)", username, user.id)
        return session_id

    def logout(self, session_id: str) -> None:
        """Logout user (delete session).

        Args:
            session_id: Session ID to delete
        """
        self.sessions.delete_session(session_id)

    def get_current_user(self, session_id: Optional[str]) -> Optional[User]:
        """Get current user from session.

        Args:
            session_id: Session ID from cookie

        Returns:
            User if session valid, None otherwise
        """
        if not session_id:
            return None

        user_id = self.sessions.get_user_id(session_id)
        if not user_id:
            return None

        return self.database.get_user(user_id)


# FastAPI dependency for requiring authentication
def require_auth(
    auth_manager: AuthManager,
) -> Callable[..., Coroutine[Any, Any, User]]:
    """Create a FastAPI dependency that requires authentication.

    Args:
        auth_manager: AuthManager instance

    Returns:
        Dependency function
    """

    async def dependency(session_id: Optional[str] = Cookie(None, alias="session_id")) -> User:
        """Check if user is authenticated.

        Args:
            session_id: Session ID from cookie

        Returns:
            Current user

        Raises:
            HTTPException: If not authenticated
        """
        user = auth_manager.get_current_user(session_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    return dependency
