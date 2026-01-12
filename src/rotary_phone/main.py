"""Main entry point for the Rotary Phone VoIP Controller."""

import argparse
import logging
import signal
import sys
import time
from typing import Any, Dict, NoReturn

from rotary_phone.call_logger import CallLogger
from rotary_phone.call_manager import CallManager
from rotary_phone.config import ConfigManager
from rotary_phone.config.config_manager import ConfigError
from rotary_phone.database import Database
from rotary_phone.hardware import get_gpio
from rotary_phone.hardware.dial_reader import DialReader
from rotary_phone.hardware.dial_tone import DialTone
from rotary_phone.hardware.hook_monitor import HookMonitor
from rotary_phone.hardware.ringer import Ringer
from rotary_phone.sip.in_memory_client import InMemorySIPClient
from rotary_phone.sip.pyvoip_client import PyVoIPClient
from rotary_phone.sip.sip_client import SIPClient


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
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    return parser.parse_args()


def main() -> NoReturn:  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """Main application entry point."""
    args = parse_args()
    setup_logging(args.debug)

    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Rotary Phone VoIP Controller v0.1.0")
    logger.info("=" * 60)

    if args.mock_gpio:
        logger.info("Running in MOCK mode (no hardware required)")
    else:
        logger.info("Running with REAL hardware")

    # Load configuration
    try:
        logger.info("Loading configuration from: %s", args.config)
        config = ConfigManager(user_config_path=args.config)
        logger.info("Configuration loaded successfully")

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

    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    # Initialize hardware interface
    try:
        hardware = get_gpio(mock=args.mock_gpio)
        logger.info("Hardware interface initialized successfully")
    except RuntimeError as e:
        logger.error("Failed to initialize hardware interface: %s", e)
        sys.exit(1)

    logger.info("Phone controller starting...")

    # Get timing configuration
    timing = config.get_timing_config()
    sip_config = config.get_sip_config()

    # Initialize hardware components
    logger.info("Initializing hardware components...")
    try:
        hook_monitor = HookMonitor(
            gpio=hardware,
            debounce_time=timing.get("debounce_time", 0.05),
        )
        logger.info("  - HookMonitor initialized")

        dial_reader = DialReader(
            gpio=hardware,
            pulse_timeout=timing.get("pulse_timeout", 0.15),
        )
        logger.info("  - DialReader initialized")

        # Get optional ring sound file from hardware config
        hardware_config: Dict[str, Any] = config.get("hardware", {})
        ring_sound_file = hardware_config.get("ring_sound_file")

        ringer = Ringer(
            gpio=hardware,
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

    except Exception as e:
        logger.error("Failed to initialize hardware components: %s", e)
        sys.exit(1)

    # Initialize SIP client (use in-memory for mock mode, PyVoIP for real)
    logger.info("Initializing SIP client...")
    sip_client: SIPClient
    try:
        if args.mock_gpio or not sip_config.get("server"):
            logger.info("  - Using InMemorySIPClient (mock mode)")
            sip_client = InMemorySIPClient()
        else:
            logger.info("  - Using PyVoIPClient (real VoIP)")
            sip_client = PyVoIPClient()

    except Exception as e:
        logger.error("Failed to initialize SIP client: %s", e)
        sys.exit(1)

    # Initialize call logging database
    logger.info("Initializing call logging...")
    call_logger = None
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

    except Exception as e:
        logger.warning("Failed to initialize call logging: %s (continuing without)", e)
        call_logger = None

    # Initialize CallManager to wire everything together
    logger.info("Initializing CallManager...")
    try:
        call_manager = CallManager(
            config=config,
            hook_monitor=hook_monitor,
            dial_reader=dial_reader,
            ringer=ringer,
            sip_client=sip_client,
            dial_tone=dial_tone,
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

    # Start the call manager
    logger.info("Starting phone controller...")
    try:
        call_manager.start()
    except Exception as e:
        logger.error("Failed to start CallManager: %s", e)
        sys.exit(1)

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

    logger.info("Goodbye!")
    sys.exit(0)


if __name__ == "__main__":
    main()
