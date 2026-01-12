"""Dial tone generator for rotary phone.

This module provides the DialTone class for playing a continuous dial tone
when the phone goes off-hook, similar to a real telephone experience.
"""

import logging
import subprocess
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DialTone:
    """Plays a continuous dial tone when the phone is off-hook.

    The dial tone plays in a loop until stopped (when user starts dialing
    or hangs up). Uses aplay to play a WAV file in a loop.
    """

    def __init__(self, sound_file: Optional[str] = None) -> None:
        """Initialize the dial tone player.

        Args:
            sound_file: Path to WAV file containing dial tone audio.
                       If None or file doesn't exist, dial tone is disabled.
        """
        self._sound_file = sound_file
        self._is_playing = False
        self._play_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._lock = threading.Lock()

        # Validate sound file if provided
        if self._sound_file:
            if Path(self._sound_file).exists():
                logger.debug("DialTone initialized with sound file: %s", self._sound_file)
            else:
                logger.warning(
                    "Dial tone sound file not found: %s (dial tone disabled)", self._sound_file
                )
                self._sound_file = None
        else:
            logger.debug("DialTone initialized without sound file (disabled)")

    def start(self) -> None:
        """Start playing the dial tone.

        If already playing or no sound file configured, this method has no effect.
        """
        with self._lock:
            if self._is_playing:
                logger.debug("Dial tone already playing, ignoring start request")
                return

            if not self._sound_file:
                logger.debug("No dial tone sound file configured, skipping")
                return

            self._is_playing = True
            self._stop_event.clear()
            logger.info("Starting dial tone")

            # Start playback in background thread
            self._play_thread = threading.Thread(target=self._play_loop, daemon=True)
            self._play_thread.start()

    def stop(self) -> None:
        """Stop playing the dial tone.

        If not playing, this method has no effect.
        """
        with self._lock:
            if not self._is_playing:
                logger.debug("Dial tone already stopped, ignoring stop request")
                return

            self._is_playing = False
            self._stop_event.set()
            logger.info("Stopping dial tone")

            # Kill the aplay process if running
            if self._process is not None:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                except Exception as e:
                    logger.debug("Error terminating dial tone process: %s", e)
                self._process = None

        # Wait for play thread to complete (outside lock to avoid deadlock)
        if self._play_thread is not None:
            self._play_thread.join(timeout=1.0)
            self._play_thread = None

    def is_playing(self) -> bool:
        """Check if the dial tone is currently playing.

        Returns:
            True if playing, False otherwise
        """
        with self._lock:
            return self._is_playing

    def _play_loop(self) -> None:
        """Play dial tone in a loop until stopped."""
        # Type narrowing: this method is only called when _sound_file is not None
        assert self._sound_file is not None

        while not self._stop_event.is_set():
            try:
                # Start aplay process
                with self._lock:
                    if not self._is_playing:
                        break
                    self._process = subprocess.Popen(
                        ["aplay", "-q", self._sound_file],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

                # Wait for process to complete or stop event
                while not self._stop_event.is_set():
                    try:
                        # Poll with short timeout to check stop event frequently
                        returncode = self._process.wait(timeout=0.1)
                        # Process finished, loop to play again
                        break
                    except subprocess.TimeoutExpired:
                        # Process still running, check stop event
                        continue

            except FileNotFoundError:
                logger.error("aplay command not found - dial tone disabled")
                with self._lock:
                    self._sound_file = None
                break
            except Exception as e:
                logger.error("Error playing dial tone: %s", e)
                # Brief pause before retry to avoid tight error loop
                self._stop_event.wait(timeout=0.5)
