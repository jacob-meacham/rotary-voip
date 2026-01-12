"""Main entry point for the Rotary Phone VoIP Controller."""

import argparse
import logging
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, NoReturn, Optional

from rotary_phone.call_logger import CallLogger
from rotary_phone.call_manager import CallManager
from rotary_phone.config import ConfigManager
from rotary_phone.config.config_manager import ConfigError
from rotary_phone.database import Database
from rotary_phone.hardware import get_gpio
from rotary_phone.hardware.dial_reader import DialReader
from rotary_phone.hardware.dial_tone import DialTone
from rotary_phone.hardware.gpio_abstraction import GPIO
from rotary_phone.hardware.hook_monitor import HookMonitor
from rotary_phone.hardware.ringer import Ringer
from rotary_phone.network.network_monitor import NetworkMonitor
from rotary_phone.sip.in_memory_client import InMemorySIPClient
from rotary_phone.sip.pyvoip_client import PyVoIPClient
from rotary_phone.sip.sip_client import SIPClient

logger = logging.getLogger(__name__)


@dataclass
class HardwareComponents:
    """Container for initialized hardware components."""

    hook_monitor: HookMonitor
    dial_reader: DialReader
    ringer: Ringer
    dial_tone: DialTone


def setup_logging(debug: bool = False) -> None:
    """Configure logging for the application.

    Args:
        debug: If True, set log level to DEBUG, otherwise INFO
    """
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed command-line arguments
    """
    parser = argparse.ArgumentParser(
        description="Rotary Phone VoIP Controller - Make calls with a vintage rotary phone"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--mock-gpio",
        action="store_true",
        help="Use mock GPIO instead of real hardware (for testing)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yml",
        help="Path to configuration file (default: config.yml)",
    )
    return parser.parse_args()


def _init_hardware(gpio: GPIO, config: ConfigManager) -> HardwareComponents:
    """Initialize all hardware components.

    Args:
        gpio: GPIO interface to use
        config: Configuration manager

    Returns:
        HardwareComponents dataclass with all initialized components

    Raises:
        Exception: If any hardware component fails to initialize
    """
    timing = config.get_timing_config()

    hook_monitor = HookMonitor(
        gpio=gpio,
        debounce_time=timing.get("hook_debounce_time", 0.01),
    )
    logger.info("  - HookMonitor initialized")

    dial_reader = DialReader(
        gpio=gpio,
        pulse_timeout=timing.get("pulse_timeout", 0.3),
    )
    logger.info("  - DialReader initialized")

    # Get optional ring sound file from hardware config
    hardware_config: Dict[str, Any] = config.get("hardware", {})
    ring_sound_file = hardware_config.get("ring_sound_file")

    ringer = Ringer(
        gpio=gpio,
        ring_on_duration=timing.get("ring_duration", 2.0),
        ring_off_duration=timing.get("ring_pause", 4.0),
        sound_file=ring_sound_file,
    )
    logger.info("  - Ringer initialized")

    # Initialize dial tone player
    audio_config: Dict[str, Any] = config.get("audio", {})
    dial_tone_file = audio_config.get("dial_tone")
    dial_tone = DialTone(sound_file=dial_tone_file)
    if dial_tone_file:
        logger.info("  - DialTone initialized with: %s", dial_tone_file)
    else:
        logger.info("  - DialTone disabled (no sound file configured)")

    return HardwareComponents(
        hook_monitor=hook_monitor,
        dial_reader=dial_reader,
        ringer=ringer,
        dial_tone=dial_tone,
    )


def _init_sip_client(config: ConfigManager, mock_mode: bool) -> SIPClient:
    """Initialize the SIP client.

    Args:
        config: Configuration manager
        mock_mode: If True, use mock SIP client

    Returns:
        Initialized SIPClient

    Raises:
        Exception: If SIP client fails to initialize
    """
    sip_config = config.get_sip_config()
    timing = config.get_timing_config()

    if mock_mode or not sip_config.get("server"):
        logger.info("  - Using InMemorySIPClient (mock mode)")
        return InMemorySIPClient()

    logger.info("  - Using PyVoIPClient (real VoIP)")
    return PyVoIPClient(
        registration_timeout=timing.get("sip_registration_timeout", 10.0),
    )


def _init_call_logging(config: ConfigManager) -> Optional[CallLogger]:
    """Initialize call logging database and logger.

    Args:
        config: Configuration manager

    Returns:
        CallLogger instance, or None if initialization fails
    """
    try:
        db_config: Dict[str, Any] = config.get("database", {})
        db_path = db_config.get("path", "calls.db")
        database = Database(db_path)
        database.init_db()
        call_logger = CallLogger(database)
        logger.info("  - Call logging initialized (database: %s)", db_path)

        # Run cleanup if configured
        cleanup_days = db_config.get("cleanup_days", 365)
        if cleanup_days > 0:
            deleted = database.cleanup_old_calls(cleanup_days)
            if deleted > 0:
                logger.info("  - Cleaned up %d old call logs", deleted)

        return call_logger

    except Exception as e:
        logger.warning("Failed to initialize call logging: %s (continuing without)", e)
        return None


def _start_web_server(call_manager: CallManager, config: ConfigManager, config_path: str) -> None:
    """Start the web admin interface in a background thread.

    Args:
        call_manager: CallManager instance
        config: Configuration manager
        config_path: Path to config file (for saving changes)
    """
    # pylint: disable=import-outside-toplevel
    from threading import Thread

    import uvicorn

    from rotary_phone.web.app import create_app

    # Create FastAPI app
    web_app = create_app(call_manager=call_manager, config_manager=config, config_path=config_path)

    # Start FastAPI in daemon thread
    def run_web_server() -> None:
        uvicorn.run(
            web_app,
            host=config.get("web.host", "0.0.0.0"),
            port=config.get("web.port", 7474),
            log_level="warning",  # Reduce uvicorn logging noise
        )

    web_thread = Thread(target=run_web_server, daemon=True, name="WebServer")
    web_thread.start()

    logger.info(
        "  - Web admin interface started at http://%s:%d",
        config.get("web.host", "0.0.0.0"),
        config.get("web.port", 7474),
    )


def _load_config(config_path: str) -> ConfigManager:
    """Load and validate configuration.

    Args:
        config_path: Path to configuration file

    Returns:
        Initialized ConfigManager

    Raises:
        SystemExit: If configuration is invalid
    """
    try:
        config = ConfigManager(user_config_path=config_path)

        # Log some key config info
        sip_config = config.get_sip_config()
        if sip_config.get("server"):
            logger.info("SIP server: %s", sip_config["server"])
        else:
            logger.warning("No SIP server configured")

        speed_dial: dict[str, str] = config.get("speed_dial", {})
        logger.info("Speed dial entries: %d", len(speed_dial))

        allowlist: list[str] = config.get("allowlist", [])
        logger.info("Allowlist entries: %d", len(allowlist))

        return config

    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)


def _init_network_monitor(
    config: ConfigManager, sip_client: SIPClient, mock_mode: bool
) -> Optional[NetworkMonitor]:
    """Initialize network connectivity monitor.

    Args:
        config: Configuration manager
        sip_client: SIP client to re-register on reconnection
        mock_mode: If True, skip network monitoring

    Returns:
        NetworkMonitor instance, or None if disabled/mock mode
    """
    if mock_mode:
        logger.info("  - Network monitoring disabled in mock mode")
        return None

    sip_config = config.get_sip_config()
    if not sip_config.get("server"):
        logger.info("  - Network monitoring disabled (no SIP server configured)")
        return None

    def on_network_connected() -> None:
        """Re-register SIP when network is restored."""
        logger.info("Network restored - re-registering SIP client")
        try:
            # Re-register with SIP server
            account_uri = f"{sip_config['server']}:{sip_config.get('port', 5060)}"
            sip_client.register(
                account_uri=account_uri,
                username=sip_config["username"],
                password=sip_config.get("password", ""),
            )
        except Exception as e:
            logger.error("Failed to re-register SIP client: %s", e)

    def on_network_disconnected() -> None:
        """Log network disconnection."""
        logger.warning("Network disconnected - calls unavailable until reconnection")

    monitor = NetworkMonitor(
        check_interval=30.0,  # Check every 30 seconds
        on_connected=on_network_connected,
        on_disconnected=on_network_disconnected,
    )
    logger.info("  - NetworkMonitor initialized")
    return monitor


def _shutdown(
    call_manager: CallManager,
    hardware: GPIO,
    network_monitor: Optional[NetworkMonitor] = None,
) -> None:
    """Perform graceful shutdown.

    Args:
        call_manager: CallManager to stop
        hardware: GPIO interface to clean up
        network_monitor: Optional network monitor to stop
    """
    if network_monitor:
        logger.info("Stopping NetworkMonitor...")
        try:
            network_monitor.stop()
            logger.info("NetworkMonitor stopped")
        except Exception as e:
            logger.warning("Error stopping NetworkMonitor: %s", e)

    logger.info("Stopping CallManager...")
    try:
        call_manager.stop()
        logger.info("CallManager stopped")
    except Exception as e:
        logger.warning("Error stopping CallManager: %s", e)

    logger.info("Cleaning up hardware...")
    try:
        hardware.cleanup()
        logger.info("Hardware cleaned up")
    except RuntimeError as e:
        logger.warning("Error cleaning up hardware: %s", e)


def main() -> NoReturn:  # pylint: disable=too-many-statements
    """Main application entry point."""
    args = parse_args()
    setup_logging(args.debug)

    logger.info("=" * 60)
    logger.info("Rotary Phone VoIP Controller v0.1.0")
    logger.info("=" * 60)

    if args.mock_gpio:
        logger.info("Running in MOCK mode (no hardware required)")
    else:
        logger.info("Running with REAL hardware")

    # Load configuration
    config = _load_config(args.config)

    # Initialize hardware interface
    try:
        hardware = get_gpio(mock=args.mock_gpio)
        logger.info("Hardware interface initialized successfully")
    except RuntimeError as e:
        logger.error("Failed to initialize hardware interface: %s", e)
        sys.exit(1)

    logger.info("Phone controller starting...")

    # Initialize hardware components
    logger.info("Initializing hardware components...")
    try:
        hw = _init_hardware(hardware, config)
    except Exception as e:
        logger.error("Failed to initialize hardware components: %s", e)
        sys.exit(1)

    # Initialize SIP client
    logger.info("Initializing SIP client...")
    try:
        sip_client = _init_sip_client(config, args.mock_gpio)
    except Exception as e:
        logger.error("Failed to initialize SIP client: %s", e)
        sys.exit(1)

    # Initialize call logging database
    logger.info("Initializing call logging...")
    call_logger = _init_call_logging(config)

    # Initialize CallManager to wire everything together
    logger.info("Initializing CallManager...")
    try:
        call_manager = CallManager(
            config=config,
            hook_monitor=hw.hook_monitor,
            dial_reader=hw.dial_reader,
            ringer=hw.ringer,
            sip_client=sip_client,
            dial_tone=hw.dial_tone,
            call_logger=call_logger,
        )
        logger.info("  - CallManager initialized")
    except Exception as e:
        logger.error("Failed to initialize CallManager: %s", e)
        sys.exit(1)

    # Set up signal handlers for graceful shutdown
    shutdown_requested = False

    def signal_handler(signum: int, _frame: object) -> None:
        nonlocal shutdown_requested
        if shutdown_requested:
            logger.warning("Force quit!")
            sys.exit(1)
        logger.info("\nShutdown requested (signal %d)...", signum)
        shutdown_requested = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize network monitor (for auto SIP re-registration)
    logger.info("Initializing network monitor...")
    network_monitor = _init_network_monitor(config, sip_client, args.mock_gpio)

    # Start web admin interface if enabled
    if config.get("web.enabled", False):
        logger.info("Starting web admin interface...")
        try:
            _start_web_server(call_manager, config, args.config)
        except Exception as e:
            logger.error("Failed to start web admin interface: %s", e)
            logger.warning("Continuing without web interface...")

    # Start the call manager
    logger.info("Starting phone controller...")
    try:
        call_manager.start()
    except Exception as e:
        logger.error("Failed to start CallManager: %s", e)
        sys.exit(1)

    # Start network monitor after call manager is ready
    if network_monitor:
        network_monitor.start()

    logger.info("=" * 60)
    logger.info("Phone controller is ready!")
    logger.info("=" * 60)
    logger.info("Press Ctrl+C to stop")

    # Main event loop
    try:
        while not shutdown_requested:
            time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("\nShutting down...")

    # Graceful shutdown
    _shutdown(call_manager, hardware, network_monitor)

    logger.info("Goodbye!")
    sys.exit(0)


if __name__ == "__main__":
    main()
