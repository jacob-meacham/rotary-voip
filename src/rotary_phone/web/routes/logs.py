"""Log viewing routes."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from rotary_phone.web.log_buffer import LogEntry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
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


@router.get("/stream")
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


@router.delete("")
async def clear_logs(request: Request) -> Dict[str, Any]:
    """Clear the in-memory log buffer."""
    log_buffer = request.app.state.log_buffer
    log_buffer.clear()
    return {"success": True, "message": "Log buffer cleared"}
