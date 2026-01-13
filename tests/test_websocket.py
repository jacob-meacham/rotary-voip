"""Tests for the WebSocket module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rotary_phone.web.websocket.events import (
    CallEndedEvent,
    CallLogUpdatedEvent,
    CallStartedEvent,
    ConfigChangedEvent,
    DigitDialedEvent,
    EventType,
    PhoneStateChangedEvent,
    WebSocketEvent,
)
from rotary_phone.web.websocket.manager import ConnectionManager


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self, should_fail: bool = False) -> None:
        """Initialize mock WebSocket.

        Args:
            should_fail: If True, send_text will raise an exception
        """
        self.should_fail = should_fail
        self.accepted = False
        self.sent_messages: list[str] = []

    async def accept(self) -> None:
        """Accept the WebSocket connection."""
        self.accepted = True

    async def send_text(self, data: str) -> None:
        """Send text data over WebSocket."""
        if self.should_fail:
            raise ConnectionError("WebSocket disconnected")
        self.sent_messages.append(data)


class TestWebSocketEvents:
    """Tests for WebSocket event models."""

    def test_base_event(self) -> None:
        """Test base WebSocketEvent creation."""
        event = WebSocketEvent(type=EventType.CONFIG_CHANGED, data={"key": "value"})

        assert event.type == EventType.CONFIG_CHANGED
        assert event.data == {"key": "value"}
        assert event.timestamp.endswith("Z")

    def test_phone_state_changed_event(self) -> None:
        """Test PhoneStateChangedEvent creation."""
        event = PhoneStateChangedEvent(old_state="idle", new_state="dialing", current_number="123")

        assert event.type == EventType.PHONE_STATE_CHANGED
        assert event.data["old_state"] == "idle"
        assert event.data["new_state"] == "dialing"
        assert event.data["current_number"] == "123"

    def test_phone_state_changed_event_without_number(self) -> None:
        """Test PhoneStateChangedEvent without current number."""
        event = PhoneStateChangedEvent(old_state="dialing", new_state="idle")

        assert "current_number" not in event.data

    def test_call_started_event(self) -> None:
        """Test CallStartedEvent creation."""
        event = CallStartedEvent(direction="outbound", number="+15551234567")

        assert event.type == EventType.CALL_STARTED
        assert event.data["direction"] == "outbound"
        assert event.data["number"] == "+15551234567"

    def test_call_ended_event(self) -> None:
        """Test CallEndedEvent creation."""
        event = CallEndedEvent(
            direction="inbound",
            number="+15551234567",
            duration=120.5,
            status="completed",
        )

        assert event.type == EventType.CALL_ENDED
        assert event.data["direction"] == "inbound"
        assert event.data["number"] == "+15551234567"
        assert event.data["duration"] == 120.5
        assert event.data["status"] == "completed"

    def test_digit_dialed_event(self) -> None:
        """Test DigitDialedEvent creation."""
        event = DigitDialedEvent(digit="5", number_so_far="55")

        assert event.type == EventType.DIGIT_DIALED
        assert event.data["digit"] == "5"
        assert event.data["number_so_far"] == "55"

    def test_config_changed_event(self) -> None:
        """Test ConfigChangedEvent creation."""
        event = ConfigChangedEvent(section="speed_dial")

        assert event.type == EventType.CONFIG_CHANGED
        assert event.data["section"] == "speed_dial"

    def test_call_log_updated_event(self) -> None:
        """Test CallLogUpdatedEvent creation."""
        event = CallLogUpdatedEvent(call_id=42)

        assert event.type == EventType.CALL_LOG_UPDATED
        assert event.data["call_id"] == 42

    def test_event_json_serialization(self) -> None:
        """Test that events can be serialized to JSON."""
        event = CallStartedEvent(direction="outbound", number="123")

        json_str = event.model_dump_json()

        assert "call_started" in json_str
        assert "outbound" in json_str
        assert "123" in json_str


class TestConnectionManager:
    """Tests for the ConnectionManager class."""

    def test_init(self) -> None:
        """Test ConnectionManager initialization."""
        manager = ConnectionManager()

        assert manager.active_connections == []
        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_connect(self) -> None:
        """Test connecting a WebSocket."""
        manager = ConnectionManager()
        ws = MockWebSocket()

        await manager.connect(ws)

        assert ws.accepted
        assert ws in manager.active_connections
        assert manager.connection_count == 1

    @pytest.mark.asyncio
    async def test_connect_multiple(self) -> None:
        """Test connecting multiple WebSockets."""
        manager = ConnectionManager()
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        ws3 = MockWebSocket()

        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.connect(ws3)

        assert manager.connection_count == 3
        assert ws1 in manager.active_connections
        assert ws2 in manager.active_connections
        assert ws3 in manager.active_connections

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        """Test disconnecting a WebSocket."""
        manager = ConnectionManager()
        ws = MockWebSocket()

        await manager.connect(ws)
        await manager.disconnect(ws)

        assert ws not in manager.active_connections
        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self) -> None:
        """Test disconnecting a WebSocket that's not connected."""
        manager = ConnectionManager()
        ws = MockWebSocket()

        await manager.disconnect(ws)  # Should not raise

        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_send_personal_message(self) -> None:
        """Test sending a personal message."""
        manager = ConnectionManager()
        ws = MockWebSocket()

        await manager.connect(ws)
        await manager.send_personal_message("Hello!", ws)

        assert "Hello!" in ws.sent_messages

    @pytest.mark.asyncio
    async def test_send_personal_message_failure(self) -> None:
        """Test that failed personal message removes connection."""
        manager = ConnectionManager()
        ws = MockWebSocket(should_fail=True)

        await manager.connect(ws)
        await manager.send_personal_message("Hello!", ws)

        assert ws not in manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast(self) -> None:
        """Test broadcasting an event to all connections."""
        manager = ConnectionManager()
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        ws3 = MockWebSocket()

        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.connect(ws3)

        event = CallStartedEvent(direction="outbound", number="123")
        await manager.broadcast(event)

        for ws in [ws1, ws2, ws3]:
            assert len(ws.sent_messages) == 1
            assert "call_started" in ws.sent_messages[0]

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self) -> None:
        """Test broadcasting when no connections exist."""
        manager = ConnectionManager()
        event = CallStartedEvent(direction="outbound", number="123")

        await manager.broadcast(event)  # Should not raise

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_connections(self) -> None:
        """Test that broadcast removes connections that fail."""
        manager = ConnectionManager()
        ws1 = MockWebSocket()
        ws2 = MockWebSocket(should_fail=True)
        ws3 = MockWebSocket()

        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.connect(ws3)

        event = CallStartedEvent(direction="outbound", number="123")
        await manager.broadcast(event)

        assert ws1 in manager.active_connections
        assert ws2 not in manager.active_connections
        assert ws3 in manager.active_connections
        assert manager.connection_count == 2

    def test_broadcast_sync_with_running_loop(self) -> None:
        """Test synchronous broadcast when event loop is running."""
        manager = ConnectionManager()

        async def run_test() -> None:
            ws = MockWebSocket()
            await manager.connect(ws)

            event = CallStartedEvent(direction="outbound", number="123")
            manager.broadcast_sync(event)

            # Give the scheduled task a chance to run
            await asyncio.sleep(0.01)

            assert len(ws.sent_messages) == 1

        asyncio.run(run_test())

    def test_broadcast_sync_no_loop(self) -> None:
        """Test synchronous broadcast when no event loop exists."""
        manager = ConnectionManager()
        event = CallStartedEvent(direction="outbound", number="123")

        # This should not raise, just log a warning
        with patch("rotary_phone.web.websocket.manager.asyncio.get_event_loop") as mock:
            mock.side_effect = RuntimeError("No event loop")
            manager.broadcast_sync(event)  # Should not raise

    def test_broadcast_sync_other_error(self) -> None:
        """Test synchronous broadcast with other errors."""
        manager = ConnectionManager()
        event = CallStartedEvent(direction="outbound", number="123")

        with patch("rotary_phone.web.websocket.manager.asyncio.get_event_loop") as mock:
            mock.side_effect = ValueError("Unexpected error")
            manager.broadcast_sync(event)  # Should not raise

    def test_connection_count_property(self) -> None:
        """Test connection_count property."""
        manager = ConnectionManager()

        assert manager.connection_count == 0

        async def add_connections() -> None:
            ws1 = MockWebSocket()
            ws2 = MockWebSocket()
            await manager.connect(ws1)
            await manager.connect(ws2)

        asyncio.run(add_connections())

        assert manager.connection_count == 2


