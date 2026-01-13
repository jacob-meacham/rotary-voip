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
        """Broadcast an event synchronously (from non-async code).

        This schedules the broadcast to run in the event loop.

        Args:
            event: Event to broadcast
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule the coroutine to run in the existing event loop
                asyncio.create_task(self.broadcast(event))
            else:
                # If no loop is running, run it synchronously
                asyncio.run(self.broadcast(event))
        except RuntimeError:
            # No event loop available - this can happen during shutdown
            logger.warning("Cannot broadcast event: no event loop available")
        except Exception as e:
            logger.error("Error broadcasting event synchronously: %s", e)

    @property
    def connection_count(self) -> int:
        """Get the number of active connections.

        Returns:
            Number of active WebSocket connections
        """
        return len(self.active_connections)
