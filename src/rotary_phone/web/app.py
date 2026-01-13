"""FastAPI application for rotary phone web admin interface."""

# pylint: disable=too-many-lines

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from fastapi import (
    APIRouter,
    FastAPI,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from rotary_phone.call_manager import CallManager
from rotary_phone.config import ConfigManager
from rotary_phone.config.config_manager import ConfigError
from rotary_phone.database import Database
from rotary_phone.web.log_buffer import LogEntry, get_log_buffer, install_log_handler
from rotary_phone.web.models import (
    AllowlistUpdate,
    AudioGainUpdate,
    LoggingSettingsUpdate,
    LogLevelUpdate,
    RingSettingsUpdate,
    SoundAssignmentsUpdate,
    SpeedDialEntry,
    SpeedDialUpdate,
    TimingSettingsUpdate,
    _is_valid_speed_dial_code,
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

# =============================================================================
# Router Definitions
# =============================================================================

sounds_router = APIRouter(prefix="/api", tags=["sounds"])
settings_router = APIRouter(prefix="/api/settings", tags=["settings"])
logs_router = APIRouter(prefix="/api/logs", tags=["logs"])
calls_router = APIRouter(prefix="/api/calls", tags=["calls"])
allowlist_router = APIRouter(prefix="/api/allowlist", tags=["allowlist"])
speed_dial_router = APIRouter(prefix="/api/speed-dial", tags=["speed-dial"])
network_router = APIRouter(prefix="/api/network", tags=["network"])


# =============================================================================
# Sounds Router
# =============================================================================


@sounds_router.get("/sounds")
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


@sounds_router.post("/sounds/upload")
async def upload_sound(file: UploadFile) -> Dict[str, Any]:
    """Upload a new sound file."""
    if not file.filename or not file.filename.lower().endswith(".wav"):
        raise HTTPException(status_code=400, detail="Only .wav files are allowed")

    sounds_dir = Path("sounds")
    sounds_dir.mkdir(exist_ok=True)

    try:
        file_path = sounds_dir / file.filename
        content = await file.read()

        if not content.startswith(b"RIFF"):
            raise HTTPException(status_code=400, detail="Invalid WAV file format")

        file_path.write_bytes(content)

        return {
            "success": True,
            "message": f"File '{file.filename}' uploaded successfully",
            "filename": file.filename,
            "size": len(content),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {e}") from e


@sounds_router.get("/sounds/{filename}")
async def get_sound(filename: str) -> StreamingResponse:
    """Stream a sound file for playback."""
    sounds_dir = Path("sounds")
    file_path = _validate_sound_filename(filename, sounds_dir)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Sound file not found: {filename}")

    if not file_path.suffix.lower() == ".wav":
        raise HTTPException(status_code=400, detail="Only .wav files are supported")

    def iterfile() -> Iterator[bytes]:
        with open(file_path, "rb") as f:
            yield from f

    safe_filename = file_path.name
    return StreamingResponse(
        iterfile(),
        media_type="audio/wav",
        headers={"Content-Disposition": f"inline; filename={safe_filename}"},
    )


@sounds_router.delete("/sounds/{filename}")
async def delete_sound(request: Request, filename: str) -> Dict[str, Any]:
    """Delete a sound file."""
    sounds_dir = Path("sounds")
    file_path = _validate_sound_filename(filename, sounds_dir)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Sound file not found: {filename}")

    audio_config: Dict[str, str] = request.app.state.config_manager.get("audio", {})
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


@sounds_router.get("/sound-assignments")
async def get_sound_assignments(request: Request) -> Dict[str, Any]:
    """Get current sound assignments from config."""
    audio_config: Dict[str, str] = request.app.state.config_manager.get("audio", {})
    return {
        "assignments": {
            "ring_sound": audio_config.get("ring_sound", ""),
            "dial_tone": audio_config.get("dial_tone", ""),
            "busy_tone": audio_config.get("busy_tone", ""),
            "error_tone": audio_config.get("error_tone", ""),
        }
    }


@sounds_router.put("/sound-assignments")
async def update_sound_assignments(
    request: Request, data: SoundAssignmentsUpdate
) -> Dict[str, Any]:
    """Update sound assignments."""
    sounds_dir = Path("sounds")
    assignments = data.assignments.model_dump()

    # Validate sound files exist
    for key, value in assignments.items():
        if value and not (sounds_dir / Path(value).name).exists():
            if not Path(value).exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"Sound file not found for '{key}': {value}",
                )

    try:
        current_audio: Dict[str, str] = request.app.state.config_manager.get("audio", {})
        for key, value in assignments.items():
            current_audio[key] = value

        request.app.state.config_manager.update_config({"audio": current_audio})
        request.app.state.config_manager.save_config(request.app.state.config_path)

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


@sounds_router.get("/ring-settings")
async def get_ring_settings(request: Request) -> Dict[str, Any]:
    """Get ring timing settings."""
    timing = request.app.state.config_manager.get_timing_config()
    return {
        "ring_duration": timing.get("ring_duration", 2.0),
        "ring_pause": timing.get("ring_pause", 4.0),
    }


@sounds_router.put("/ring-settings")
async def update_ring_settings(request: Request, data: RingSettingsUpdate) -> Dict[str, Any]:
    """Update ring timing settings."""
    try:
        current_timing = request.app.state.config_manager.get_timing_config()

        if data.ring_duration is not None:
            current_timing["ring_duration"] = float(data.ring_duration)
        if data.ring_pause is not None:
            current_timing["ring_pause"] = float(data.ring_pause)

        request.app.state.config_manager.update_config({"timing": current_timing})
        request.app.state.config_manager.save_config(request.app.state.config_path)

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


@sounds_router.get("/audio-gain")
async def get_audio_gain(request: Request) -> Dict[str, Any]:
    """Get audio input/output gain settings."""
    audio_config: Dict[str, Any] = request.app.state.config_manager.get("audio", {})
    return {
        "input_gain": audio_config.get("input_gain", 1.0),
        "output_volume": audio_config.get("output_volume", 1.0),
    }


@sounds_router.put("/audio-gain")
async def update_audio_gain(request: Request, data: AudioGainUpdate) -> Dict[str, Any]:
    """Update audio gain settings."""
    try:
        current_audio: Dict[str, Any] = request.app.state.config_manager.get("audio", {})

        if data.input_gain is not None:
            current_audio["input_gain"] = float(data.input_gain)
        if data.output_volume is not None:
            current_audio["output_volume"] = float(data.output_volume)

        request.app.state.config_manager.update_config({"audio": current_audio})
        request.app.state.config_manager.save_config(request.app.state.config_path)

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


# =============================================================================
# Settings Router
# =============================================================================


@settings_router.get("/timing")
async def get_timing_settings(request: Request) -> Dict[str, Any]:
    """Get all timing settings."""
    timing = request.app.state.config_manager.get_timing_config()
    return {
        "inter_digit_timeout": timing.get("inter_digit_timeout", 2.0),
        "ring_duration": timing.get("ring_duration", 2.0),
        "ring_pause": timing.get("ring_pause", 4.0),
        "pulse_timeout": timing.get("pulse_timeout", 0.3),
        "hook_debounce_time": timing.get("hook_debounce_time", 0.01),
        "sip_registration_timeout": timing.get("sip_registration_timeout", 10.0),
        "call_attempt_timeout": timing.get("call_attempt_timeout", 60.0),
    }


@settings_router.put("/timing")
async def update_timing_settings(request: Request, data: TimingSettingsUpdate) -> Dict[str, Any]:
    """Update timing settings."""
    try:
        current_timing = request.app.state.config_manager.get_timing_config()
        update_data = data.model_dump(exclude_none=True)

        for key, value in update_data.items():
            current_timing[key] = float(value)

        request.app.state.config_manager.update_config({"timing": current_timing})
        request.app.state.config_manager.save_config(request.app.state.config_path)

        return {
            "success": True,
            "message": "Timing settings updated successfully",
            "timing": {
                "inter_digit_timeout": current_timing.get("inter_digit_timeout", 2.0),
                "ring_duration": current_timing.get("ring_duration", 2.0),
                "ring_pause": current_timing.get("ring_pause", 4.0),
                "pulse_timeout": current_timing.get("pulse_timeout", 0.3),
                "hook_debounce_time": current_timing.get("hook_debounce_time", 0.01),
                "sip_registration_timeout": current_timing.get("sip_registration_timeout", 10.0),
                "call_attempt_timeout": current_timing.get("call_attempt_timeout", 60.0),
            },
        }
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save timing settings: {e}") from e


@settings_router.get("/logging")
async def get_logging_settings(request: Request) -> Dict[str, Any]:
    """Get logging configuration."""
    log_config: Dict[str, Any] = request.app.state.config_manager.get("logging", {})
    return {
        "level": log_config.get("level", "INFO"),
        "file": log_config.get("file", ""),
        "max_bytes": log_config.get("max_bytes", 10485760),
        "backup_count": log_config.get("backup_count", 3),
    }


@settings_router.put("/logging")
async def update_logging_settings(request: Request, data: LoggingSettingsUpdate) -> Dict[str, Any]:
    """Update logging settings."""
    try:
        current_logging: Dict[str, Any] = request.app.state.config_manager.get("logging", {})
        update_data = data.model_dump(exclude_none=True)

        for key, value in update_data.items():
            current_logging[key] = value

        request.app.state.config_manager.update_config({"logging": current_logging})
        request.app.state.config_manager.save_config(request.app.state.config_path)

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
        raise HTTPException(status_code=500, detail=f"Failed to save logging settings: {e}") from e


@settings_router.put("/log-level")
async def change_log_level(request: Request, data: LogLevelUpdate) -> Dict[str, Any]:
    """Change the log level at runtime (no restart required)."""
    level = data.level
    root_logger = logging.getLogger()
    level_value = getattr(logging, level)
    root_logger.setLevel(level_value)

    manager = logging.Logger.manager
    for name in list(manager.loggerDict.keys()):
        if name.startswith("rotary_phone"):
            named_logger = logging.getLogger(name)
            named_logger.setLevel(level_value)

    current_logging: Dict[str, Any] = request.app.state.config_manager.get("logging", {})
    current_logging["level"] = level
    request.app.state.config_manager.update_config({"logging": current_logging})

    return {"success": True, "level": level}


# =============================================================================
# Logs Router
# =============================================================================


@logs_router.get("")
async def get_logs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    level: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Get recent log entries from the in-memory buffer."""
    log_buffer = request.app.state.log_buffer

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


@logs_router.get("/stream")
async def stream_logs(
    request: Request,
    level: Optional[str] = Query(default=None),
) -> StreamingResponse:
    """Stream log entries in real-time using Server-Sent Events (SSE)."""
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

    log_buffer = request.app.state.log_buffer

    async def event_generator() -> AsyncIterator[str]:
        """Generate SSE events for new log entries."""
        queue: asyncio.Queue[LogEntry] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def on_log_entry(entry: LogEntry) -> None:
            """Callback to queue new log entries."""
            if level_order.get(entry.level, 0) >= min_level:
                loop.call_soon_threadsafe(queue.put_nowait, entry)

        log_buffer.subscribe(on_log_entry)

        try:
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

            while True:
                if await request.is_disconnected():
                    break

                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield f"data: {json.dumps(entry.to_dict())}\n\n"
                except asyncio.TimeoutError:
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


@logs_router.delete("")
async def clear_logs(request: Request) -> Dict[str, Any]:
    """Clear the in-memory log buffer."""
    log_buffer = request.app.state.log_buffer
    log_buffer.clear()
    return {"success": True, "message": "Log buffer cleared"}


# =============================================================================
# Calls Router
# =============================================================================


@calls_router.get("")
async def get_calls(  # pylint: disable=too-many-positional-arguments
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    direction: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Get call log entries with pagination and filtering."""
    db = request.app.state.database
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    if direction and direction not in ("inbound", "outbound"):
        raise HTTPException(
            status_code=400,
            detail="Invalid direction. Must be 'inbound' or 'outbound'",
        )

    valid_statuses = ("completed", "missed", "failed", "rejected")
    if status and status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )

    calls = db.search_calls(
        direction=direction,
        status=status,
        number_pattern=search,
        limit=limit + 1,
        offset=offset,
    )

    has_more = len(calls) > limit
    if has_more:
        calls = calls[:limit]

    return {
        "calls": [call.to_dict() for call in calls],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "returned": len(calls),
        },
    }


