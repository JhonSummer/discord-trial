"""Codec frame model.

Lyra v2 operates at 3.2 / 6 / 9.2 kbps (v1 was ~3 kbps). The product uses Lyra because a
voice stream an order of magnitude smaller than Opus is what makes a bandwidth-starved BLE
mesh viable. ``frame_ms`` is a calibration parameter (default 20 ms = 50 frames/s); the
on-device bench in Phase 4 can recalibrate it without touching the model.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CodecProfile:
    name: str
    bitrate_bps: int
    frame_ms: float = 20.0

    def __post_init__(self) -> None:
        if self.bitrate_bps <= 0:
            raise ValueError("bitrate_bps must be positive")
        if self.frame_ms <= 0:
            raise ValueError("frame_ms must be positive")

    @property
    def frame_seconds(self) -> float:
        return self.frame_ms / 1000.0

    @property
    def frames_per_second(self) -> float:
        return 1000.0 / self.frame_ms

    @property
    def payload_bytes(self) -> float:
        """Codec payload carried by one frame at this bitrate."""
        return self.bitrate_bps * self.frame_seconds / 8.0

    def packet_bits(self, frames_per_packet: int = 1, overhead_bytes: float = 0.0) -> int:
        """Bits on the wire for a packet of ``frames_per_packet`` frames + fixed overhead.

        Overhead (SRTP + mesh envelope header) is per-packet, so batching multiple frames
        per packet amortizes it — a real lever for BLE, where tiny voice frames otherwise
        pay a large relative header cost.
        """
        if frames_per_packet < 1:
            raise ValueError("frames_per_packet must be >= 1")
        if overhead_bytes < 0:
            raise ValueError("overhead_bytes must be >= 0")
        total_bytes = frames_per_packet * self.payload_bytes + overhead_bytes
        return int(round(total_bytes * 8))


LYRA_V1_3000 = CodecProfile("lyra_v1_3.0k", 3000)
LYRA_V2_3200 = CodecProfile("lyra_v2_3.2k", 3200)
LYRA_V2_6000 = CodecProfile("lyra_v2_6.0k", 6000)
LYRA_V2_9200 = CodecProfile("lyra_v2_9.2k", 9200)

PROFILES = {p.name: p for p in (LYRA_V1_3000, LYRA_V2_3200, LYRA_V2_6000, LYRA_V2_9200)}


def by_name(name: str) -> CodecProfile:
    if name not in PROFILES:
        raise KeyError(f"unknown codec profile {name!r}; known: {sorted(PROFILES)}")
    return PROFILES[name]