class TestConnectionManagerThreadSafety:
    """Tests for thread safety of ConnectionManager."""

    @pytest.mark.asyncio
    async def test_concurrent_connects(self) -> None:
        """Test multiple concurrent connections."""
        manager = ConnectionManager()
        websockets = [MockWebSocket() for _ in range(10)]

        # Connect all concurrently
        await asyncio.gather(*[manager.connect(ws) for ws in websockets])

        assert manager.connection_count == 10

    @pytest.mark.asyncio
    async def test_concurrent_disconnects(self) -> None:
        """Test multiple concurrent disconnections."""
        manager = ConnectionManager()
        websockets = [MockWebSocket() for _ in range(10)]

        # Connect all
        for ws in websockets:
            await manager.connect(ws)

        # Disconnect all concurrently
        await asyncio.gather(*[manager.disconnect(ws) for ws in websockets])

        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_concurrent_connect_disconnect(self) -> None:
        """Test concurrent connect and disconnect operations."""
        manager = ConnectionManager()
        websockets = [MockWebSocket() for _ in range(10)]

        # Connect half, then do mixed operations
        for ws in websockets[:5]:
            await manager.connect(ws)

        async def mixed_ops() -> None:
            # Connect remaining
            for ws in websockets[5:]:
                await manager.connect(ws)
            # Disconnect first ones
            for ws in websockets[:5]:
                await manager.disconnect(ws)

        await mixed_ops()

        assert manager.connection_count == 5
        for ws in websockets[5:]:
            assert ws in manager.active_connections
