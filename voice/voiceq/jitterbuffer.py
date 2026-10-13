"""Jitter buffers: a fixed baseline and an adaptive playout-delay buffer.

A jitter buffer holds arriving packets and plays them on a steady 20 ms clock. Its one knob is
the playout delay ``D``: a packet whose network delay exceeds ``D`` misses its slot and is
counted as *late loss* (handed to PLC like any other gap). Bigger ``D`` hides more jitter at the
cost of mouth-to-ear latency.

* ``FixedJitterBuffer`` uses a constant ``D`` — simple, but either wasteful (too big) or lossy
  (too small) because real mesh jitter is non-stationary.
* ``AdaptiveJitterBuffer`` tracks a high percentile of recent network delay and sets ``D`` just
  above it, so it spends latency only when jitter actually demands it. This is the jitter-buffer
  half of the optimization the gate rewards.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from .channel import DeliveryTrace


@dataclass
class PlayoutResult:
    present: np.ndarray        # bool[n_frames] — frame available at its playout slot
    playout_delay_ms: np.ndarray  # float[n_frames] — mouth-to-ear latency for each slot
    late: int                  # frames that arrived but missed their deadline
    buffer_depth_ms: np.ndarray   # float[n_frames] — D (jitter absorbed above the base delay)

    @property
    def mean_delay_ms(self) -> float:
        return float(np.mean(self.playout_delay_ms))

    @property
    def available_rate(self) -> float:
        return float(np.mean(self.present))


def _anchor_ms(delay_ms: np.ndarray, arrived: np.ndarray) -> float:
    """Base one-way delay: the minimum network delay (what the playout clock locks onto)."""
    if not np.any(arrived):
        return 0.0
    return float(np.min(delay_ms[arrived]))


class FixedJitterBuffer:
    """Constant buffer depth ``target_ms`` above the base delay — the naive baseline."""

    def __init__(self, target_ms: float = 60.0):
        self.target_ms = target_ms

    def process(self, trace: DeliveryTrace) -> PlayoutResult:
        delay_ms = (trace.arrival_s - trace.send_s) * 1000.0
        anchor = _anchor_ms(delay_ms, trace.arrived)
        jitter_ms = delay_ms - anchor  # delay above the base: what the buffer must absorb
        present = trace.arrived & (jitter_ms <= self.target_ms + 1e-9)
        late = int(np.sum(trace.arrived & ~present))
        depth = np.full(trace.n, self.target_ms)
        return PlayoutResult(present=present, playout_delay_ms=anchor + depth, late=late, buffer_depth_ms=depth)


class AdaptiveJitterBuffer:
    """Causal percentile-tracking buffer: depth follows the recent *jitter* (delay above base)."""

    def __init__(self, percentile: float = 97.0, margin_ms: float = 12.0,
                 window: int = 64, min_ms: float = 10.0, max_ms: float = 200.0,
                 step_ms: float = 8.0):
        self.percentile = percentile
        self.margin_ms = margin_ms
        self.window = window
        self.min_ms = min_ms
        self.max_ms = max_ms
        self.step_ms = step_ms

    def process(self, trace: DeliveryTrace) -> PlayoutResult:
        delay_ms = (trace.arrival_s - trace.send_s) * 1000.0
        anchor = _anchor_ms(delay_ms, trace.arrived)
        jitter_ms = delay_ms - anchor
        recent: deque[float] = deque(maxlen=self.window)
        present = np.zeros(trace.n, dtype=bool)
        depth = np.zeros(trace.n)
        D = self.min_ms
        late = 0
        for k in range(trace.n):
            # Set depth for this slot from jitter observed so far (causal), moving it smoothly.
            target = (float(np.percentile(recent, self.percentile)) + self.margin_ms) if recent else self.min_ms
            target = float(np.clip(target, self.min_ms, self.max_ms))
            D += float(np.clip(target - D, -self.step_ms, self.step_ms))
            depth[k] = D
            if trace.arrived[k]:
                ok = jitter_ms[k] <= D + 1e-9
                present[k] = ok
                late += 0 if ok else 1
                recent.append(jitter_ms[k])
        return PlayoutResult(present=present, playout_delay_ms=anchor + depth, late=late, buffer_depth_ms=depth)