@calls_router.get("/stats")
async def get_call_stats(
    request: Request,
    days: int = Query(default=7, ge=1, le=365),
) -> Dict[str, Any]:
    """Get call statistics for dashboard."""
    db = request.app.state.database
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    stats = db.get_call_stats(days=days)
    return {"stats": stats, "days": days}


@calls_router.get("/{call_id}")
async def get_call(request: Request, call_id: int) -> Dict[str, Any]:
    """Get a single call by ID."""
    db = request.app.state.database
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    call = db.get_call(call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    return {"call": call.to_dict()}


@calls_router.delete("/{call_id}")
async def delete_call(request: Request, call_id: int) -> Dict[str, Any]:
    """Delete a call record."""
    db = request.app.state.database
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    if not db.delete_call(call_id):
        raise HTTPException(status_code=404, detail="Call not found")

    return {"success": True, "message": f"Call {call_id} deleted"}


# =============================================================================
# Allowlist Router
# =============================================================================


@allowlist_router.get("")
async def get_allowlist(request: Request) -> Dict[str, Any]:
    """Get current allowlist configuration."""
    allowlist: List[str] = request.app.state.config_manager.get("allowlist", [])
    return {
        "allowlist": allowlist,
        "allow_all": "*" in allowlist,
    }


@allowlist_router.put("")
async def update_allowlist(request: Request, data: AllowlistUpdate) -> Dict[str, Any]:
    """Update the allowlist."""
    try:
        new_allowlist = data.allowlist

        request.app.state.config_manager.update_config({"allowlist": new_allowlist})
        request.app.state.config_manager.save_config(request.app.state.config_path)

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


# =============================================================================
# Speed Dial Router
# =============================================================================


@speed_dial_router.get("")
async def get_speed_dial(request: Request) -> Dict[str, Any]:
    """Get current speed dial configuration."""
    speed_dial: Dict[str, str] = request.app.state.config_manager.get("speed_dial", {})
    return {"speed_dial": speed_dial}


@speed_dial_router.put("")
async def update_speed_dial(request: Request, data: SpeedDialUpdate) -> Dict[str, Any]:
    """Update entire speed dial configuration."""
    try:
        new_speed_dial = data.speed_dial

        request.app.state.config_manager.update_config({"speed_dial": new_speed_dial})
        request.app.state.config_manager.save_config(request.app.state.config_path)

        return {
            "success": True,
            "message": "Speed dial updated successfully",
            "speed_dial": new_speed_dial,
        }
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save speed dial: {e}") from e


@speed_dial_router.post("")
async def add_speed_dial(request: Request, data: SpeedDialEntry) -> Dict[str, Any]:
    """Add a single speed dial entry."""
    try:
        current: Dict[str, str] = request.app.state.config_manager.get("speed_dial", {})
        current[data.code] = data.number

        request.app.state.config_manager.update_config({"speed_dial": current})
        request.app.state.config_manager.save_config(request.app.state.config_path)

        return {
            "success": True,
            "message": f"Speed dial '{data.code}' added successfully",
            "code": data.code,
            "number": data.number,
        }
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add speed dial: {e}") from e


@speed_dial_router.delete("/{code}")
async def delete_speed_dial(request: Request, code: str) -> Dict[str, Any]:
    """Delete a speed dial entry."""
    if not _is_valid_speed_dial_code(code):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid speed dial code '{code}': must be 1-2 digits",
        )

    try:
        current: Dict[str, str] = request.app.state.config_manager.get("speed_dial", {})

        if code not in current:
            raise HTTPException(status_code=404, detail=f"Speed dial '{code}' not found")

        del current[code]

        request.app.state.config_manager.update_config({"speed_dial": current})
        request.app.state.config_manager.save_config(request.app.state.config_path)

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


