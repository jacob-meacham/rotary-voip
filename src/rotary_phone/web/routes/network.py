"""Network management routes."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from rotary_phone.config import ConfigManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/network", tags=["network"])


@router.get("/status")
async def get_network_status(_request: Request) -> Dict[str, Any]:
    """Get current network connection status."""
    try:
        # Import here to avoid issues if not on Linux
        from rotary_phone.network import WiFiManager  # pylint: disable=import-outside-toplevel

        wifi_manager = WiFiManager()
        status = wifi_manager.get_status()

        return {
            "success": True,
            "status": status.to_dict(),
        }
    except RuntimeError as e:
        # WiFi manager not available (not on Pi or nmcli missing)
        return {
            "success": False,
            "error": str(e),
            "status": {
                "connected": False,
                "ssid": None,
                "signal": None,
                "ip_address": None,
                "interface": None,
            },
        }
    except Exception as e:
        logger.error("Error getting network status: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get network status: {e}") from e


@router.get("/scan")
async def scan_networks(_request: Request) -> Dict[str, Any]:
    """Scan for available WiFi networks."""
    try:
        from rotary_phone.network import WiFiManager  # pylint: disable=import-outside-toplevel

        wifi_manager = WiFiManager()
        networks = wifi_manager.scan_networks()

        return {
            "success": True,
            "networks": [network.to_dict() for network in networks],
        }
    except RuntimeError as e:
        logger.warning("WiFi scan not available: %s", e)
        return {
            "success": False,
            "error": str(e),
            "networks": [],
        }
    except Exception as e:
        logger.error("Error scanning networks: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to scan networks: {e}") from e


@router.post("/connect")
async def connect_network(request: Request) -> Dict[str, Any]:
    """Connect to a WiFi network.

    Body:
        ssid: Network SSID
        password: Network password (optional for open networks)
    """
    try:
        from rotary_phone.network import WiFiManager  # pylint: disable=import-outside-toplevel

        body = await request.json()
        ssid = body.get("ssid")
        password = body.get("password")

        if not ssid:
            raise HTTPException(status_code=400, detail="SSID is required")

        wifi_manager = WiFiManager()
        wifi_manager.connect(ssid, password)

        # Update config with new network credentials
        config_manager: ConfigManager = request.app.state.config_manager
        network_config = {
            "network": {
                "wifi_ssid": ssid,
                "wifi_password": password or "",
            }
        }
        config_manager.update_config(network_config)
        config_manager.save_config(request.app.state.config_path)

        return {
            "success": True,
            "message": f"Connected to {ssid}",
        }
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error connecting to network: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to connect: {e}") from e


@router.post("/disconnect")
async def disconnect_network(_request: Request) -> Dict[str, Any]:
    """Disconnect from current WiFi network."""
    try:
        from rotary_phone.network import WiFiManager  # pylint: disable=import-outside-toplevel

        wifi_manager = WiFiManager()
        wifi_manager.disconnect()

        return {
            "success": True,
            "message": "Disconnected from WiFi",
        }
    except Exception as e:
        logger.error("Error disconnecting: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to disconnect: {e}") from e


@router.get("/ap/status")
async def get_ap_status(request: Request) -> Dict[str, Any]:
    """Get Access Point status."""
    # AP status is tracked in app state if running
    ap_running = (
        hasattr(request.app.state, "access_point") and request.app.state.access_point.is_running()
    )

    config_manager: ConfigManager = request.app.state.config_manager
    ap_ssid = config_manager.get("network.ap_ssid", "RotaryPhone")

    return {
        "success": True,
        "status": {
            "running": ap_running,
            "ssid": ap_ssid,
        },
    }


@router.post("/ap/start")
async def start_ap(request: Request) -> Dict[str, Any]:
    """Start Access Point mode."""
    try:
        # pylint: disable=import-outside-toplevel
        from rotary_phone.network import AccessPoint, APConfig

        config_manager: ConfigManager = request.app.state.config_manager

        # Get AP config from settings
        ap_ssid = config_manager.get("network.ap_ssid", "RotaryPhone")
        ap_password = config_manager.get("network.ap_password", "rotaryphone")

        # Create and start AP
        ap_config = APConfig(ssid=ap_ssid, password=ap_password)
        access_point = AccessPoint(ap_config)
        access_point.start()

        # Store in app state
        request.app.state.access_point = access_point

        return {
            "success": True,
            "message": f"Access Point '{ap_ssid}' started",
        }
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error starting AP: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to start AP: {e}") from e


@router.post("/ap/stop")
async def stop_ap(request: Request) -> Dict[str, Any]:
    """Stop Access Point mode."""
    try:
        if hasattr(request.app.state, "access_point"):
            request.app.state.access_point.stop()
            delattr(request.app.state, "access_point")

        return {
            "success": True,
            "message": "Access Point stopped",
        }
    except Exception as e:
        logger.error("Error stopping AP: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to stop AP: {e}") from e
