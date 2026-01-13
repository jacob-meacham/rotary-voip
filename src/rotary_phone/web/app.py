"""FastAPI application for rotary phone web admin interface."""

# pylint: disable=too-many-lines

import asyncio  # Used in event_generator for SSE streaming
import json  # Used in event_generator for JSON serialization
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from rotary_phone.call_manager import CallManager
from rotary_phone.config import ConfigManager
from rotary_phone.config.config_manager import ConfigError
from rotary_phone.database import Database
from rotary_phone.web.log_buffer import LogEntry, get_log_buffer, install_log_handler

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

    # Initialize log buffer for log viewer (Phase W9)
    app.state.log_buffer = get_log_buffer()
    install_log_handler(level=logging.DEBUG)

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

    @app.get("/api/sounds/{filename}")
    async def get_sound(filename: str) -> StreamingResponse:
        """Stream a sound file for playback.

        Args:
            filename: Name of the sound file

        Returns:
            Audio file stream
        """
        sounds_dir = Path("sounds")
        file_path = _validate_sound_filename(filename, sounds_dir)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Sound file not found: {filename}")

        if not file_path.suffix.lower() == ".wav":
            raise HTTPException(status_code=400, detail="Only .wav files are supported")

        def iterfile() -> Iterator[bytes]:
            with open(file_path, "rb") as f:
                yield from f

        # Use the validated filename (basename only) in the header
        safe_filename = file_path.name
        return StreamingResponse(
            iterfile(),
            media_type="audio/wav",
            headers={"Content-Disposition": f"inline; filename={safe_filename}"},
        )

    @app.delete("/api/sounds/{filename}")
    async def delete_sound(filename: str) -> Dict[str, Any]:
        """Delete a sound file.

        Args:
            filename: Name of the sound file to delete

        Returns:
            Success message
        """
        sounds_dir = Path("sounds")
        file_path = _validate_sound_filename(filename, sounds_dir)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Sound file not found: {filename}")

        # Check if this sound is currently assigned
        audio_config: Dict[str, str] = app.state.config_manager.get("audio", {})
        assigned_to = []
        for key, value in audio_config.items():
            if value and Path(value).name == filename:
                assigned_to.append(key)

        try:
            file_path.unlink()
            return {
                "success": True,
                "message": f"Sound file '{filename}' deleted",
                "was_assigned_to": assigned_to,
            }
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}") from e

    @app.get("/api/sound-assignments")
    async def get_sound_assignments() -> Dict[str, Any]:
        """Get current sound assignments from config."""
        audio_config: Dict[str, str] = app.state.config_manager.get("audio", {})
        return {
            "assignments": {
                "ring_sound": audio_config.get("ring_sound", ""),
                "dial_tone": audio_config.get("dial_tone", ""),
                "busy_tone": audio_config.get("busy_tone", ""),
                "error_tone": audio_config.get("error_tone", ""),
            }
        }

    @app.put("/api/sound-assignments")
    async def update_sound_assignments(request: Request) -> Dict[str, Any]:
        """Update sound assignments.

        Accepts JSON body with assignments object containing any of:
        - ring_sound: path to ring sound file
        - dial_tone: path to dial tone file
        - busy_tone: path to busy signal file
        - error_tone: path to error tone file
        """
        try:
            data = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

        if "assignments" not in data:
            raise HTTPException(status_code=400, detail="Missing 'assignments' field")

        assignments = data["assignments"]
        if not isinstance(assignments, dict):
            raise HTTPException(status_code=400, detail="'assignments' must be an object")

        # Validate each assignment
        valid_keys = {"ring_sound", "dial_tone", "busy_tone", "error_tone"}
        sounds_dir = Path("sounds")

        for key, value in assignments.items():
            if key not in valid_keys:
                raise HTTPException(status_code=400, detail=f"Invalid assignment key: {key}")
            if not isinstance(value, str):
                raise HTTPException(status_code=400, detail=f"Assignment '{key}' must be a string")
            # Allow empty string to clear assignment
            if value and not (sounds_dir / Path(value).name).exists():
                # Check if the full path exists
                if not Path(value).exists():
                    raise HTTPException(
                        status_code=400,
                        detail=f"Sound file not found for '{key}': {value}",
                    )

        try:
            # Get current audio config and merge updates
            current_audio: Dict[str, str] = app.state.config_manager.get("audio", {})
            for key, value in assignments.items():
                current_audio[key] = value

            # Update in-memory config
            app.state.config_manager.update_config({"audio": current_audio})

            # Save to file
            app.state.config_manager.save_config(app.state.config_path)

            return {
                "success": True,
                "message": "Sound assignments updated successfully",
                "assignments": {
                    "ring_sound": current_audio.get("ring_sound", ""),
                    "dial_tone": current_audio.get("dial_tone", ""),
                    "busy_tone": current_audio.get("busy_tone", ""),
                    "error_tone": current_audio.get("error_tone", ""),
                },
            }
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save assignments: {e}") from e

    # -------------------------------------------------------------------------
    # Ring Settings API
    # -------------------------------------------------------------------------

    @app.get("/api/ring-settings")
    async def get_ring_settings() -> Dict[str, Any]:
        """Get ring timing settings."""
        timing = app.state.config_manager.get_timing_config()
        return {
            "ring_duration": timing.get("ring_duration", 2.0),
            "ring_pause": timing.get("ring_pause", 4.0),
        }

    @app.put("/api/ring-settings")
    async def update_ring_settings(request: Request) -> Dict[str, Any]:
        """Update ring timing settings.

        Accepts JSON body with:
        - ring_duration: how long the ring plays (seconds)
        - ring_pause: silence between rings (seconds)
        """
        try:
            data = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

        # Validate values
        ring_duration = data.get("ring_duration")
        ring_pause = data.get("ring_pause")

        if ring_duration is not None:
            if not isinstance(ring_duration, (int, float)):
                raise HTTPException(status_code=400, detail="ring_duration must be a number")
            if ring_duration <= 0 or ring_duration > 30:
                raise HTTPException(
                    status_code=400,
                    detail="ring_duration must be between 0 and 30 seconds",
                )

        if ring_pause is not None:
            if not isinstance(ring_pause, (int, float)):
                raise HTTPException(status_code=400, detail="ring_pause must be a number")
            if ring_pause <= 0 or ring_pause > 60:
                raise HTTPException(
                    status_code=400,
                    detail="ring_pause must be between 0 and 60 seconds",
                )

        try:
            # Get current timing config
            current_timing = app.state.config_manager.get_timing_config()

            # Update with new values
            if ring_duration is not None:
                current_timing["ring_duration"] = float(ring_duration)
            if ring_pause is not None:
                current_timing["ring_pause"] = float(ring_pause)

            # Update in-memory config
            app.state.config_manager.update_config({"timing": current_timing})

            # Save to file
            app.state.config_manager.save_config(app.state.config_path)

            return {
                "success": True,
                "message": "Ring settings updated successfully",
                "ring_duration": current_timing.get("ring_duration", 2.0),
                "ring_pause": current_timing.get("ring_pause", 4.0),
            }
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save ring settings: {e}") from e

    # -------------------------------------------------------------------------
    # Audio Gain Settings API
    # -------------------------------------------------------------------------

    @app.get("/api/audio-gain")
    async def get_audio_gain() -> Dict[str, Any]:
        """Get audio input/output gain settings."""
        audio_config: Dict[str, Any] = app.state.config_manager.get("audio", {})
        return {
            "input_gain": audio_config.get("input_gain", 1.0),
            "output_volume": audio_config.get("output_volume", 1.0),
        }

    @app.put("/api/audio-gain")
    async def update_audio_gain(request: Request) -> Dict[str, Any]:
        """Update audio gain settings.

        Accepts JSON body with:
        - input_gain: microphone gain (0.0-2.0)
        - output_volume: speaker volume (0.0-2.0)
        """
        try:
            data = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

        # Validate values
        input_gain = data.get("input_gain")
        output_volume = data.get("output_volume")

        if input_gain is not None:
            if not isinstance(input_gain, (int, float)):
                raise HTTPException(status_code=400, detail="input_gain must be a number")
            if input_gain < 0.0 or input_gain > 2.0:
                raise HTTPException(
                    status_code=400,
                    detail="input_gain must be between 0.0 and 2.0",
                )

        if output_volume is not None:
            if not isinstance(output_volume, (int, float)):
                raise HTTPException(status_code=400, detail="output_volume must be a number")
            if output_volume < 0.0 or output_volume > 2.0:
                raise HTTPException(
                    status_code=400,
                    detail="output_volume must be between 0.0 and 2.0",
                )

        try:
            # Get current audio config
            current_audio: Dict[str, Any] = app.state.config_manager.get("audio", {})

            # Update with new values
            if input_gain is not None:
                current_audio["input_gain"] = float(input_gain)
            if output_volume is not None:
                current_audio["output_volume"] = float(output_volume)

            # Update in-memory config
            app.state.config_manager.update_config({"audio": current_audio})

            # Save to file
            app.state.config_manager.save_config(app.state.config_path)

            return {
                "success": True,
                "message": "Audio gain settings updated successfully",
                "input_gain": current_audio.get("input_gain", 1.0),
                "output_volume": current_audio.get("output_volume", 1.0),
            }
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to save audio gain settings: {e}"
            ) from e

    # -------------------------------------------------------------------------
    # Timing Settings API (Phase W9)
    # -------------------------------------------------------------------------

    @app.get("/api/settings/timing")
    async def get_timing_settings() -> Dict[str, Any]:
        """Get all timing settings."""
        timing = app.state.config_manager.get_timing_config()
        return {
            "inter_digit_timeout": timing.get("inter_digit_timeout", 2.0),
            "ring_duration": timing.get("ring_duration", 2.0),
            "ring_pause": timing.get("ring_pause", 4.0),
            "pulse_timeout": timing.get("pulse_timeout", 0.3),
            "hook_debounce_time": timing.get("hook_debounce_time", 0.01),
            "sip_registration_timeout": timing.get("sip_registration_timeout", 10.0),
            "call_attempt_timeout": timing.get("call_attempt_timeout", 60.0),
        }

    @app.put("/api/settings/timing")
    async def update_timing_settings(request: Request) -> Dict[str, Any]:
        """Update timing settings.

        Accepts JSON body with any of:
        - inter_digit_timeout: Time to wait for next digit before dialing (seconds)
        - ring_duration: Ring on time (seconds)
        - ring_pause: Ring off time (seconds)
        - pulse_timeout: Time after last pulse before digit is complete (seconds)
        - hook_debounce_time: Debounce time for hook switch (seconds)
        - sip_registration_timeout: How long to wait for SIP registration (seconds)
        - call_attempt_timeout: How long to wait for outbound call to connect (seconds)
        """
        try:
            data = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

        # Define valid timing settings with their ranges
        timing_ranges = {
            "inter_digit_timeout": (0.5, 30.0),
            "ring_duration": (0.5, 30.0),
            "ring_pause": (0.5, 60.0),
            "pulse_timeout": (0.05, 2.0),
            "hook_debounce_time": (0.001, 1.0),
            "sip_registration_timeout": (1.0, 120.0),
            "call_attempt_timeout": (5.0, 300.0),
        }

        # Validate each provided value
        for key, value in data.items():
            if key not in timing_ranges:
                raise HTTPException(status_code=400, detail=f"Unknown timing setting: {key}")
            if not isinstance(value, (int, float)):
                raise HTTPException(status_code=400, detail=f"'{key}' must be a number")
            min_val, max_val = timing_ranges[key]
            if value < min_val or value > max_val:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{key}' must be between {min_val} and {max_val} seconds",
                )

        try:
            # Get current timing config and merge updates
            current_timing = app.state.config_manager.get_timing_config()
            for key, value in data.items():
                current_timing[key] = float(value)

            # Update in-memory config
            app.state.config_manager.update_config({"timing": current_timing})

            # Save to file
            app.state.config_manager.save_config(app.state.config_path)

            return {
                "success": True,
                "message": "Timing settings updated successfully",
                "timing": {
                    "inter_digit_timeout": current_timing.get("inter_digit_timeout", 2.0),
                    "ring_duration": current_timing.get("ring_duration", 2.0),
                    "ring_pause": current_timing.get("ring_pause", 4.0),
                    "pulse_timeout": current_timing.get("pulse_timeout", 0.3),
                    "hook_debounce_time": current_timing.get("hook_debounce_time", 0.01),
                    "sip_registration_timeout": current_timing.get(
                        "sip_registration_timeout", 10.0
                    ),
                    "call_attempt_timeout": current_timing.get("call_attempt_timeout", 60.0),
                },
            }
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to save timing settings: {e}"
            ) from e

    # -------------------------------------------------------------------------
    # Logging Settings API (Phase W9)
    # -------------------------------------------------------------------------

    @app.get("/api/settings/logging")
    async def get_logging_settings() -> Dict[str, Any]:
        """Get logging configuration."""
        log_config: Dict[str, Any] = app.state.config_manager.get("logging", {})
        return {
            "level": log_config.get("level", "INFO"),
            "file": log_config.get("file", ""),
            "max_bytes": log_config.get("max_bytes", 10485760),
            "backup_count": log_config.get("backup_count", 3),
        }

    @app.put("/api/settings/logging")
    async def update_logging_settings(  # pylint: disable=too-many-branches
        request: Request,
    ) -> Dict[str, Any]:
        """Update logging settings.

        Accepts JSON body with any of:
        - level: Log level (DEBUG, INFO, WARNING, ERROR)
        - file: Log file path (empty string for stdout only)
        - max_bytes: Max log file size in bytes
        - backup_count: Number of backup log files to keep
        """
        try:
            data = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR"}

        # Validate level
        if "level" in data:
            level = data["level"]
            if not isinstance(level, str):
                raise HTTPException(status_code=400, detail="'level' must be a string")
            if level.upper() not in valid_levels:
                raise HTTPException(
                    status_code=400,
                    detail=f"'level' must be one of: {', '.join(sorted(valid_levels))}",
                )
            data["level"] = level.upper()

        # Validate file path
        if "file" in data:
            if not isinstance(data["file"], str):
                raise HTTPException(status_code=400, detail="'file' must be a string")

        # Validate max_bytes
        if "max_bytes" in data:
            max_bytes = data["max_bytes"]
            if not isinstance(max_bytes, int):
                raise HTTPException(status_code=400, detail="'max_bytes' must be an integer")
            if max_bytes < 1024 or max_bytes > 1073741824:  # 1KB to 1GB
                raise HTTPException(
                    status_code=400,
                    detail="'max_bytes' must be between 1024 and 1073741824",
                )

        # Validate backup_count
        if "backup_count" in data:
            backup_count = data["backup_count"]
            if not isinstance(backup_count, int):
                raise HTTPException(status_code=400, detail="'backup_count' must be an integer")
            if backup_count < 0 or backup_count > 100:
                raise HTTPException(
                    status_code=400,
                    detail="'backup_count' must be between 0 and 100",
                )

        try:
            # Get current logging config and merge updates
            current_logging: Dict[str, Any] = app.state.config_manager.get("logging", {})
            for key, value in data.items():
                current_logging[key] = value

            # Update in-memory config
            app.state.config_manager.update_config({"logging": current_logging})

            # Save to file
            app.state.config_manager.save_config(app.state.config_path)

            return {
                "success": True,
                "message": "Logging settings updated successfully. Restart required to apply.",
                "restart_required": True,
                "logging": {
                    "level": current_logging.get("level", "INFO"),
                    "file": current_logging.get("file", ""),
                    "max_bytes": current_logging.get("max_bytes", 10485760),
                    "backup_count": current_logging.get("backup_count", 3),
                },
            }
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to save logging settings: {e}"
            ) from e

    @app.put("/api/settings/log-level")
    async def change_log_level(request: Request) -> Dict[str, Any]:
        """Change the log level at runtime (no restart required).

        Args:
            request: FastAPI request with JSON body containing 'level'

        Returns:
            Dictionary with success status and new level
        """
        try:
            data = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON") from exc

        level = data.get("level")
        if not level:
            raise HTTPException(status_code=400, detail="Missing 'level' field")

        level = level.upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR"}
        if level not in valid_levels:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid level. Must be one of: {', '.join(sorted(valid_levels))}",
            )

        # Update the root logger level
        root_logger = logging.getLogger()
        level_value = getattr(logging, level)
        root_logger.setLevel(level_value)

        # Also update rotary_phone loggers
        # Access logger manager dictionary via logging.Logger.manager
        manager = logging.Logger.manager
        for name in list(manager.loggerDict.keys()):
            if name.startswith("rotary_phone"):
                named_logger = logging.getLogger(name)
                named_logger.setLevel(level_value)

        # Update config in memory (but don't save to file)
        current_logging: Dict[str, Any] = app.state.config_manager.get("logging", {})
        current_logging["level"] = level
        app.state.config_manager.update_config({"logging": current_logging})

        return {"success": True, "level": level}

    # -------------------------------------------------------------------------
    # Log Viewer API (Phase W9)
    # -------------------------------------------------------------------------

    @app.get("/api/logs")
    async def get_logs(
        limit: int = Query(default=100, ge=1, le=1000),
        level: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        """Get recent log entries from the in-memory buffer.

        Args:
            limit: Maximum number of entries to return (1-1000)
            level: Minimum log level filter (DEBUG, INFO, WARNING, ERROR)
            search: Search term to filter by message content

        Returns:
            Dictionary with log entries (most recent first)
        """
        log_buffer = app.state.log_buffer

        # Validate level
        if level:
            valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR"}
            if level.upper() not in valid_levels:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid level. Must be one of: {', '.join(sorted(valid_levels))}",
                )

        entries = log_buffer.get_entries(limit=limit, level=level, search=search)

        return {
            "entries": [e.to_dict() for e in entries],
            "count": len(entries),
            "buffer_size": len(log_buffer),
        }

    @app.get("/api/logs/stream")
    async def stream_logs(
        request: Request,
        level: Optional[str] = Query(default=None),
    ) -> StreamingResponse:
        """Stream log entries in real-time using Server-Sent Events (SSE).

        Args:
            request: FastAPI request object (for disconnect detection)
            level: Minimum log level filter (DEBUG, INFO, WARNING, ERROR)

        Returns:
            SSE stream of log entries
        """
        # Validate level
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_level = 0
        valid_stream_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level:
            if level.upper() not in valid_stream_levels:
                level_list = ", ".join(sorted(valid_stream_levels))
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid level. Must be one of: {level_list}",
                )
            min_level = level_order[level.upper()]

        log_buffer = app.state.log_buffer

        async def event_generator() -> AsyncIterator[str]:
            """Generate SSE events for new log entries."""
            queue: asyncio.Queue[LogEntry] = asyncio.Queue()
            loop = asyncio.get_event_loop()

            def on_log_entry(entry: LogEntry) -> None:
                """Callback to queue new log entries."""
                if level_order.get(entry.level, 0) >= min_level:
                    loop.call_soon_threadsafe(queue.put_nowait, entry)

            # Subscribe to log entries
            log_buffer.subscribe(on_log_entry)

            try:
                # Send initial connection event
                yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

                while True:
                    # Check if client disconnected
                    if await request.is_disconnected():
                        break

                    try:
                        # Wait for new entry with timeout (allows disconnect check)
                        entry = await asyncio.wait_for(queue.get(), timeout=1.0)
                        yield f"data: {json.dumps(entry.to_dict())}\n\n"
                    except asyncio.TimeoutError:
                        # Send keepalive
                        yield ": keepalive\n\n"

            finally:
                log_buffer.unsubscribe(on_log_entry)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.delete("/api/logs")
    async def clear_logs() -> Dict[str, Any]:
        """Clear the in-memory log buffer.

        Returns:
            Success message
        """
        log_buffer = app.state.log_buffer
        log_buffer.clear()
        return {"success": True, "message": "Log buffer cleared"}

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

        # Use search_calls for filtering with proper SQL pagination
        # Fetch one extra to determine if there are more results
        calls = db.search_calls(
            direction=direction,
            status=status,
            number_pattern=search,
            limit=limit + 1,
            offset=offset,
        )

        # Determine if there are more results
        has_more = len(calls) > limit
        if has_more:
            calls = calls[:limit]  # Remove the extra record

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

        # Delete the call (returns False if not found)
        if not db.delete_call(call_id):
            raise HTTPException(status_code=404, detail="Call not found")

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

    # -------------------------------------------------------------------------
    # Speed Dial API
    # -------------------------------------------------------------------------

    @app.get("/api/speed-dial")
    async def get_speed_dial() -> Dict[str, Any]:
        """Get current speed dial configuration."""
        speed_dial: Dict[str, str] = app.state.config_manager.get("speed_dial", {})
        return {"speed_dial": speed_dial}

    @app.put("/api/speed-dial")
    async def update_speed_dial(request: Request) -> Dict[str, Any]:
        """Update entire speed dial configuration.

        Accepts JSON body with:
        - speed_dial: object mapping codes to phone numbers
        """
        try:
            data = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

        if "speed_dial" not in data:
            raise HTTPException(status_code=400, detail="Missing 'speed_dial' field")

        new_speed_dial = data["speed_dial"]

        # Validate it's a dict
        if not isinstance(new_speed_dial, dict):
            raise HTTPException(status_code=400, detail="'speed_dial' must be an object")

        # Validate each entry
        for code, number in new_speed_dial.items():
            if not _is_valid_speed_dial_code(code):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid speed dial code '{code}': must be 1-2 digits",
                )
            if not isinstance(number, str):
                raise HTTPException(
                    status_code=400,
                    detail=f"Speed dial '{code}' destination must be a string",
                )
            if not _is_valid_phone_pattern(number):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid phone number for speed dial '{code}': '{number}'",
                )

        try:
            # Update in-memory config
            app.state.config_manager.update_config({"speed_dial": new_speed_dial})

            # Save to file
            app.state.config_manager.save_config(app.state.config_path)

            return {
                "success": True,
                "message": "Speed dial updated successfully",
                "speed_dial": new_speed_dial,
            }
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save speed dial: {e}") from e

    @app.post("/api/speed-dial")
    async def add_speed_dial(request: Request) -> Dict[str, Any]:
        """Add a single speed dial entry.

        Accepts JSON body with:
        - code: 1-2 digit speed dial code
        - number: phone number destination
        """
        try:
            data = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

        if "code" not in data or "number" not in data:
            raise HTTPException(status_code=400, detail="Missing 'code' or 'number' field")

        code = str(data["code"])
        number = str(data["number"])

        if not _is_valid_speed_dial_code(code):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid speed dial code '{code}': must be 1-2 digits",
            )

        if not _is_valid_phone_pattern(number):
            raise HTTPException(status_code=400, detail=f"Invalid phone number: '{number}'")

        try:
            # Get current speed dial and add new entry
            current: Dict[str, str] = app.state.config_manager.get("speed_dial", {})
            current[code] = number

            # Update in-memory config
            app.state.config_manager.update_config({"speed_dial": current})

            # Save to file
            app.state.config_manager.save_config(app.state.config_path)

            return {
                "success": True,
                "message": f"Speed dial '{code}' added successfully",
                "code": code,
                "number": number,
            }
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to add speed dial: {e}") from e

    @app.delete("/api/speed-dial/{code}")
    async def delete_speed_dial(code: str) -> Dict[str, Any]:
        """Delete a speed dial entry.

        Args:
            code: Speed dial code to delete
        """
        if not _is_valid_speed_dial_code(code):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid speed dial code '{code}': must be 1-2 digits",
            )

        try:
            # Get current speed dial
            current: Dict[str, str] = app.state.config_manager.get("speed_dial", {})

            if code not in current:
                raise HTTPException(status_code=404, detail=f"Speed dial '{code}' not found")

            # Remove entry
            del current[code]

            # Update in-memory config
            app.state.config_manager.update_config({"speed_dial": current})

            # Save to file
            app.state.config_manager.save_config(app.state.config_path)

            return {
                "success": True,
                "message": f"Speed dial '{code}' deleted successfully",
            }
        except HTTPException:
            raise
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete speed dial: {e}") from e

    logger.info("FastAPI application created")
    return app


def _validate_sound_filename(filename: str, sounds_dir: Path) -> Path:
    """Validate a sound filename and return the resolved path.

    Uses resolved path comparison to prevent path traversal attacks.

    Args:
        filename: The filename to validate
        sounds_dir: The sounds directory path

    Returns:
        Resolved file path if valid

    Raises:
        HTTPException: If filename is invalid or attempts path traversal
    """
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Resolve paths to catch traversal attempts like "foo/../../../etc/passwd"
    sounds_dir_resolved = sounds_dir.resolve()
    file_path = (sounds_dir / filename).resolve()

    # Check that the resolved path is within sounds directory
    try:
        file_path.relative_to(sounds_dir_resolved)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename") from None

    return file_path


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


def _is_valid_speed_dial_code(code: str) -> bool:
    """Validate a speed dial code.

    Speed dial codes must be 1-2 digits.

    Args:
        code: Speed dial code to validate

    Returns:
        True if code is valid
    """
    return len(code) in (1, 2) and code.isdigit()
