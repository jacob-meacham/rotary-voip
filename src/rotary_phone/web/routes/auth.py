"""Authentication routes."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from rotary_phone.web.auth import AuthManager
from rotary_phone.web.rate_limiter import LOGIN_RATE_LIMIT, limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
@limiter.limit(LOGIN_RATE_LIMIT)
async def login(request: Request) -> JSONResponse:
    """Login and create session.

    Rate limited to 5 attempts per minute per IP address.

    Request body:
        {
            "username": "admin",
            "password": "password"
        }

    Returns:
        Success message with session cookie set
    """
    auth_manager: AuthManager = request.app.state.auth_manager

    try:
        body = await request.json()
        username = body.get("username")
        password = body.get("password")

        if not username or not password:
            raise HTTPException(status_code=400, detail="Username and password required")

        # Authenticate
        session_id = auth_manager.login(username, password)
        if not session_id:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        # Return success with session cookie
        response = JSONResponse(content={"success": True, "message": "Logged in successfully"})
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=3600,  # 1 hour
            samesite="lax",
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Logout and destroy session."""
    auth_manager: AuthManager = request.app.state.auth_manager
    session_id = request.cookies.get("session_id")

    if session_id:
        auth_manager.logout(session_id)

    response = JSONResponse(content={"success": True, "message": "Logged out successfully"})
    response.delete_cookie("session_id")
    return response


@router.get("/status")
async def auth_status(request: Request) -> Dict[str, Any]:
    """Check authentication status.

    Returns:
        {
            "authenticated": true/false,
            "user": {...} (if authenticated)
        }
    """
    auth_manager: AuthManager = request.app.state.auth_manager
    session_id = request.cookies.get("session_id")

    user = auth_manager.get_current_user(session_id)
    if user:
        return {"authenticated": True, "user": user.to_dict()}
    return {"authenticated": False}
