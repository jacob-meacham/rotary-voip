"""Access Point mode management using hostapd and dnsmasq."""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class APConfig:
    """Access Point configuration."""

    ssid: str
    password: str
    channel: int = 6
    interface: str = "wlan0"
    ip_address: str = "192.168.4.1"
    dhcp_range_start: str = "192.168.4.2"
    dhcp_range_end: str = "192.168.4.20"


class AccessPoint:
    """Manages WiFi Access Point mode using hostapd and dnsmasq."""

    def __init__(self, config: APConfig) -> None:
        """Initialize Access Point manager.

        Args:
            config: AP configuration
        """
        self.config = config
        self._hostapd_conf_path: Optional[Path] = None
        self._dnsmasq_conf_path: Optional[Path] = None
        self._running = False

    def _check_dependencies(self) -> None:
        """Check if required tools are available."""
        for cmd in ["hostapd", "dnsmasq", "ip"]:
            try:
                subprocess.run(
                    ["which", cmd],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                raise RuntimeError(f"Required command '{cmd}' not found") from e

    def _create_hostapd_config(self) -> Path:
        """Create hostapd configuration file.

        Returns:
            Path to config file
        """
        # Use a persistent location instead of temp
        conf_dir = Path("/tmp/rotary-phone-ap")
        conf_dir.mkdir(exist_ok=True, mode=0o755)
        conf_path = conf_dir / "hostapd.conf"

        config_content = f"""interface={self.config.interface}
driver=nl80211
ssid={self.config.ssid}
hw_mode=g
channel={self.config.channel}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={self.config.password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
"""
        conf_path.write_text(config_content)
        os.chmod(conf_path, 0o600)  # Secure the password
        logger.debug("Created hostapd config at %s", conf_path)
        return conf_path

    def _create_dnsmasq_config(self) -> Path:
        """Create dnsmasq configuration file.

        Returns:
            Path to config file
        """
        conf_dir = Path("/tmp/rotary-phone-ap")
        conf_dir.mkdir(exist_ok=True, mode=0o755)
        conf_path = conf_dir / "dnsmasq.conf"

        config_content = f"""interface={self.config.interface}
dhcp-range={self.config.dhcp_range_start},{self.config.dhcp_range_end},255.255.255.0,24h
domain=rotary-phone.local
address=/#/{self.config.ip_address}
"""
        conf_path.write_text(config_content)
        logger.debug("Created dnsmasq config at %s", conf_path)
        return conf_path

    def _configure_interface(self) -> None:
        """Configure network interface for AP mode."""
        try:
            # Bring interface down
            subprocess.run(
                ["sudo", "ip", "link", "set", self.config.interface, "down"],
                check=True,
                capture_output=True,
                timeout=10,
            )

            # Set IP address
            subprocess.run(
                ["sudo", "ip", "addr", "flush", "dev", self.config.interface],
                check=True,
                capture_output=True,
                timeout=10,
            )

            subprocess.run(
                [
                    "sudo",
                    "ip",
                    "addr",
                    "add",
                    f"{self.config.ip_address}/24",
                    "dev",
                    self.config.interface,
                ],
                check=True,
                capture_output=True,
                timeout=10,
            )

            # Bring interface up
            subprocess.run(
                ["sudo", "ip", "link", "set", self.config.interface, "up"],
                check=True,
                capture_output=True,
                timeout=10,
            )

            logger.info(
                "Configured interface %s with IP %s", self.config.interface, self.config.ip_address
            )

        except subprocess.TimeoutExpired as e:
            logger.error("Timeout configuring interface: %s", e)
            raise RuntimeError("Interface configuration timeout") from e
        except subprocess.CalledProcessError as e:
            logger.error("Failed to configure interface: %s", e)
            raise RuntimeError(f"Interface configuration failed: {e.stderr}") from e

    def start(self) -> bool:
        """Start Access Point mode.

        Returns:
            True if AP started successfully

        Raises:
            RuntimeError: If AP fails to start
        """
        if self._running:
            logger.warning("Access Point already running")
            return True

        try:
            logger.info("Starting Access Point: %s", self.config.ssid)

            # Check dependencies
            self._check_dependencies()

            # Stop NetworkManager from managing the interface
            try:
                subprocess.run(
                    ["sudo", "nmcli", "device", "set", self.config.interface, "managed", "no"],
                    check=True,
                    capture_output=True,
                    timeout=10,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                logger.warning("Could not unmanage interface via NetworkManager: %s", e)

            # Configure interface
            self._configure_interface()

            # Create config files
            self._hostapd_conf_path = self._create_hostapd_config()
            self._dnsmasq_conf_path = self._create_dnsmasq_config()

            # Start dnsmasq
            subprocess.run(
                [
                    "sudo",
                    "dnsmasq",
                    "-C",
                    str(self._dnsmasq_conf_path),
                    "--no-daemon",
                    "--log-facility=-",
                ],
                check=False,  # Run in background
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Start hostapd
            subprocess.run(
                ["sudo", "hostapd", "-B", str(self._hostapd_conf_path)],
                check=True,
                capture_output=True,
                timeout=10,
            )

            self._running = True
            logger.info("Access Point started successfully")
            return True

        except RuntimeError:
            raise
        except Exception as e:
            logger.error("Failed to start Access Point: %s", e)
            self.stop()  # Clean up
            raise RuntimeError(f"AP start failed: {e}") from e

    def stop(self) -> bool:
        """Stop Access Point mode.

        Returns:
            True if AP stopped successfully
        """
        if not self._running:
            logger.debug("Access Point not running")
            return True

        try:
            logger.info("Stopping Access Point")

            # Stop hostapd
            try:
                subprocess.run(
                    ["sudo", "killall", "hostapd"],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                logger.warning("Timeout stopping hostapd")

            # Stop dnsmasq
            try:
                subprocess.run(
                    ["sudo", "killall", "dnsmasq"],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                logger.warning("Timeout stopping dnsmasq")

            # Reset interface
            try:
                subprocess.run(
                    ["sudo", "ip", "addr", "flush", "dev", self.config.interface],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
                subprocess.run(
                    ["sudo", "ip", "link", "set", self.config.interface, "down"],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                logger.warning("Timeout resetting interface")

            # Re-enable NetworkManager management
            try:
                subprocess.run(
                    ["sudo", "nmcli", "device", "set", self.config.interface, "managed", "yes"],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                logger.warning("Timeout re-enabling NetworkManager")

            # Clean up config files
            if self._hostapd_conf_path and self._hostapd_conf_path.exists():
                self._hostapd_conf_path.unlink()
            if self._dnsmasq_conf_path and self._dnsmasq_conf_path.exists():
                self._dnsmasq_conf_path.unlink()

            self._running = False
            logger.info("Access Point stopped")
            return True

        except Exception as e:
            logger.error("Error stopping Access Point: %s", e)
            return False

    def is_running(self) -> bool:
        """Check if Access Point is running.

        Returns:
            True if AP is running
        """
        try:
            # Check if hostapd is running
            result = subprocess.run(
                ["pgrep", "-f", "hostapd"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            logger.error("Error checking AP status: %s", e)
            return False

    def get_status(self) -> dict:
        """Get Access Point status.

        Returns:
            Status dictionary
        """
        return {
            "running": self.is_running(),
            "ssid": self.config.ssid,
            "ip_address": self.config.ip_address,
            "interface": self.config.interface,
        }
