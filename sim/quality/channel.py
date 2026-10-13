"""Turn a mesh scenario into the frame-loss pattern Lyra's decoder conceals.

Each 20 ms Lyra frame is one simulator packet. A frame is played only when its
fate is ``ok``. Residual per-link errors compound across hops, a full jitter
buffer drops late frames, and extra calls on the same path create congestion
loss. Frames that miss playout are concealed by Lyra (its fixed packet-loss
pattern); arrival jitter inside the buffer does not time-warp the waveform.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

from meshvoice.codec import CodecProfile
from meshvoice.metrics import per_call
from meshvoice.network import LinkParams, line
from meshvoice.simulator import Call, SimParams, Simulator

from .speech import FRAME_SAMPLES, N_FRAMES, SAMPLE_RATE

FRAME_S = 0.02
OVERHEAD_BYTES = 12.0  # SRTP + mesh envelope, same header the capacity sweep uses
HOP_SAMPLES = FRAME_SAMPLES


@dataclass(frozen=True)
class MeshCondition:
    name: str
    hops: int
    per: float
    jitter_buffer_ms: float
    n_calls: int = 1
    capacity_bps: float = 37_500.0
    connection_interval_ms: float = 15.0
    seed: int = 11
    role: str = "hold"  # hold = usable-call bar; watch = stress, still gated


# Hold rows are calls the mesh design treats as usable. Watch rows are stress
# cases (loss above the 2% QoS cap, a jitter buffer shorter than the connection
# interval, a long path, a loaded relay). Both are gated; the floors differ.
CONDITIONS: Tuple[MeshCondition, ...] = (
    MeshCondition("clean", hops=1, per=0.0, jitter_buffer_ms=60.0, role="hold"),
    MeshCondition("loss_2pct", hops=1, per=0.02, jitter_buffer_ms=60.0, role="hold"),
    MeshCondition("loss_5pct", hops=1, per=0.05, jitter_buffer_ms=60.0, role="watch"),
    MeshCondition("jitter_tight", hops=1, per=0.0, jitter_buffer_ms=8.0, role="watch"),
    MeshCondition("hop3", hops=3, per=0.005, jitter_buffer_ms=60.0, role="hold"),
    MeshCondition("hop5", hops=5, per=0.005, jitter_buffer_ms=60.0, role="watch"),
    MeshCondition("relay_load", hops=1, per=0.001, jitter_buffer_ms=60.0, n_calls=3, role="watch"),
)

BITRATES: Tuple[int, ...] = (3200, 6000, 9200)


def lyra_packet_bounds(start: float, duration: float) -> Tuple[int, int]:
    """Mirror Lyra 1.3.2 ``FixedPacketLossModel`` (float32 ceil).

    ``start_packet = ceil(sample_rate * start / hop)`` and the end bound uses
    ``start + duration``. Both seconds are float32, matching decoder_main.
    """
    sr = np.float32(SAMPLE_RATE)
    hop = np.float32(HOP_SAMPLES)
    s = np.float32(start)
    d = np.float32(duration)
    start_packet = math.ceil(float(sr * s / hop))
    end_packet = math.ceil(float(sr * (s + d) / hop))
    return int(start_packet), int(end_packet)


def _burst_seconds(first: int, last_exclusive: int) -> Tuple[np.float32, np.float32]:
    """Seconds pair whose float32 ceil covers packets ``[first, last_exclusive)``."""
    if last_exclusive <= first:
        raise ValueError("empty loss burst")
    if first == 0:
        start_target = np.float32(0.0)
    else:
        start_target = np.float32(first) - np.float32(0.25)
    end_target = np.float32(last_exclusive) - np.float32(0.25)
    start = np.float32(start_target / np.float32(50.0))
    end = np.float32(end_target / np.float32(50.0))
    dur = np.float32(end - start)
    if not (start >= 0 and dur > 0):
        raise RuntimeError(f"loss burst {first}:{last_exclusive} formatted to {start}, {dur}")
    return start, dur


def loss_pattern_flag(received: Sequence[bool]) -> str:
    """Comma-separated start,duration seconds for ``--fixed_packet_loss_pattern``.

    An empty string means every frame arrived. Lyra ignores the Gilbert model
    when this flag is non-empty, so the mask is exact rather than a random draw.
    """
    parts: List[str] = []
    i = 0
    n = len(received)
    while i < n:
        if received[i]:
            i += 1
            continue
        j = i + 1
        while j < n and not received[j]:
            j += 1
        start, dur = _burst_seconds(i, j)
        parts.append(format(float(start), ".8f"))
        parts.append(format(float(dur), ".8f"))
        i = j
    return ",".join(parts)


def mask_from_pattern(n_frames: int, pattern: str) -> List[bool]:
    """Invert ``loss_pattern_flag`` with the same float32 ceil Lyra uses."""
    received = [True] * n_frames
    if not pattern:
        return received
    parts = pattern.split(",")
    if len(parts) % 2:
        raise ValueError("packet-loss pattern must be start,duration pairs")
    for k in range(0, len(parts), 2):
        start_packet, end_packet = lyra_packet_bounds(np.float32(parts[k]), np.float32(parts[k + 1]))
        for index in range(max(0, start_packet), min(n_frames, end_packet)):
            received[index] = False
    return received


def simulate(condition: MeshCondition, bitrate: int, n_frames: int = N_FRAMES) -> Tuple[List[bool], dict]:
    """Run one call (id 0) through ``condition`` and return its playout mask.

    The mask entry is True when the jitter buffer plays the frame. Call 0 is
    phase-aligned to the audio (phase 0) so frame ``i`` is simulator packet ``i``.
    Extra calls, when requested, share the path with random phases and only
    exist to load the link.
    """
    if bitrate not in BITRATES:
        raise ValueError(f"unsupported Lyra bitrate {bitrate}")
    if condition.hops < 1:
        raise ValueError("hops must be >= 1")
    codec = CodecProfile(f"lyra_v2_{bitrate}", bitrate)
    params = LinkParams(
        capacity_bps=condition.capacity_bps,
        connection_interval_ms=condition.connection_interval_ms,
        per=condition.per,
    )
    graph = line(condition.hops + 1, params)
    path = list(range(condition.hops + 1))
    # Integer-sample duration. 0.02 is not binary-exact; n/rate for 16 kHz is.
    duration_s = n_frames * HOP_SAMPLES / SAMPLE_RATE
    interval = codec.frame_seconds
    rng = random.Random(condition.seed)
    calls = [Call(0, path, codec, overhead_bytes=OVERHEAD_BYTES, phase_s=0.0)]
    for call_id in range(1, condition.n_calls):
        calls.append(Call(
            call_id, path, codec, overhead_bytes=OVERHEAD_BYTES,
            phase_s=rng.uniform(0.0, interval),
        ))
    sim = SimParams(
        duration_s=duration_s,
        encode_ms=10.0,
        decode_ms=5.0,
        jitter_buffer_ms=condition.jitter_buffer_ms,
        seed=condition.seed,
    )
    result = Simulator(graph, calls, sim).run()
    fates = [fate for fate in result.fates if fate.call_id == 0]
    if [fate.packet_index for fate in fates] != list(range(n_frames)):
        raise RuntimeError(
            f"{condition.name} @ {bitrate} produced {len(fates)} frames for call 0, expected {n_frames}"
        )
    received = [fate.outcome == "ok" for fate in fates]
    summary = per_call(result)
    call0 = next(row for row in summary if row.call_id == 0)
    meta = {
        "condition": condition.name,
        "role": condition.role,
        "bitrate": bitrate,
        "hops": condition.hops,
        "per": condition.per,
        "jitter_buffer_ms": condition.jitter_buffer_ms,
        "n_calls": condition.n_calls,
        "frames": n_frames,
        "frames_played": sum(received),
        "frames_lost": n_frames - sum(received),
        "loss_fraction": (n_frames - sum(received)) / n_frames,
        "sim_mte_p95_ms": call0.mte_p95_ms,
        "lost_random": sum(fate.outcome == "random" for fate in fates),
        "lost_congestion": sum(fate.outcome == "congestion" for fate in fates),
        "lost_late": sum(fate.outcome == "late" for fate in fates),
    }
    return received, meta


def all_masks(n_frames: int = N_FRAMES) -> Dict[str, Dict[str, str]]:
    """``{bitrate: {condition: '01..'}}`` playout masks, 1 = played."""
    table: Dict[str, Dict[str, str]] = {}
    for bitrate in BITRATES:
        per_rate: Dict[str, str] = {}
        for condition in CONDITIONS:
            received, _meta = simulate(condition, bitrate, n_frames)
            per_rate[condition.name] = "".join("1" if bit else "0" for bit in received)
        table[str(bitrate)] = per_rate
    return table


def condition_by_name(name: str) -> MeshCondition:
    for condition in CONDITIONS:
        if condition.name == name:
            return condition
    raise KeyError(name)
