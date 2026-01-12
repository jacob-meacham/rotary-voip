"""Network connectivity monitor for automatic SIP re-registration.

This module provides a NetworkMonitor class that periodically checks network
connectivity and triggers SIP re-registration when the network connection
is restored after a disconnect.
"""

import logging
import socket
import threading
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class NetworkState(Enum):
    """Network connectivity states."""

    UNKNOWN = "unknown"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class NetworkMonitor:
    """Monitors network connectivity and triggers callbacks on state changes.

    Periodically checks if the network is reachable by attempting to resolve
    a DNS name or connect to a known host. When connectivity changes,
    registered callbacks are invoked.
    """

    # pylint: disable=too-many-positional-arguments
    def __init__(
        self,
        check_host: str = "8.8.8.8",
        check_port: int = 53,
        check_interval: float = 10.0,
        on_connected: Optional[Callable[[], None]] = None,
        on_disconnected: Optional[Callable[[], None]] = None,
    ) -> None:
        """Initialize the network monitor.

        Args:
            check_host: Host to check for connectivity (default: Google DNS)
            check_port: Port to connect to for check (default: 53 for DNS)
            check_interval: Seconds between connectivity checks
            on_connected: Callback when network becomes available
            on_disconnected: Callback when network becomes unavailable
        """
        self._check_host = check_host
        self._check_port = check_port
        self._check_interval = check_interval
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected

        self._state = NetworkState.UNKNOWN
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        logger.debug(
            "NetworkMonitor initialized (check_host=%s:%d, interval=%.1fs)",
            check_host,
            check_port,
            check_interval,
        )

    def start(self) -> None:
        """Start the network monitor background thread."""
        with self._lock:
            if self._running:
                logger.warning("NetworkMonitor already running")
                return

            self._running = True
            self._stop_event.clear()

            self._thread = threading.Thread(
                target=self._monitor_loop, daemon=True, name="NetworkMonitor"
            )
            self._thread.start()

            logger.info("NetworkMonitor started")

    def stop(self) -> None:
        """Stop the network monitor."""
        with self._lock:
            if not self._running:
                return

            self._running = False
            self._stop_event.set()

        # Wait for thread to finish (outside lock)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        logger.info("NetworkMonitor stopped")

    def get_state(self) -> NetworkState:
        """Get the current network state.

        Returns:
            Current NetworkState
        """
        with self._lock:
            return self._state

    def is_connected(self) -> bool:
        """Check if network is currently connected.

        Returns:
            True if connected, False otherwise
        """
        return self.get_state() == NetworkState.CONNECTED

    def set_callbacks(
        self,
        on_connected: Optional[Callable[[], None]] = None,
        on_disconnected: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set callbacks for network state changes.

        Args:
            on_connected: Callback when network becomes available
            on_disconnected: Callback when network becomes unavailable
        """
        with self._lock:
            if on_connected is not None:
                self._on_connected = on_connected
            if on_disconnected is not None:
                self._on_disconnected = on_disconnected

    def check_connectivity(self) -> bool:
        """Perform a single connectivity check.

        Returns:
            True if network is reachable, False otherwise
        """
        try:
            # Attempt to connect to the check host
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect((self._check_host, self._check_port))
            sock.close()
            return True
        except (socket.timeout, socket.error, OSError) as e:
            logger.debug("Connectivity check failed: %s", e)
            return False

    def _monitor_loop(self) -> None:
        """Background loop that periodically checks connectivity."""
        # Initial check on startup
        self._check_and_update()

        while not self._stop_event.wait(timeout=self._check_interval):
            self._check_and_update()

    def _check_and_update(self) -> None:
        """Check connectivity and update state, triggering callbacks if changed."""
        is_connected = self.check_connectivity()
        new_state = NetworkState.CONNECTED if is_connected else NetworkState.DISCONNECTED

        # Check if state changed
        with self._lock:
            old_state = self._state
            if new_state == old_state:
                return  # No change

            self._state = new_state
            on_connected = self._on_connected
            on_disconnected = self._on_disconnected

        # Log state change
        logger.info("Network state changed: %s -> %s", old_state.value, new_state.value)

        # Trigger callbacks outside lock
        if new_state == NetworkState.CONNECTED and on_connected:
            try:
                on_connected()
            except Exception as e:
                logger.error("Error in on_connected callback: %s", e)
        elif new_state == NetworkState.DISCONNECTED and on_disconnected:
            try:
                on_disconnected()
            except Exception as e:
                logger.error("Error in on_disconnected callback: %s", e)
