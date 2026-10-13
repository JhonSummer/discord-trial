"""Adaptive bitrate / adaptive protection — the "beat the bar on Bluetooth" lever (doc 03).

The optimized pipeline can carry in-band redundancy (a coarse 3.2 kbps copy of an earlier frame
piggybacked on a later packet) so a lost frame is *recovered*, not merely concealed. Always-on
redundancy is wasteful: it pays the overhead even on a clean link, and a fixed one-frame depth
cannot recover a *burst* of two lost packets in a row.

This controller makes the protection **adaptive**: it tracks the loss the receiver is reporting
and chooses, per packet, how many prior frames to also carry (the *redundancy depth*):

* depth 0 — clean link: no overhead, just the frame itself.
* depth 1 — moderate loss: recover an isolated drop (the classic one-frame FEC).
* depth 2 — bursts: also carry the frame-before-last, so a two-in-a-row loss is still recovered.

It is deliberately **causal**: the sender composing packet ``m`` can only act on loss among
frames up to ``m - lag_frames`` (one feedback round-trip old), and the depth ramps one step at a
time rather than jumping — a real sender reacting to RTCP-style feedback, not an oracle peeking at
the future. The result is the robustness of always-on FEC at a fraction of the average bitrate
(spent only where the channel actually needs it); ``bench``/``thresholds`` quantify the trade.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# A redundant copy is coded at 3.2 kbps, so each depth level adds this many bits/s to the stream.
REDUNDANCY_BPS = 3200


@dataclass(frozen=True)
class AbrConfig:
    window: int = 50          # frames of history the receiver averages loss over (~1 s)
    lag_frames: int = 10      # feedback delay before the sender can react (~200 ms round-trip)
    low: float = 0.03         # loss below this -> drop protection (depth 0)
    high: float = 0.12        # loss at/above this -> deepest protection (depth 2)
    max_depth: int = 2


def _level_for(loss: float, cfg: AbrConfig) -> int:
    if loss < cfg.low:
        return 0
    if loss < cfg.high:
        return 1
    return cfg.max_depth


def plan_protection(present: np.ndarray, cfg: AbrConfig) -> np.ndarray:
    """Per-packet redundancy depth from causally-observed loss feedback.

    ``present[k]`` is whether frame ``k`` reached playout (drop- or late-loss both count as
    lost). Returns ``depth[m]`` = how many prior frames packet ``m`` additionally carries. The
    decision for ``m`` uses only the loss window ending at ``m - lag_frames`` (causal), and moves
    at most one level per packet so it cannot teleport to full protection the instant a burst
    starts.
    """
    present = np.asarray(present, dtype=bool)
    n = len(present)
    depth = np.zeros(n, dtype=int)
    if n == 0:
        return depth
    lost = (~present).astype(float)
    # Trailing-window loss fraction the receiver could have reported by each frame.
    csum = np.concatenate([[0.0], np.cumsum(lost)])
    cur = 0
    for m in range(n):
        end = m - cfg.lag_frames              # newest frame the sender has feedback on
        if end < 0:
            observed = 0.0
        else:
            start = max(0, end - cfg.window + 1)
            observed = (csum[end + 1] - csum[start]) / (end - start + 1)
        target = _level_for(observed, cfg)
        cur = min(cur + 1, target) if target > cur else max(cur - 1, target)
        depth[m] = cur
    return depth
