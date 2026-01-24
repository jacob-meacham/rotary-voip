"""Speed dial management routes."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from rotary_phone.config.config_manager import ConfigError
from rotary_phone.web.models import SpeedDialEntry, SpeedDialUpdate, _is_valid_speed_dial_code

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/speed-dial", tags=["speed-dial"])


@router.get("")
async def get_speed_dial(request: Request) -> Dict[str, Any]:
    """Get current speed dial configuration."""
    speed_dial: Dict[str, str] = request.app.state.config_manager.get("speed_dial", {})
    return {"speed_dial": speed_dial}


@router.put("")
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


@router.post("")
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


@router.delete("/{code}")
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
