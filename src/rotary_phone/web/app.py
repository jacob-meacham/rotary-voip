"""FastAPI application for rotary phone web admin interface."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from rotary_phone.call_manager import CallManager
from rotary_phone.config import ConfigManager
from rotary_phone.config.config_manager import ConfigError
from rotary_phone.database import Database
from rotary_phone.web.auth import AuthManager, require_auth
from rotary_phone.web.log_buffer import get_log_buffer, install_log_handler
from rotary_phone.web.rate_limiter import limiter
from rotary_phone.web.routes import (
    allowlist_router,
    auth_router,
    calls_router,
    logs_router,
    network_router,
    settings_router,
    sounds_router,
    speed_dial_router,
)
from rotary_phone.web.websocket import (
    CallEndedEvent,
    CallStartedEvent,
    ConnectionManager,
    DigitDialedEvent,
    PhoneStateChangedEvent,
    WebSocketEvent,
)

logger = logging.getLogger(__name__)

# Session cleanup interval in seconds
SESSION_CLEANUP_INTERVAL = 300  # 5 minutes


# pylint: disable=too-many-locals,too-many-statements
# create_app is the application wiring entry point; splitting it would only push
# the same locals/statements into helpers without making the dependency graph
# clearer. Disabled here rather than across the whole file.
def create_app(
    call_manager: CallManager,
    config_manager: ConfigManager,
    config_path: str,
    database: Optional[Database] = None,
) -> FastAPI:
    """Create and configure FastAPI application.

    Args:
        call_manager: CallManager instance
        config_manager: ConfigManager instance
        config_path: Path to the configuration file
        database: Database instance for call logs (optional)

    Returns:
        Configured FastAPI application
    """

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
        """Manage background tasks for the app lifecycle."""
        cleanup_task: Optional[asyncio.Task[None]] = None
        if hasattr(fastapi_app.state, "auth_manager"):

            async def cleanup_loop() -> None:
                while True:
                    await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
                    try:
                        fastapi_app.state.auth_manager.sessions.cleanup_expired()
                    except Exception as e:
                        logger.error("Session cleanup error: %s", e)

            cleanup_task = asyncio.create_task(cleanup_loop())
            logger.debug("Session cleanup task started")

        try:
            yield
        finally:
            if cleanup_task is not None:
                cleanup_task.cancel()
                try:
                    await cleanup_task
                except asyncio.CancelledError:
                    pass
                logger.debug("Session cleanup task stopped")

    app = FastAPI(
        title="Rotary Phone VoIP Admin",
        description="Web admin interface for rotary phone system",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Add rate limiter
    app.state.limiter = limiter
    # slowapi's _rate_limit_exceeded_handler is typed (Request, RateLimitExceeded) -> Response,
    # but Starlette's add_exception_handler expects (Request, Exception) -> Response. The runtime
    # contract is correct (the handler is only invoked for RateLimitExceeded); the signatures just
    # don't compose. Tracked upstream at https://github.com/laurents/slowapi/issues/177.
    app.add_exception_handler(
        RateLimitExceeded,
        _rate_limit_exceeded_handler,  # type: ignore[arg-type]
    )

    # Store references for API handlers
    app.state.call_manager = call_manager
    app.state.config_manager = config_manager
    app.state.config_path = config_path
    app.state.database = database

    # Initialize log buffer for log viewer
    app.state.log_buffer = get_log_buffer()
    install_log_handler(level=logging.DEBUG)

    # Initialize WebSocket connection manager
    app.state.ws_manager = ConnectionManager()

    # Initialize authentication manager
    if database:
        database.init_db()  # Ensure users table exists
        app.state.auth_manager = AuthManager(database, session_timeout_minutes=60)
        logger.info("Authentication enabled with %d users", database.count_users())
    else:
        logger.warning("No database provided - authentication will be disabled")

    # Set up CallManager event callback to broadcast via WebSocket
    def on_call_manager_event(event_type: str, data: Dict[str, Any]) -> None:
        """Handle CallManager events and broadcast via WebSocket."""
        ws_manager: ConnectionManager = app.state.ws_manager
        try:
            # Create appropriate event object
            event: WebSocketEvent
            if event_type == "phone_state_changed":
                event = PhoneStateChangedEvent(
                    old_state=data["old_state"],
                    new_state=data["new_state"],
                    current_number=data.get("current_number"),
                )
            elif event_type == "call_started":
                event = CallStartedEvent(
                    direction=data["direction"],
                    number=data["number"],
                )
            elif event_type == "call_ended":
                event = CallEndedEvent(
                    direction=data["direction"],
                    number=data["number"],
                    duration=data["duration"],
                    status=data["status"],
                )
            elif event_type == "digit_dialed":
                event = DigitDialedEvent(
                    digit=data["digit"],
                    number_so_far=data["number_so_far"],
                )
            else:
                logger.warning("Unknown event type from CallManager: %s", event_type)
                return

            # Broadcast to all connected WebSocket clients
            ws_manager.broadcast_sync(event)
        except Exception as e:
            logger.error("Error broadcasting CallManager event: %s", e)

    call_manager.set_event_callback(on_call_manager_event)

    # Serve static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Include routers from route modules.
    # Every router except the auth router itself requires a valid session cookie.
    # Adding the dependency here (rather than per-route) guarantees a new endpoint
    # can't be accidentally exposed.
    _protected = [Depends(require_auth)]

    app.include_router(auth_router)  # NOT protected — login can't require login
    app.include_router(sounds_router, dependencies=_protected)
    app.include_router(settings_router, dependencies=_protected)
    app.include_router(logs_router, dependencies=_protected)
    app.include_router(calls_router, dependencies=_protected)
    app.include_router(allowlist_router, dependencies=_protected)
    app.include_router(speed_dial_router, dependencies=_protected)
    app.include_router(network_router, dependencies=_protected)

    # -------------------------------------------------------------------------
    # WebSocket Endpoint
    # -------------------------------------------------------------------------

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time updates. Requires a valid
        session cookie; otherwise rejects with WS close code 4401."""
        session_id = websocket.cookies.get("session_id")
        auth_manager: AuthManager = websocket.app.state.auth_manager
        if auth_manager.get_current_user(session_id) is None:
            await websocket.close(code=4401, reason="Not authenticated")
            return

        ws_manager: ConnectionManager = websocket.app.state.ws_manager
        await ws_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await ws_manager.disconnect(websocket)
        except Exception as e:
            logger.error("WebSocket error: %s", e)
            await ws_manager.disconnect(websocket)

    # -------------------------------------------------------------------------
    # Core Routes
    # -------------------------------------------------------------------------

    @app.get("/")
    async def root() -> FileResponse:
        """Serve the main HTML page."""
        return FileResponse(static_dir / "index.html")

    @app.get("/setup")
    async def setup_page() -> FileResponse:
        """Serve the captive portal setup page."""
        return FileResponse(static_dir / "captive.html")

    @app.get("/login")
    async def login_page() -> FileResponse:
        """Serve login page."""
        return FileResponse(static_dir / "login.html")

    @app.get("/api/status", dependencies=_protected)
    async def get_status() -> Dict[str, Any]:
        """Get current phone status."""
        cm = app.state.call_manager

        return {
            "phone": {
                "state": cm.get_state().value,
                "dialed_number": cm.get_dialed_number(),
                "error_message": cm.get_error_message(),
            },
            "config": {
                "sip_server": app.state.config_manager.get("sip.server", ""),
                "sip_username": app.state.config_manager.get("sip.username", ""),
            },
        }

    @app.get("/api/config", dependencies=_protected)
    async def get_config() -> Dict[str, Any]:
        """Get current configuration (with sensitive data masked)."""
        result: Dict[str, Any] = app.state.config_manager.to_dict_safe()
        return result

    @app.get("/api/config/raw", dependencies=_protected)
    async def get_config_raw() -> PlainTextResponse:
        """Get raw configuration file content."""
        try:
            config_file = Path(app.state.config_path)
            content = config_file.read_text(encoding="utf-8")
            return PlainTextResponse(content)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail="Config file not found") from e
        except IOError as e:
            raise HTTPException(status_code=500, detail=f"Failed to read config: {e}") from e

    @app.post("/api/config", dependencies=_protected)
    async def save_config(request: Request) -> Dict[str, Any]:
        """Save configuration file. Accepts raw YAML text."""
        try:
            yaml_content = await request.body()
            yaml_text = yaml_content.decode("utf-8")

            try:
                yaml.safe_load(yaml_text)
            except yaml.YAMLError as e:
                raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}") from e

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(yaml_text)
                tmp_path = tmp.name

            try:
                ConfigManager(user_config_path=tmp_path)

                config_file = Path(app.state.config_path)
                config_file.write_text(yaml_text, encoding="utf-8")

                return {
                    "success": True,
                    "message": "Configuration saved. Restart the application to apply changes.",
                    "restart_required": True,
                }
            finally:
                Path(tmp_path).unlink()

        except ConfigError as e:
            raise HTTPException(status_code=400, detail=f"Invalid configuration: {e}") from e
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save config: {e}") from e

    # -------------------------------------------------------------------------
    # Exception Handlers
    # -------------------------------------------------------------------------

    @app.exception_handler(RequestValidationError)
    # Branches map each Pydantic error_type to a specific 400 response shape;
    # a dispatch table would add indirection without reducing the surface.
    # pylint: disable-next=too-many-return-statements
    async def request_validation_exception_handler(
        request: Request,  # pylint: disable=unused-argument
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Convert FastAPI validation errors to HTTP 400 responses with user-friendly messages."""
        errors = exc.errors()
        if not errors:
            return JSONResponse(status_code=400, content={"detail": "Validation error"})

        first_error = errors[0]
        error_type = first_error.get("type", "")
        error_msg = first_error.get("msg", "")
        loc = first_error.get("loc", [])

        # Get the field name (skip 'body' prefix if present)
        field_parts = [str(part) for part in loc if part != "body"]
        field = field_parts[0] if field_parts else "unknown"

        # Handle JSON parsing errors
        if error_type == "json_invalid":
            return JSONResponse(status_code=400, content={"detail": "Invalid JSON"})

        # Handle missing required fields
        if error_type == "missing":
            # Special case for SpeedDialEntry which needs both code and number
            if field in ("code", "number"):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Missing 'code' or 'number' field"},
                )
            return JSONResponse(status_code=400, content={"detail": f"Missing '{field}' field"})

        # Handle type errors
        if error_type in ("dict_type", "mapping_type"):
            return JSONResponse(status_code=400, content={"detail": f"'{field}' must be an object"})
        if error_type in ("list_type", "array_type"):
            return JSONResponse(status_code=400, content={"detail": f"'{field}' must be an array"})
        if error_type == "string_type":
            return JSONResponse(
                status_code=400, content={"detail": f"Entry at index {field} must be a string"}
            )

        # Handle custom validation errors from Pydantic validators
        if error_type == "value_error":
            # Parse error message from custom validators
            if "Invalid speed dial code" in error_msg:
                return JSONResponse(status_code=400, content={"detail": "Invalid speed dial code"})
            if "Invalid phone number" in error_msg:
                return JSONResponse(status_code=400, content={"detail": "Invalid phone number"})
            if "Invalid phone pattern" in error_msg:
                return JSONResponse(status_code=400, content={"detail": "Invalid phone pattern"})
            return JSONResponse(status_code=400, content={"detail": error_msg})

        # Default fallback
        return JSONResponse(status_code=400, content={"detail": error_msg or "Validation error"})

    # -------------------------------------------------------------------------
    # SPA Catch-All Route (must be last)
    # -------------------------------------------------------------------------

    @app.get("/{full_path:path}")
    async def spa_catch_all(full_path: str) -> FileResponse:
        """Catch-all route for SPA - serves index.html for all non-API routes.

        This enables client-side routing with clean URLs. Must be defined last
        so it doesn't override other routes.
        """
        # Don't intercept API or static routes
        if full_path.startswith("api/") or full_path.startswith("static/"):
            raise HTTPException(status_code=404, detail="Not found")

        # Check if file exists in static directory (e.g., login.html if accessed directly)
        file_path = static_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # Otherwise serve index.html for SPA routing
        return FileResponse(static_dir / "index.html")

    logger.info("FastAPI application created")
    return app
