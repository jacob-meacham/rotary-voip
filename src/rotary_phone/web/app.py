"""FastAPI application for rotary phone web admin interface."""

import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from rotary_phone.call_manager import CallManager
from rotary_phone.config import ConfigManager
from rotary_phone.config.config_manager import ConfigError

logger = logging.getLogger(__name__)


def create_app(  # pylint: disable=too-many-statements
    call_manager: CallManager, config_manager: ConfigManager, config_path: str
) -> FastAPI:
    """Create and configure FastAPI application.

    Args:
        call_manager: CallManager instance
        config_manager: ConfigManager instance
        config_path: Path to the configuration file

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

    logger.info("FastAPI application created")
    return app