# =============================================================================
# Network Router
# =============================================================================


@network_router.get("/status")
async def get_network_status(request: Request) -> Dict[str, Any]:
    """Get current network connection status."""
    try:
        # Import here to avoid issues if not on Linux
        from rotary_phone.network import WiFiManager  # pylint: disable=import-outside-toplevel

        wifi_manager = WiFiManager()
        status = wifi_manager.get_status()

        return {
            "success": True,
            "status": status.to_dict(),
        }
    except RuntimeError as e:
        # WiFi manager not available (not on Pi or nmcli missing)
        return {
            "success": False,
            "error": str(e),
            "status": {
                "connected": False,
                "ssid": None,
                "signal": None,
                "ip_address": None,
                "interface": None,
            },
        }
    except Exception as e:
        logger.error("Error getting network status: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get network status: {e}") from e


@network_router.get("/scan")
async def scan_networks(request: Request) -> Dict[str, Any]:
    """Scan for available WiFi networks."""
    try:
        from rotary_phone.network import WiFiManager  # pylint: disable=import-outside-toplevel

        wifi_manager = WiFiManager()
        networks = wifi_manager.scan_networks()

        return {
            "success": True,
            "networks": [network.to_dict() for network in networks],
        }
    except RuntimeError as e:
        logger.warning("WiFi scan not available: %s", e)
        return {
            "success": False,
            "error": str(e),
            "networks": [],
        }
    except Exception as e:
        logger.error("Error scanning networks: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to scan networks: {e}") from e


