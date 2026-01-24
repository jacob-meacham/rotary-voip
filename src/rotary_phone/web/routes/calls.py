"""Call log routes."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calls", tags=["calls"])


@router.get("")
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


@router.get("/stats")
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


@router.get("/{call_id}")
async def get_call(request: Request, call_id: int) -> Dict[str, Any]:
    """Get a single call by ID."""
    db = request.app.state.database
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    call = db.get_call(call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    return {"call": call.to_dict()}


@router.delete("/{call_id}")
async def delete_call(request: Request, call_id: int) -> Dict[str, Any]:
    """Delete a call record."""
    db = request.app.state.database
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    if not db.delete_call(call_id):
        raise HTTPException(status_code=404, detail="Call not found")

    return {"success": True, "message": f"Call {call_id} deleted"}
