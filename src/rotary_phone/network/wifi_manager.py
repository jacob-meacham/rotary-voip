"""WiFi management using NetworkManager (nmcli)."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class WiFiNetwork:
    """Represents a WiFi network."""

    ssid: str
    bssid: str
    signal: int  # 0-100
    security: str  # "WPA2", "WPA3", "Open", etc.
    in_use: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ssid": self.ssid,
            "bssid": self.bssid,
            "signal": self.signal,
            "security": self.security,
            "in_use": self.in_use,
        }


@dataclass
class ConnectionStatus:
    """Current WiFi connection status."""

    connected: bool
    ssid: Optional[str] = None
    signal: Optional[int] = None
    ip_address: Optional[str] = None
    interface: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "connected": self.connected,
            "ssid": self.ssid,
            "signal": self.signal,
            "ip_address": self.ip_address,
            "interface": self.interface,
        }


class WiFiManager:
    """Manages WiFi connections using NetworkManager (nmcli)."""

    def __init__(self) -> None:
        """Initialize WiFi manager."""
        self._check_nmcli()

    def _check_nmcli(self) -> None:
        """Check if nmcli is available."""
        try:
            subprocess.run(
                ["nmcli", "--version"],
                check=True,
                capture_output=True,
                timeout=5,
            )
            logger.debug("nmcli is available")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning("nmcli not available: %s", e)
            raise RuntimeError("NetworkManager (nmcli) is not available") from e

    def scan_networks(self) -> List[WiFiNetwork]:
        """Scan for available WiFi networks.

        Returns:
            List of WiFiNetwork objects

        Raises:
            RuntimeError: If scan fails
        """
        try:
            # Rescan first
            subprocess.run(
                ["nmcli", "device", "wifi", "rescan"],
                check=False,  # Don't fail if rescan fails
                capture_output=True,
                timeout=10,
            )

            # List networks
            result = subprocess.run(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "SSID,BSSID,SIGNAL,SECURITY,IN-USE",
                    "device",
                    "wifi",
                    "list",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )

            networks = []
            seen_ssids = set()

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split(":")
                if len(parts) < 5:
                    continue

                ssid = parts[0].strip()
                bssid = parts[1].strip()
                signal_str = parts[2].strip()
                security = parts[3].strip()
                in_use = parts[4].strip() == "*"

                # Skip hidden networks
                if not ssid or ssid == "--":
                    continue

                # Skip duplicates (same SSID, keep strongest)
                if ssid in seen_ssids:
                    continue
                seen_ssids.add(ssid)

                try:
                    signal = int(signal_str)
                except ValueError:
                    signal = 0

                networks.append(
                    WiFiNetwork(
                        ssid=ssid,
                        bssid=bssid,
                        signal=signal,
                        security=security if security else "Open",
                        in_use=in_use,
                    )
                )

            # Sort by signal strength
            networks.sort(key=lambda n: n.signal, reverse=True)
            logger.info("Found %d WiFi networks", len(networks))
            return networks

        except subprocess.TimeoutExpired as e:
            logger.error("WiFi scan timeout: %s", e)
            raise RuntimeError("WiFi scan timed out") from e
        except subprocess.CalledProcessError as e:
            logger.error("WiFi scan failed: %s", e)
            raise RuntimeError(f"WiFi scan failed: {e.stderr}") from e
        except Exception as e:
            logger.error("Unexpected error during WiFi scan: %s", e)
            raise RuntimeError(f"WiFi scan error: {e}") from e

    def get_status(self) -> ConnectionStatus:  # pylint: disable=too-many-branches
        """Get current WiFi connection status.

        Returns:
            ConnectionStatus object
        """
        try:
            # Get active connection info
            result = subprocess.run(
                ["nmcli", "-t", "-f", "TYPE,NAME,DEVICE", "connection", "show", "--active"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Find WiFi connection
            wifi_connection = None
            wifi_interface = None
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) >= 3 and parts[0] == "802-11-wireless":
                    wifi_connection = parts[1]
                    wifi_interface = parts[2]
                    break

            if not wifi_connection or not wifi_interface:
                return ConnectionStatus(connected=False)

            # Get connection details
            result = subprocess.run(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "IP4.ADDRESS,802-11-WIRELESS.SSID",
                    "connection",
                    "show",
                    wifi_connection,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )

            ssid = None
            ip_address = None
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                if ":" in line:
                    key, value = line.split(":", 1)
                    if key == "802-11-WIRELESS.SSID":
                        ssid = value.strip()
                    elif key in ("IP4.ADDRESS[1]", "IP4.ADDRESS"):
                        # Extract IP from "192.168.1.100/24" format
                        ip_match = re.match(r"([0-9.]+)/\d+", value)
                        if ip_match:
                            ip_address = ip_match.group(1)

            # Get signal strength
            signal = None
            try:
                result = subprocess.run(
                    ["nmcli", "-t", "-f", "IN-USE,SIGNAL", "device", "wifi", "list"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in result.stdout.strip().split("\n"):
                    if line.startswith("*:"):
                        signal_str = line.split(":")[1] if ":" in line else "0"
                        try:
                            signal = int(signal_str)
                        except ValueError:
                            pass
                        break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass

            return ConnectionStatus(
                connected=True,
                ssid=ssid,
                signal=signal,
                ip_address=ip_address,
                interface=wifi_interface,
            )

        except subprocess.TimeoutExpired as e:
            logger.warning("Timeout getting WiFi status: %s", e)
            return ConnectionStatus(connected=False)
        except subprocess.CalledProcessError as e:
            logger.warning("Failed to get WiFi status: %s", e)
            return ConnectionStatus(connected=False)
        except Exception as e:
            logger.error("Unexpected error getting WiFi status: %s", e)
            return ConnectionStatus(connected=False)

    def connect(self, ssid: str, password: Optional[str] = None) -> bool:
        """Connect to a WiFi network.

        Args:
            ssid: Network SSID
            password: Network password (None for open networks)

        Returns:
            True if connection successful

        Raises:
            RuntimeError: If connection fails
        """
        try:
            logger.info("Connecting to WiFi network: %s", ssid)

            # Build command
            cmd = ["nmcli", "device", "wifi", "connect", ssid]
            if password:
                cmd.extend(["password", password])

            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )

            logger.info("Successfully connected to %s", ssid)
            return True

        except subprocess.TimeoutExpired as e:
            logger.error("Connection timeout for %s: %s", ssid, e)
            raise RuntimeError(f"Connection to {ssid} timed out") from e
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            logger.error("Failed to connect to %s: %s", ssid, error_msg)
            raise RuntimeError(f"Connection failed: {error_msg}") from e
        except Exception as e:
            logger.error("Unexpected error connecting to %s: %s", ssid, e)
            raise RuntimeError(f"Connection error: {e}") from e

    def disconnect(self) -> bool:
        """Disconnect from current WiFi network.

        Returns:
            True if disconnection successful
        """
        try:
            # Get current WiFi interface
            status = self.get_status()
            if not status.connected or not status.interface:
                logger.info("Not connected to WiFi")
                return True

            # Disconnect
            subprocess.run(
                ["nmcli", "device", "disconnect", status.interface],
                check=True,
                capture_output=True,
                timeout=10,
            )

            logger.info("Disconnected from WiFi")
            return True

        except subprocess.TimeoutExpired as e:
            logger.error("Disconnect timeout: %s", e)
            return False
        except subprocess.CalledProcessError as e:
            logger.error("Failed to disconnect: %s", e)
            return False
        except Exception as e:
            logger.error("Unexpected error disconnecting: %s", e)
            return False

    def forget_network(self, ssid: str) -> bool:
        """Forget a saved WiFi network.

        Args:
            ssid: Network SSID to forget

        Returns:
            True if successful
        """
        try:
            # Get connection UUID by SSID
            result = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,UUID", "connection", "show"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )

            uuid = None
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) >= 2 and parts[0] == ssid:
                    uuid = parts[1]
                    break

            if not uuid:
                logger.warning("Network %s not found in saved connections", ssid)
                return False

            # Delete connection
            subprocess.run(
                ["nmcli", "connection", "delete", uuid],
                check=True,
                capture_output=True,
                timeout=5,
            )

            logger.info("Forgot network: %s", ssid)
            return True

        except subprocess.TimeoutExpired as e:
            logger.error("Timeout forgetting network %s: %s", ssid, e)
            return False
        except subprocess.CalledProcessError as e:
            logger.error("Failed to forget network %s: %s", ssid, e)
            return False
        except Exception as e:
            logger.error("Unexpected error forgetting network %s: %s", ssid, e)
            return False
