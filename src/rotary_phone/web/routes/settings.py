"""Settings management routes."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from rotary_phone.config.config_manager import ConfigError
from rotary_phone.web.models import LoggingSettingsUpdate, LogLevelUpdate, TimingSettingsUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/timing")
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


@router.put("/timing")
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


@router.get("/logging")
async def get_logging_settings(request: Request) -> Dict[str, Any]:
    """Get logging configuration."""
    log_config: Dict[str, Any] = request.app.state.config_manager.get("logging", {})
    return {
        "level": log_config.get("level", "INFO"),
        "file": log_config.get("file", ""),
        "max_bytes": log_config.get("max_bytes", 10485760),
        "backup_count": log_config.get("backup_count", 3),
    }


@router.put("/logging")
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


@router.put("/log-level")
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
