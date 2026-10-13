"""Scenario builders, breaking-point search, and the concurrent-call sweep.

Scenarios are deliberately small and legible so results are explainable: a single shared
relay link (the cleanest stress test and the analytic cross-check), a line for per-hop
latency growth, and a random-geometric cluster for a realistic spatial layout. The
breaking point is the largest number of concurrent calls that still meets the QoS target.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from .codec import CodecProfile, LYRA_V2_3200, LYRA_V2_6000, LYRA_V2_9200
from .metrics import AggregateSummary, summarize
from .network import Graph, LinkParams, line, random_geometric
from .routing import lowest_latency_path, shortest_path
from .simulator import Call, SimParams, Simulator


@dataclass
class QoS:
    """Interactive-voice acceptance target."""
    max_p95_ms: float = 200.0
    max_loss: float = 0.02


def make_calls(paths: List[List[int]], codec: CodecProfile, frames_per_packet: int = 1,
               overhead_bytes: float = 0.0, seed: int = 0) -> List[Call]:
    """One ``Call`` per path, each with a random phase so streams are not artificially
    synchronized on connection-interval boundaries."""
    rng = random.Random(seed)
    interval = frames_per_packet * codec.frame_seconds
    calls = []
    for i, path in enumerate(paths):
        calls.append(Call(i, path, codec, frames_per_packet, overhead_bytes,
                          start_s=0.0, phase_s=rng.uniform(0.0, interval)))
    return calls


def call_bitrate_bps(codec: CodecProfile, frames_per_packet: int = 1, overhead_bytes: float = 0.0) -> float:
    interval = frames_per_packet * codec.frame_seconds
    return codec.packet_bits(frames_per_packet, overhead_bytes) / interval


def analytic_capacity(codec: CodecProfile, params: LinkParams, frames_per_packet: int = 1,
                      overhead_bytes: float = 0.0) -> float:
    """How many on-wire streams fit a single link, ignoring queueing/latency (upper bound)."""
    return params.capacity_bps / call_bitrate_bps(codec, frames_per_packet, overhead_bytes)


def shared_relay(n: int, codec: CodecProfile, params: LinkParams, frames_per_packet: int = 1,
                 overhead_bytes: float = 0.0, seed: int = 0) -> Tuple[Graph, List[Call]]:
    """``n`` calls all crossing one directed relay link 0->1 — the capacity bottleneck."""
    g = Graph()
    g.add_link(0, 1, params)
    paths = [[0, 1] for _ in range(n)]
    return g, make_calls(paths, codec, frames_per_packet, overhead_bytes, seed)


def line_result(hops: int, codec: CodecProfile, params: LinkParams, sim_params: SimParams,
                frames_per_packet: int = 1, overhead_bytes: float = 0.0, seed: int = 0) -> AggregateSummary:
    """A single call over ``hops`` BLE hops; isolates per-hop latency accumulation."""
    g = line(hops + 1, params)
    calls = make_calls([list(range(hops + 1))], codec, frames_per_packet, overhead_bytes, seed)
    return summarize(Simulator(g, calls, sim_params).run())


def breaking_point(build_fn: Callable[[int], Tuple[Graph, List[Call]]], qos: QoS,
                   sim_params: SimParams, n_max: int = 128) -> int:
    """Largest ``n`` for which the built scenario meets the QoS target."""
    best = 0
    for n in range(1, n_max + 1):
        g, calls = build_fn(n)
        agg = summarize(Simulator(g, calls, sim_params).run())
        if agg.meets(qos.max_p95_ms, qos.max_loss):
            best = n
        else:
            break
    return best


def adaptive_codec_for(n: int, params: LinkParams,
                       ladder: Tuple[CodecProfile, ...] = (LYRA_V2_9200, LYRA_V2_6000, LYRA_V2_3200),
                       frames_per_packet: int = 1, overhead_bytes: float = 0.0,
                       target_util: float = 0.95) -> CodecProfile:
    """Pick the highest-quality rate whose aggregate load stays under ``target_util`` — the
    adaptive-bitrate lever that lets a loaded relay downshift to keep calls alive."""
    for codec in ladder:
        if n * call_bitrate_bps(codec, frames_per_packet, overhead_bytes) <= target_util * params.capacity_bps:
            return codec
    return ladder[-1]


def adaptive_shared_relay(n: int, params: LinkParams, frames_per_packet: int = 1,
                          overhead_bytes: float = 0.0, seed: int = 0) -> Tuple[Graph, List[Call]]:
    codec = adaptive_codec_for(n, params, frames_per_packet=frames_per_packet, overhead_bytes=overhead_bytes)
    return shared_relay(n, codec, params, frames_per_packet, overhead_bytes, seed)


def random_pairs_paths(g: Graph, n_calls: int, packet_bits: int, routing: str = "latency",
                       hop_limit: Optional[int] = None, seed: int = 0) -> List[List[int]]:
    """Route ``n_calls`` random reachable source/destination pairs on a fixed graph."""
    rng = random.Random(seed)
    nodes = sorted(g.nodes)
    paths: List[List[int]] = []
    attempts = 0
    while len(paths) < n_calls and attempts < n_calls * 100 + 100:
        a, b = rng.sample(nodes, 2)
        if routing == "latency":
            path = lowest_latency_path(g, a, b, packet_bits, hop_limit)
        else:
            path = shortest_path(g, a, b, hop_limit)
        if path and len(path) >= 2:
            paths.append(path)
        attempts += 1
    return paths


def geometric_scenario(n_nodes: int, radius: float, n_calls: int, codec: CodecProfile,
                       params: LinkParams, sim_params: SimParams, routing: str = "latency",
                       frames_per_packet: int = 1, overhead_bytes: float = 0.0,
                       hop_limit: Optional[int] = None, side: float = 1.0,
                       seed: int = 0) -> Tuple[Graph, List[Call], AggregateSummary]:
    g = random_geometric(n_nodes, radius, params, seed=seed, side=side)
    pb = codec.packet_bits(frames_per_packet, overhead_bytes)
    paths = random_pairs_paths(g, n_calls, pb, routing, hop_limit, seed + 1)
    calls = make_calls(paths, codec, frames_per_packet, overhead_bytes, seed + 2)
    return g, calls, summarize(Simulator(g, calls, sim_params).run())
