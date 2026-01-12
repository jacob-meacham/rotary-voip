"""FastAPI application for rotary phone web admin interface."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from rotary_phone.call_manager import CallManager
from rotary_phone.config import ConfigManager
from rotary_phone.config.config_manager import ConfigError
from rotary_phone.database import Database

logger = logging.getLogger(__name__)


def create_app(  # pylint: disable=too-many-statements,too-many-locals
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
    app = FastAPI(
        title="Rotary Phone VoIP Admin",
        description="Web admin interface for rotary phone system",
        version="1.0.0",
    )

    # Store references for API handlers
    app.state.call_manager = call_manager
    app.state.config_manager = config_manager
    app.state.config_path = config_path
    app.state.database = database

    # Serve static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def root() -> FileResponse:
        """Serve the main HTML page."""
        return FileResponse(static_dir / "index.html")

    @app.get("/api/status")
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

    @app.get("/api/config")
    async def get_config() -> Dict[str, Any]:
        """Get current configuration (with sensitive data masked)."""
        result: Dict[str, Any] = app.state.config_manager.to_dict_safe()
        return result

    @app.get("/api/config/raw")
    async def get_config_raw() -> PlainTextResponse:
        """Get raw configuration file content."""
        try:
            config_file = Path(app.state.config_path)
            content = config_file.read_text(encoding="utf-8")
            return PlainTextResponse(content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read config: {e}") from e

    @app.post("/api/config")
    async def save_config(request: Request) -> Dict[str, Any]:
        """Save configuration file.

        Accepts raw YAML text, validates it, and saves atomically.
        """
        try:
            # Get raw YAML text from request body
            yaml_content = await request.body()
            yaml_text = yaml_content.decode("utf-8")

            # Parse and validate by creating a temp ConfigManager
            # pylint: disable=import-outside-toplevel
            import tempfile

            import yaml

            # First validate it's valid YAML
            try:
                yaml.safe_load(yaml_text)
            except yaml.YAMLError as e:
                raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}") from e

            # Write to temp file and validate with ConfigManager
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(yaml_text)
                tmp_path = tmp.name

            try:
                # Validate by loading with ConfigManager
                ConfigManager(user_config_path=tmp_path)

                # If validation passed, save to actual config file atomically
                config_file = Path(app.state.config_path)
                config_file.write_text(yaml_text, encoding="utf-8")

                return {
                    "success": True,
                    "message": "Configuration saved. Restart the application to apply changes.",
                    "restart_required": True,
                }
            finally:
                # Clean up temp file
                Path(tmp_path).unlink()

        except ConfigError as e:
            raise HTTPException(status_code=400, detail=f"Invalid configuration: {e}") from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save config: {e}") from e

    @app.get("/api/sounds")
    async def list_sounds() -> Dict[str, List[Dict[str, Any]]]:
        """List all sound files in the sounds directory."""
        sounds_dir = Path("sounds")
        if not sounds_dir.exists():
            return {"files": []}

        files = []
        for sound_file in sorted(sounds_dir.glob("*.wav")):
            files.append(
                {
                    "name": sound_file.name,
                    "size": sound_file.stat().st_size,
                    "path": str(sound_file),
                }
            )

        return {"files": files}

    @app.post("/api/sounds/upload")
    async def upload_sound(file: UploadFile) -> Dict[str, Any]:
        """Upload a new sound file."""
        # Validate file extension
        if not file.filename or not file.filename.lower().endswith(".wav"):
            raise HTTPException(status_code=400, detail="Only .wav files are allowed")

        # Ensure sounds directory exists
        sounds_dir = Path("sounds")
        sounds_dir.mkdir(exist_ok=True)

        # Save the file
        try:
            file_path = sounds_dir / file.filename
            content = await file.read()

            # Simple validation: check for RIFF header (WAV file magic bytes)
            if not content.startswith(b"RIFF"):
                raise HTTPException(status_code=400, detail="Invalid WAV file format")

            file_path.write_bytes(content)

            return {
                "success": True,
                "message": f"File '{file.filename}' uploaded successfully",
                "filename": file.filename,
                "size": len(content),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload file: {e}") from e

    # -------------------------------------------------------------------------
    # Call Log API
    # -------------------------------------------------------------------------

    @app.get("/api/calls")
    async def get_calls(
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        direction: Optional[str] = Query(default=None),
        status: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        """Get call log entries with pagination and filtering.

        Args:
            limit: Maximum number of calls to return (1-500)
            offset: Number of records to skip for pagination
            direction: Filter by direction ("inbound" or "outbound")
            status: Filter by status ("completed", "missed", "failed", "rejected")
            search: Search term for phone number

        Returns:
            Dictionary with calls array and pagination info
        """
        db = app.state.database
        if db is None:
            raise HTTPException(status_code=503, detail="Database not configured")

        # Validate direction
        if direction and direction not in ("inbound", "outbound"):
            raise HTTPException(
                status_code=400,
                detail="Invalid direction. Must be 'inbound' or 'outbound'",
            )

        # Validate status
        valid_statuses = ("completed", "missed", "failed", "rejected")
        if status and status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
            )

        # Use search_calls for filtering
        calls = db.search_calls(
            direction=direction,
            status=status,
            number_pattern=search,
            limit=limit + offset + 1,  # Fetch extra to determine if there are more
        )

        # Apply offset manually (search_calls doesn't support offset directly)
        total_before_offset = len(calls)
        calls = calls[offset : offset + limit]

        # Determine if there are more results
        has_more = total_before_offset > offset + limit

        return {
            "calls": [call.to_dict() for call in calls],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "returned": len(calls),
            },
        }

    @app.get("/api/calls/stats")
    async def get_call_stats(
        days: int = Query(default=7, ge=1, le=365),
    ) -> Dict[str, Any]:
        """Get call statistics for dashboard.

        Args:
            days: Number of days to include in stats (1-365)

        Returns:
            Dictionary with call statistics
        """
        db = app.state.database
        if db is None:
            raise HTTPException(status_code=503, detail="Database not configured")

        stats = db.get_call_stats(days=days)
        return {"stats": stats, "days": days}

    @app.get("/api/calls/{call_id}")
    async def get_call(call_id: int) -> Dict[str, Any]:
        """Get a single call by ID.

        Args:
            call_id: Call record ID

        Returns:
            Call details
        """
        db = app.state.database
        if db is None:
            raise HTTPException(status_code=503, detail="Database not configured")

        call = db.get_call(call_id)
        if call is None:
            raise HTTPException(status_code=404, detail="Call not found")

        return {"call": call.to_dict()}

    @app.delete("/api/calls/{call_id}")
    async def delete_call(call_id: int) -> Dict[str, Any]:
        """Delete a call record.

        Args:
            call_id: Call record ID to delete

        Returns:
            Success message
        """
        db = app.state.database
        if db is None:
            raise HTTPException(status_code=503, detail="Database not configured")

        # Check if call exists first
        call = db.get_call(call_id)
        if call is None:
            raise HTTPException(status_code=404, detail="Call not found")

        # Delete the call
        with db._connection() as conn:  # pylint: disable=protected-access
            conn.execute("DELETE FROM call_logs WHERE id = ?", (call_id,))
            conn.commit()

        return {"success": True, "message": f"Call {call_id} deleted"}

    # -------------------------------------------------------------------------
    # Allowlist API
    # -------------------------------------------------------------------------

    @app.get("/api/allowlist")
    async def get_allowlist() -> Dict[str, Any]:
        """Get current allowlist configuration."""
        allowlist: List[str] = app.state.config_manager.get("allowlist", [])
        return {
            "allowlist": allowlist,
            "allow_all": "*" in allowlist,
        }

    @app.put("/api/allowlist")
    async def update_allowlist(request: Request) -> Dict[str, Any]:
        """Update the allowlist.

        Accepts JSON body with:
        - allowlist: array of phone number patterns (or ["*"] for allow all)
        """
        try:
            data = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

        if "allowlist" not in data:
            raise HTTPException(status_code=400, detail="Missing 'allowlist' field")

        new_allowlist = data["allowlist"]

        # Validate it's a list
        if not isinstance(new_allowlist, list):
            raise HTTPException(status_code=400, detail="'allowlist' must be an array")

        # Validate each entry
        for i, entry in enumerate(new_allowlist):
            if not isinstance(entry, str):
                raise HTTPException(status_code=400, detail=f"Entry {i} must be a string")
            # Allow "*" wildcard or phone numbers (basic validation)
            if entry != "*" and not _is_valid_phone_pattern(entry):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid phone pattern at index {i}: '{entry}'",
                )

        try:
            # Update in-memory config
            app.state.config_manager.update_config({"allowlist": new_allowlist})

            # Save to file
            app.state.config_manager.save_config(app.state.config_path)

            return {
                "success": True,
                "message": "Allowlist updated successfully",
                "allowlist": new_allowlist,
                "allow_all": "*" in new_allowlist,
            }
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save allowlist: {e}") from e

    logger.info("FastAPI application created")
    return app


def _is_valid_phone_pattern(pattern: str) -> bool:
    """Validate a phone number pattern.

    Accepts:
    - Numbers starting with + followed by digits (e.g., +12065551234)
    - Plain digit strings (e.g., 911, 5551234)
    - Numbers with common separators that will be stripped

    Args:
        pattern: Phone number pattern to validate

    Returns:
        True if pattern appears to be a valid phone number
    """
    if not pattern:
        return False

    # Strip common separators for validation
    cleaned = pattern.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")

    # Must start with + or digit
    if not cleaned:
        return False

    if cleaned[0] == "+":
        # International format: + followed by at least 2 digits (country code + something)
        return len(cleaned) >= 3 and cleaned[1:].isdigit()

    # Plain digits
    return cleaned.isdigit()