@network_router.post("/connect")
async def connect_network(request: Request) -> Dict[str, Any]:
    """Connect to a WiFi network.

    Body:
        ssid: Network SSID
        password: Network password (optional for open networks)
    """
    try:
        from rotary_phone.network import WiFiManager  # pylint: disable=import-outside-toplevel

        body = await request.json()
        ssid = body.get("ssid")
        password = body.get("password")

        if not ssid:
            raise HTTPException(status_code=400, detail="SSID is required")

        wifi_manager = WiFiManager()
        wifi_manager.connect(ssid, password)

        # Update config with new network credentials
        config_manager: ConfigManager = request.app.state.config_manager
        network_config = {
            "network": {
                "wifi_ssid": ssid,
                "wifi_password": password or "",
            }
        }
        config_manager.update_config(network_config)
        config_manager.save_config(request.app.state.config_path)

        return {
            "success": True,
            "message": f"Connected to {ssid}",
        }
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error connecting to network: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to connect: {e}") from e


@network_router.post("/disconnect")
async def disconnect_network(request: Request) -> Dict[str, Any]:
    """Disconnect from current WiFi network."""
    try:
        from rotary_phone.network import WiFiManager  # pylint: disable=import-outside-toplevel

        wifi_manager = WiFiManager()
        wifi_manager.disconnect()

        return {
            "success": True,
            "message": "Disconnected from WiFi",
        }
    except Exception as e:
        logger.error("Error disconnecting: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to disconnect: {e}") from e


