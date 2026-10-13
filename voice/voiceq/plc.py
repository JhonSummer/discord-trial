"""Packet-loss concealment: fill gaps left by dropped / late frames.

The channel + jitter buffer hand the decoder a stream of per-frame parameters with holes (``None``
for every lost or late packet). A PLC decides what to synthesize in those holes:

* ``SilencePLC`` inserts nothing — the gaps become silence. This is the naive baseline and sounds
  like the call is dropping out.
* ``ParametricPLC`` extrapolates the last good frame: it keeps the pitch and spectral envelope
  going (so the vowel continues), decays the gain a few dB per lost frame, and fades to silence
  after a maximum gap. Because the decoder is phase-continuous, a continued pitch track stitches
  across the gap instead of clicking — which is exactly what PLCMOS is trained to reward.

PLC operates on *parameters*, not waveforms, which is the natural fit for a parametric codec (and
for Lyra): concealing a lost frame is "guess the features," and the generative decoder does the
rest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Protocol

from .codec import FrameParams


class PLC(Protocol):
    def conceal(self, received: List[Optional[FrameParams]]) -> List[Optional[FrameParams]]: ...


class SilencePLC:
    """Baseline: leave gaps empty (decoder renders silence)."""

    name = "silence"

    def conceal(self, received: List[Optional[FrameParams]]) -> List[Optional[FrameParams]]:
        return list(received)


@dataclass
class ParametricPLC:
    """Extrapolate last-good parameters with gain decay and a bounded maximum gap."""

    name: str = "parametric"
    decay_db_per_frame: float = 3.0   # how fast a sustained gap fades
    max_gap_frames: int = 6           # after ~120 ms of loss, give up and go silent
    gain_floor: float = -9.0

    def conceal(self, received: List[Optional[FrameParams]]) -> List[Optional[FrameParams]]:
        out: List[Optional[FrameParams]] = []
        last: Optional[FrameParams] = None
        gap = 0
        for p in received:
            if p is not None:
                out.append(p)
                last = p
                gap = 0
                continue
            gap += 1
            if last is None or gap > self.max_gap_frames:
                out.append(None)
                continue
            decayed = max(self.gain_floor, last.gain - self.decay_db_per_frame * gap / 20.0 * math.log(10))
            out.append(FrameParams(voiced=last.voiced, f0=last.f0, gain=decayed, shape=last.shape.copy()))
        return out


def make_plc(kind: str) -> PLC:
    if kind == "silence":
        return SilencePLC()
    if kind == "parametric":
        return ParametricPLC()
    raise KeyError(f"unknown PLC {kind!r}")
