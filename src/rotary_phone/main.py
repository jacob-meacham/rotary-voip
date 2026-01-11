"""Main entry point for the Rotary Phone VoIP Controller."""

import argparse
import logging
import sys
from typing import NoReturn

from rotary_phone.config import ConfigManager
from rotary_phone.config.config_manager import ConfigError
from rotary_phone.hardware import get_gpio


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


def main() -> NoReturn:
    """Main application entry point."""
    args = parse_args()
    setup_logging(args.debug)

    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Rotary Phone VoIP Controller v0.1.0")
    logger.info("=" * 60)

    if args.mock_gpio:
        logger.info("Running in MOCK GPIO mode (no hardware required)")
    else:
        logger.info("Running in REAL GPIO mode")

    # Load configuration
    try:
        logger.info(f"Loading configuration from: {args.config}")
        config = ConfigManager(user_config_path=args.config)
        logger.info("Configuration loaded successfully")

        # Log some key config info
        sip_config = config.get_sip_config()
        if sip_config.get("server"):
            logger.info(f"SIP server: {sip_config['server']}")
        else:
            logger.warning("No SIP server configured")

        speed_dial = config.get("speed_dial", {})
        logger.info(f"Speed dial entries: {len(speed_dial)}")

        allowlist = config.get("allowlist", [])
        logger.info(f"Allowlist entries: {len(allowlist)}")

    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except FileNotFoundError:
        logger.warning(f"Config file not found: {args.config}")
        sys.exit(1)

    # Initialize GPIO
    try:
        gpio = get_gpio(mock=args.mock_gpio)
        logger.info("GPIO initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize GPIO: {e}")
        sys.exit(1)

    logger.info("Phone controller starting...")

    # TODO: Initialize hardware components with config and GPIO
    # TODO: Initialize SIP client
    # TODO: Start main event loop

    logger.info("Phone controller is ready!")
    logger.info("Press Ctrl+C to stop")

    try:
        # Main loop - will be replaced with actual phone controller
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        # Cleanup GPIO
        try:
            gpio.cleanup()
            logger.info("GPIO cleaned up")
        except Exception as e:
            logger.warning(f"Error cleaning up GPIO: {e}")
        # TODO: Cleanup other components
        logger.info("Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
