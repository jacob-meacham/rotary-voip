"""Authentication and session management for web admin."""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Dict, Final, Optional

import bcrypt
from fastapi import Cookie, HTTPException, Request

from rotary_phone.database.database import Database
from rotary_phone.database.models import User

logger = logging.getLogger(__name__)

# Pre-computed bcrypt hash used to equalize the timing of failed logins
# regardless of whether the username exists. Computed once at module load
# (~100ms one-time cost) so login() doesn't reveal user-existence via timing.
_DUMMY_HASH: Final[bytes] = bcrypt.hashpw(b"dummy", bcrypt.gensalt())


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
        expiry = datetime.now(UTC) + self._timeout
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
        if datetime.now(UTC) > expiry:
            del self._sessions[session_id]
            logger.debug("Session expired: %s", session_id)
            return None

        # Renew session (sliding window)
        new_expiry = datetime.now(UTC) + self._timeout
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
        now = datetime.now(UTC)
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

    async def login(
        self,
        username: str,
        password: str,
        current_session_id: Optional[str] = None,
    ) -> Optional[str]:
        """Authenticate user and create a new session.

        Always runs bcrypt — even when the username is unknown — so that
        timing doesn't reveal user existence. Runs bcrypt in a worker thread
        so the FastAPI event loop isn't blocked for ~100ms per attempt.

        If current_session_id is provided (i.e. the request already had a
        session cookie), that session is invalidated before the new one is
        minted — defends against session-fixation.
        """
        password_bytes = password.encode("utf-8")
        user = self.database.get_user_by_username(username)

        if user is None or user.id is None:
            # Run bcrypt anyway to keep the timing flat — prevents enumeration.
            await asyncio.to_thread(bcrypt.checkpw, password_bytes, _DUMMY_HASH)
            logger.warning("Login failed: user not found or has no id: %s", username)
            return None

        password_ok = await asyncio.to_thread(
            bcrypt.checkpw, password_bytes, user.password_hash.encode("utf-8")
        )
        if not password_ok:
            logger.warning("Login failed: invalid password for user: %s", username)
            return None

        # Rotate: invalidate any prior session before minting a new one.
        if current_session_id:
            self.sessions.delete_session(current_session_id)

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


async def require_auth(
    request: Request,
    session_id: Optional[str] = Cookie(None, alias="session_id"),
) -> User:
    """FastAPI dependency: returns the current User or raises 401.

    Pulls AuthManager off request.app.state so routes can use
    Depends(require_auth) directly without a factory closure.
    """
    auth_manager: AuthManager = request.app.state.auth_manager
    user = auth_manager.get_current_user(session_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
