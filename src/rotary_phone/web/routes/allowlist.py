"""Allowlist management routes."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from rotary_phone.config.config_manager import ConfigError
from rotary_phone.web.models import AllowlistUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/allowlist", tags=["allowlist"])


@router.get("")
async def get_allowlist(request: Request) -> Dict[str, Any]:
    """Get current allowlist configuration."""
    allowlist: List[str] = request.app.state.config_manager.get("allowlist", [])
    return {
        "allowlist": allowlist,
        "allow_all": "*" in allowlist,
    }


@router.put("")
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
