"""Mesh channel model: packet loss (random + bursty), jitter, multi-hop delay and reordering.

This produces a per-frame *delivery trace* — for each 20 ms voice packet, whether it survives
the path and when it arrives — which the jitter buffer then turns into a playout schedule. The
impairment axes match the mesh conditions the Phase 0 ``sim.meshvoice`` simulator sweeps
(per-link error, connection-interval delay, multi-hop), but here they drive *audio* rather than
a timing model, so we can hear and score the result. A ``DeliveryTrace`` can also be built from
a ``sim`` run (``from_sim_delays``) to score the exact topology the simulator evaluated.

Loss is modeled with a Gilbert-Elliott two-state chain so losses come in *bursts* (what a
congested or fading BLE link actually does), not as independent coin flips — bursts are far
harder for PLC and are where a jitter buffer + concealment earn their keep.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from . import FRAME_MS


@dataclass(frozen=True)
class MeshCondition:
    """One named operating point on the mesh."""

    name: str
    per_hop_loss: float = 0.0     # steady-state packet-loss probability per hop
    hops: int = 1                 # relay count (multi-hop compounds loss and delay)
    base_delay_ms: float = 20.0   # per-hop base latency (≈ a BLE connection interval)
    jitter_ms: float = 5.0        # per-hop delay jitter (std of the positive delay spread)
    burst: float = 1.0            # mean bad-run length in packets (1.0 = memoryless)

    @property
    def end_to_end_loss(self) -> float:
        return 1.0 - (1.0 - self.per_hop_loss) ** self.hops


# The committed condition set spans the three axes the user named: loss, jitter, multi-hop.
CONDITIONS: Dict[str, MeshCondition] = {
    "clean":    MeshCondition("clean", per_hop_loss=0.00, hops=1, base_delay_ms=20, jitter_ms=3, burst=1.0),
    "light":    MeshCondition("light", per_hop_loss=0.02, hops=2, base_delay_ms=20, jitter_ms=10, burst=1.0),
    "moderate": MeshCondition("moderate", per_hop_loss=0.05, hops=3, base_delay_ms=25, jitter_ms=20, burst=2.0),
    "heavy":    MeshCondition("heavy", per_hop_loss=0.10, hops=3, base_delay_ms=30, jitter_ms=30, burst=3.0),
    "burst":    MeshCondition("burst", per_hop_loss=0.10, hops=3, base_delay_ms=25, jitter_ms=20, burst=6.0),
    "severe":   MeshCondition("severe", per_hop_loss=0.20, hops=4, base_delay_ms=35, jitter_ms=40, burst=4.0),
}


@dataclass
class DeliveryTrace:
    """Per-frame delivery outcome. ``arrival_s[k]`` is NaN when frame k never arrives."""

    arrived: np.ndarray       # bool[n_frames]
    arrival_s: np.ndarray     # float[n_frames], playout-clock seconds; NaN if lost
    send_s: np.ndarray        # float[n_frames], nominal capture/send time
    condition: Optional[MeshCondition] = None

    @property
    def n(self) -> int:
        return len(self.arrived)

    @property
    def loss_rate(self) -> float:
        return float(np.mean(~self.arrived))

    def reordered_fraction(self) -> float:
        """Fraction of arrived packets that land out of send order (jitter-induced reordering)."""
        t = self.arrival_s[self.arrived]
        if len(t) < 2:
            return 0.0
        return float(np.mean(np.diff(t) < 0))


def _gilbert_elliott_losses(n: int, loss: float, mean_burst: float, rng: np.random.Generator) -> np.ndarray:
    """Per-packet loss booleans from a two-state Gilbert-Elliott chain (bad state = full loss)."""
    if loss <= 0:
        return np.zeros(n, dtype=bool)
    if mean_burst <= 1.0:
        return rng.random(n) < loss
    p_bg = 1.0 / mean_burst                         # bad -> good
    p_gb = p_bg * loss / max(1.0 - loss, 1e-6)      # good -> bad (so steady-state P(bad)=loss)
    lost = np.zeros(n, dtype=bool)
    bad = rng.random() < loss
    for k in range(n):
        lost[k] = bad
        if bad:
            bad = rng.random() >= p_bg
        else:
            bad = rng.random() < p_gb
    return lost


class MeshChannel:
    def __init__(self, condition: MeshCondition):
        self.cond = condition

    def simulate(self, n_frames: int, seed: int = 0) -> DeliveryTrace:
        rng = np.random.default_rng(seed)
        c = self.cond
        frame_s = FRAME_MS / 1000.0
        send_s = np.arange(n_frames) * frame_s

        lost = np.zeros(n_frames, dtype=bool)
        delay_ms = np.zeros(n_frames)
        for _ in range(c.hops):
            lost |= _gilbert_elliott_losses(n_frames, c.per_hop_loss, c.burst, rng)
            # positive one-sided jitter (half-normal) plus a fixed per-hop base latency
            delay_ms += c.base_delay_ms + np.abs(rng.normal(0.0, c.jitter_ms, n_frames))

        arrival_s = send_s + delay_ms / 1000.0
        arrival_s[lost] = np.nan
        return DeliveryTrace(arrived=~lost, arrival_s=arrival_s, send_s=send_s, condition=c)


def from_sim_delays(send_s: np.ndarray, delay_s: np.ndarray, lost: np.ndarray) -> DeliveryTrace:
    """Build a trace from an external (e.g. ``sim.meshvoice``) per-packet delay/loss record."""
    arrival = np.asarray(send_s, dtype=float) + np.asarray(delay_s, dtype=float)
    lost = np.asarray(lost, dtype=bool)
    arrival[lost] = np.nan
    return DeliveryTrace(arrived=~lost, arrival_s=arrival, send_s=np.asarray(send_s, dtype=float))


def condition(name: str) -> MeshCondition:
    if name not in CONDITIONS:
        raise KeyError(f"unknown condition {name!r}; known: {sorted(CONDITIONS)}")
    return CONDITIONS[name]
