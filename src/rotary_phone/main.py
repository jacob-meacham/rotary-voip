"""Main entry point for the Rotary Phone VoIP Controller."""

import argparse
import logging
import sys
from typing import NoReturn


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

    logger.info(f"Configuration file: {args.config}")
    logger.debug("Debug logging enabled")

    logger.info("Phone controller starting...")

    # TODO: Initialize components
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
        # TODO: Cleanup components
        logger.info("Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