@network_router.get("/ap/status")
async def get_ap_status(request: Request) -> Dict[str, Any]:
    """Get Access Point status."""
    # AP status is tracked in app state if running
    ap_running = (
        hasattr(request.app.state, "access_point") and request.app.state.access_point.is_running()
    )

    config_manager: ConfigManager = request.app.state.config_manager
    ap_ssid = config_manager.get("network.ap_ssid", "RotaryPhone")

    return {
        "success": True,
        "status": {
            "running": ap_running,
            "ssid": ap_ssid,
        },
    }


@network_router.post("/ap/start")
async def start_ap(request: Request) -> Dict[str, Any]:
    """Start Access Point mode."""
    try:
        from rotary_phone.network import (
            AccessPoint,
            APConfig,
        )  # pylint: disable=import-outside-toplevel

        config_manager: ConfigManager = request.app.state.config_manager

        # Get AP config from settings
        ap_ssid = config_manager.get("network.ap_ssid", "RotaryPhone")
        ap_password = config_manager.get("network.ap_password", "rotaryphone")

        # Create and start AP
        ap_config = APConfig(ssid=ap_ssid, password=ap_password)
        access_point = AccessPoint(ap_config)
        access_point.start()

        # Store in app state
        request.app.state.access_point = access_point

        return {
            "success": True,
            "message": f"Access Point '{ap_ssid}' started",
        }
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error starting AP: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to start AP: {e}") from e


