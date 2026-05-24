"""WebSocket connection manager."""

from __future__ import annotations

import asyncio
import logging
from typing import List

from fastapi import WebSocket

from .events import WebSocketEvent

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        """Initialize connection manager."""
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()
        # Reference to the event loop the FastAPI app is running on. Captured
        # from the lifespan startup so non-async callers (sync callbacks from
        # CallManager running in worker threads) can schedule coroutines onto
        # the right loop via run_coroutine_threadsafe.
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the event loop that broadcast_sync should target.

        Args:
            loop: The asyncio event loop owned by the FastAPI app.
        """
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection.

        Args:
            websocket: WebSocket connection to register
        """
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(
            "WebSocket client connected. Total connections: %d", len(self.active_connections)
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection.

        Args:
            websocket: WebSocket connection to remove
        """
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(
            "WebSocket client disconnected. Total connections: %d", len(self.active_connections)
        )

    async def send_personal_message(self, message: str, websocket: WebSocket) -> None:
        """Send a message to a specific connection.

        Args:
            message: Message to send
            websocket: Target WebSocket connection
        """
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.warning("Failed to send personal message: %s", e)
            await self.disconnect(websocket)

    async def broadcast(self, event: WebSocketEvent) -> None:
        """Broadcast an event to all connected clients.

        Args:
            event: Event to broadcast
        """
        if not self.active_connections:
            return

        message = event.model_dump_json()
        logger.debug(
            "Broadcasting event: %s to %d clients", event.type, len(self.active_connections)
        )

        # Create a copy of connections to iterate over
        async with self._lock:
            connections = self.active_connections.copy()

        # Send to all connections, removing any that fail
        disconnected = []
        for connection in connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning("Failed to send to WebSocket client: %s", e)
                disconnected.append(connection)

        # Remove disconnected clients
        if disconnected:
            async with self._lock:
                for connection in disconnected:
                    if connection in self.active_connections:
                        self.active_connections.remove(connection)
            logger.info("Removed %d disconnected clients", len(disconnected))

    def broadcast_sync(self, event: WebSocketEvent) -> None:
        """Broadcast an event synchronously from a non-async thread.

        Schedules the broadcast coroutine onto the FastAPI event loop using
        run_coroutine_threadsafe, which is thread-safe (asyncio.create_task
        is not — it requires being called from within the loop's own thread).

        Args:
            event: Event to broadcast
        """
        if self._loop is None:
            # Lifespan hasn't called set_event_loop yet, or we're already past
            # shutdown. Either way, no loop to schedule onto.
            logger.debug("Cannot broadcast event: event loop not yet registered")
            return

        if not self._loop.is_running():
            logger.debug("Cannot broadcast event: event loop is not running (shutting down?)")
            return

        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(event), self._loop)
        except RuntimeError as e:
            # Loop got torn down between is_running check and the schedule call.
            logger.debug("Cannot broadcast event: %s", e)
        except Exception as e:
            logger.error("Error broadcasting event synchronously: %s", e)

    @property
    def connection_count(self) -> int:
        """Get the number of active connections.

        Returns:
            Number of active WebSocket connections
        """
        return len(self.active_connections)
