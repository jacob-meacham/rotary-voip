"""Monkey-patches for pyVoIP to preserve μ-law dynamic range end-to-end.

pyVoIP's RTP layer normally decodes μ-law to 8-bit linear PCM
(``audioop.ulaw2lin(payload, 1)``) before handing data to ``read_audio``, and
expects 8-bit linear PCM from ``write_audio`` which it re-encodes with
``audioop.lin2ulaw(packet, 1)``. The 8-bit linear intermediate throws away the
~5 bits of effective dynamic range μ-law actually carries, and the floor-
rounding of 16→8-bit conversion biases near-silence samples toward -1 (the
distinctive 0x7F peak you can see in raw recordings).

These patches make ``RTPClient`` pass raw μ-law payloads through unchanged in
both directions. Callers do their own μ-law ↔ 16-bit signed PCM conversions
using ``audioop`` width=2, keeping the full dynamic range. The silence pad byte
is also flipped from 0x80 to 0xFF (μ-law silence) so the existing blocking-
read behavior in ``RTPClient.read`` still works correctly.

Apply once at process startup via :func:`apply_patches`.
"""

import threading
import time
from typing import Any

from pyVoIP import RTP as _rtp

# μ-law's encoding of "0" magnitude is 0xFF.
_MULAW_SILENCE = b"\xff"

_lock = threading.Lock()
_applied = False


def apply_patches() -> None:
    """Install the patches. Idempotent."""
    global _applied
    with _lock:
        if _applied:
            return

        def parse_pcmu(self: Any, packet: Any) -> None:
            self.pmin.write(packet.timestamp, packet.payload)

        def encode_pcmu(self: Any, packet: bytes) -> bytes:
            return packet

        def pm_read(self: Any, length: int = 160) -> bytes:
            with self.bufferLock:
                packet = self.buffer.read(length)
                if len(packet) < length:
                    packet = packet + (_MULAW_SILENCE * (length - len(packet)))
            return bytes(packet)

        def rtp_read(self: Any, length: int = 160, blocking: bool = True) -> bytes:
            if not blocking:
                return bytes(self.pmin.read(length))
            packet = self.pmin.read(length)
            while packet == (_MULAW_SILENCE * length) and self.NSD:
                time.sleep(0.01)
                packet = self.pmin.read(length)
            return bytes(packet)

        _rtp.RTPClient.parse_pcmu = parse_pcmu  # type: ignore[method-assign]
        _rtp.RTPClient.encode_pcmu = encode_pcmu  # type: ignore[method-assign]
        _rtp.RTPPacketManager.read = pm_read  # type: ignore[method-assign]
        _rtp.RTPClient.read = rtp_read  # type: ignore[method-assign]

        _applied = True