@network_router.post("/ap/stop")
async def stop_ap(request: Request) -> Dict[str, Any]:
    """Stop Access Point mode."""
    try:
        if hasattr(request.app.state, "access_point"):
            request.app.state.access_point.stop()
            delattr(request.app.state, "access_point")

        return {
            "success": True,
            "message": "Access Point stopped",
        }
    except Exception as e:
        logger.error("Error stopping AP: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to stop AP: {e}") from e


# =============================================================================
# App Factory
# =============================================================================


def create_app(  # pylint: disable=too-many-statements
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

    # Initialize log buffer for log viewer
    app.state.log_buffer = get_log_buffer()
    install_log_handler(level=logging.DEBUG)

    # Initialize WebSocket connection manager
    app.state.ws_manager = ConnectionManager()

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

    # Include routers
    app.include_router(sounds_router)
    app.include_router(settings_router)
    app.include_router(logs_router)
    app.include_router(calls_router)
    app.include_router(allowlist_router)
    app.include_router(speed_dial_router)

    # -------------------------------------------------------------------------
    # WebSocket Endpoint
    # -------------------------------------------------------------------------

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time updates."""
        ws_manager: ConnectionManager = app.state.ws_manager
        await ws_manager.connect(websocket)
        try:
            # Keep connection alive and listen for messages
            while True:
                # We don't expect messages from client, but need to keep connection alive
                # This will raise WebSocketDisconnect when client disconnects
                await websocket.receive_text()
        except WebSocketDisconnect:
            await ws_manager.disconnect(websocket)
        except Exception as e:
            logger.error("WebSocket error: %s", e)
            await ws_manager.disconnect(websocket)

    # -------------------------------------------------------------------------
    # Core Routes (defined inline as they're simple)
    # -------------------------------------------------------------------------

    @app.get("/")
    async def root() -> FileResponse:
        """Serve the main HTML page."""
        return FileResponse(static_dir / "index.html")

    @app.get("/setup")
    async def setup_page() -> FileResponse:
        """Serve the captive portal setup page."""
        return FileResponse(static_dir / "captive.html")

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
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail="Config file not found") from e
        except IOError as e:
            raise HTTPException(status_code=500, detail=f"Failed to read config: {e}") from e

    @app.post("/api/config")
    async def save_config(request: Request) -> Dict[str, Any]:
        """Save configuration file. Accepts raw YAML text."""
        # pylint: disable=import-outside-toplevel
        import tempfile

        import yaml

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

    # Add exception handler for request validation errors
    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(  # pylint: disable=too-many-return-statements
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
        # Only serve index.html for non-API routes
        if not full_path.startswith("api/") and not full_path.startswith("static/"):
            return FileResponse(static_dir / "index.html")
        # If somehow we get here for an API route, return 404
        raise HTTPException(status_code=404, detail="Not found")

    logger.info("FastAPI application created")
    return app


# =============================================================================
# Helper Functions
# =============================================================================


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

    sounds_dir_resolved = sounds_dir.resolve()
    file_path = (sounds_dir / filename).resolve()

    try:
        file_path.relative_to(sounds_dir_resolved)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename") from None

    return file_path
