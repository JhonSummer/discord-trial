"""Discrete-event tandem-queue simulator.

Each voice packet traverses a fixed path hop by hop. Every directed link is a FIFO server:
a packet waits for the link to be free, then for the next connection-interval boundary, then
occupies the link for its serialization time. Packets are lost to (a) residual per-link
error, (b) buffer overflow when a link is saturated, or (c) arriving after their jitter-buffer
playout deadline. Processing events in global time order makes per-link FIFO queueing exact,
and a seeded RNG with a monotonic tie-breaker makes every run reproducible.

Latency convention (mouth-to-ear), all additive and configurable:

    packet_interval  (frame/packet build-up)
  + encode
  + network delay   (sum of per-hop queue + connection-interval + serialization)
  + decode
"""

from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .codec import CodecProfile
from .network import Graph, Link


@dataclass
class Call:
    call_id: int
    path: List[int]
    codec: CodecProfile
    frames_per_packet: int = 1
    overhead_bytes: float = 0.0
    start_s: float = 0.0
    phase_s: float = 0.0

    def __post_init__(self) -> None:
        if len(self.path) < 2:
            raise ValueError("a call path needs at least a source and a destination")
        if len(set(zip(self.path, self.path[1:]))) != len(self.path) - 1:
            # allow revisiting nodes but not immediately repeating an edge
            pass

    @property
    def packet_interval_s(self) -> float:
        return self.frames_per_packet * self.codec.frame_seconds

    @property
    def packet_bits(self) -> int:
        return self.codec.packet_bits(self.frames_per_packet, self.overhead_bytes)


@dataclass
class SimParams:
    duration_s: float = 10.0
    encode_ms: float = 10.0
    decode_ms: float = 5.0
    relay_processing_ms: float = 0.0
    jitter_buffer_ms: float = 60.0
    seed: int = 0
    trace: bool = False  # record a per-packet delivery trace per call (for the voice harness)


@dataclass
class CallTrace:
    """Per-packet delivery record for one call, ordered by packet index.

    This is the bridge to the voice-quality harness: ``voiceq.channel.from_sim_delays`` turns
    these arrays into a ``DeliveryTrace`` so real speech can be scored over the *exact* loss/delay
    pattern the simulator produced for a call (``send_s[k]`` nominal capture time, ``delay_s[k]``
    network delay — NaN if the packet never arrived — and ``lost[k]`` true for drop- or late-loss).
    """

    send_s: List[float]
    delay_s: List[float]
    lost: List[bool]


@dataclass
class _PacketRecord:
    call_id: int
    packet_index: int
    delivered: bool = False
    loss_reason: Optional[str] = None  # "random" | "congestion"
    network_delay_s: float = 0.0
    hops: int = 0


@dataclass
class DeliveredPacket:
    call_id: int
    network_delay_s: float
    late: bool
    mouth_to_ear_s: float  # valid only when not late


@dataclass(frozen=True)
class PacketFate:
    """What happened to one generated voice frame.

    ``outcome`` is ``ok`` (played out of the jitter buffer), ``random`` (residual
    per-link error), ``congestion`` (buffer overflow), or ``late`` (missed the
    playout deadline). One fate is recorded per generated packet.
    """

    call_id: int
    packet_index: int
    outcome: str


@dataclass
class SimResult:
    params: SimParams
    calls: List[Call]
    delivered: List[DeliveredPacket]
    lost_random: int
    lost_congestion: int
    lost_late: int
    generated: int
    link_utilization: Dict[Tuple[int, int], float]
    link_max_queue_ms: Dict[Tuple[int, int], float]
    fates: List[PacketFate] = field(default_factory=list)
    packet_trace: Optional[Dict[int, CallTrace]] = None  # call_id -> trace, only when SimParams.trace

    @property
    def total_lost(self) -> int:
        return self.lost_random + self.lost_congestion + self.lost_late


class Simulator:
    def __init__(self, graph: Graph, calls: List[Call], params: Optional[SimParams] = None):
        self.graph = graph
        self.calls = calls
        self.params = params or SimParams()
        self._validate()

    def _validate(self) -> None:
        for call in self.calls:
            for a, b in zip(call.path, call.path[1:]):
                if (a, b) not in self.graph.links:
                    raise ValueError(f"call {call.call_id} uses missing link {a}->{b}")

    def run(self) -> SimResult:
        p = self.params
        self.graph.reset()
        rng = random.Random(p.seed)
        encode_s = p.encode_ms / 1000.0
        decode_s = p.decode_ms / 1000.0
        relay_s = p.relay_processing_ms / 1000.0

        # Event = (time, seq, call_index, packet_index, hop_index, send_ready_time)
        heap: List[Tuple[float, int, int, int, int, float]] = []
        seq = 0
        generated = 0
        gen_per_call: Dict[int, int] = {}
        for ci, call in enumerate(self.calls):
            interval = call.packet_interval_s
            # first full packet is captured over [start, start+interval], ready after encode
            k = 0
            capture = call.start_s + call.phase_s
            while capture + interval <= p.duration_s + 1e-9:
                send_ready = capture + interval + encode_s
                heapq.heappush(heap, (send_ready, seq, ci, k, 0, send_ready))
                seq += 1
                generated += 1
                k += 1
                capture = call.start_s + call.phase_s + k * interval
            gen_per_call[ci] = k

        # Per-packet outcome keyed by (call_index, packet_index), only when tracing is requested.
        traced: Optional[Dict[Tuple[int, int], Tuple[str, float]]] = {} if p.trace else None
        delivered_raw: List[_PacketRecord] = []
        fates: List[PacketFate] = []
        lost_random = 0
        lost_congestion = 0

        while heap:
            t, _, ci, k, hop, send_ready = heapq.heappop(heap)
            call = self.calls[ci]
            src = call.path[hop]
            dst = call.path[hop + 1]
            link = self.graph.link(src, dst)
            lp = link.params

            # Connection-interval access: a packet can first be radioed at the next
            # connection event. Once the radio is active, many packets ride back-to-back
            # within/across events, so throughput is bounded by airtime (service), not by
            # one-packet-per-interval.
            ci_s = lp.connection_interval_ms / 1000.0
            effective_arrival = math.ceil(t / ci_s - 1e-12) * ci_s if ci_s > 0 else t

            queue_wait = max(0.0, link.free_at - effective_arrival)
            if queue_wait > lp.max_queue_delay_ms / 1000.0:
                link.dropped_congestion += 1
                lost_congestion += 1
                fates.append(PacketFate(call.call_id, k, "congestion"))
                if traced is not None:
                    traced[(ci, k)] = ("congestion", float("nan"))
                continue

            service = call.packet_bits / lp.capacity_bps
            server_start = max(link.free_at, effective_arrival)
            depart = server_start + service

            link.free_at = depart
            link.busy_time += service
            link.admitted += 1
            if queue_wait > link.max_queue_delay:
                link.max_queue_delay = queue_wait

            if rng.random() < lp.per:
                lost_random += 1
                fates.append(PacketFate(call.call_id, k, "random"))
                if traced is not None:
                    traced[(ci, k)] = ("random", float("nan"))
                continue

            is_last = hop + 1 == len(call.path) - 1
            if is_last:
                delivered_raw.append(_PacketRecord(
                    call_id=call.call_id, packet_index=k, delivered=True,
                    network_delay_s=depart - send_ready, hops=len(call.path) - 1))
                if traced is not None:
                    traced[(ci, k)] = ("delivered", depart - send_ready)
            else:
                seq += 1
                heapq.heappush(heap, (depart + relay_s, seq, ci, k, hop + 1, send_ready))

        return self._finalize(delivered_raw, lost_random, lost_congestion, generated,
                              encode_s, decode_s, fates, traced, gen_per_call)

    def _finalize(self, delivered_raw, lost_random, lost_congestion, generated,
                  encode_s, decode_s, fates: List[PacketFate], traced=None,
                  gen_per_call=None) -> SimResult:
        p = self.params
        jb_s = p.jitter_buffer_ms / 1000.0

        # Jitter buffer anchors on each call's minimum observed network delay; packets whose
        # delay exceeds anchor + buffer depth arrive after playout and count as lost.
        anchor: Dict[int, float] = {}
        for rec in delivered_raw:
            d = rec.network_delay_s
            if rec.call_id not in anchor or d < anchor[rec.call_id]:
                anchor[rec.call_id] = d

        delivered: List[DeliveredPacket] = []
        lost_late = 0
        for rec in delivered_raw:
            call = self._call_by_id(rec.call_id)
            budget = anchor[rec.call_id] + jb_s
            late = rec.network_delay_s > budget + 1e-12
            if late:
                lost_late += 1
                fates.append(PacketFate(rec.call_id, rec.packet_index, "late"))
                delivered.append(DeliveredPacket(rec.call_id, rec.network_delay_s, True, float("nan")))
            else:
                mte = call.packet_interval_s + encode_s + rec.network_delay_s + decode_s
                fates.append(PacketFate(rec.call_id, rec.packet_index, "ok"))
                delivered.append(DeliveredPacket(rec.call_id, rec.network_delay_s, False, mte))
        fates.sort(key=lambda fate: (fate.call_id, fate.packet_index))

        util = {k: v.utilization(p.duration_s) for k, v in self.graph.links.items()}
        maxq = {k: v.max_queue_delay * 1000.0 for k, v in self.graph.links.items()}

        # The trace carries *raw network* delivery (random/congestion drops + the real network
        # delay of every packet that arrived). Late-loss is deliberately left out so the voice
        # harness's own jitter buffer decides it from the delays — the same split as run_pipeline.
        packet_trace: Optional[Dict[int, CallTrace]] = None
        if traced is not None:
            packet_trace = {}
            for ci, call in enumerate(self.calls):
                interval = call.packet_interval_s
                n_k = (gen_per_call or {}).get(ci, 0)
                send_s, delay_s, lost = [], [], []
                for k in range(n_k):
                    status, d = traced.get((ci, k), ("random", float("nan")))
                    is_lost = status != "delivered"
                    send_s.append(k * interval)
                    delay_s.append(d)
                    lost.append(is_lost)
                packet_trace[call.call_id] = CallTrace(send_s=send_s, delay_s=delay_s, lost=lost)

        return SimResult(
            params=p, calls=self.calls, delivered=delivered,
            lost_random=lost_random, lost_congestion=lost_congestion, lost_late=lost_late,
            generated=generated, link_utilization=util, link_max_queue_ms=maxq,
            fates=fates, packet_trace=packet_trace)

    def _call_by_id(self, call_id: int) -> Call:
        for c in self.calls:
            if c.call_id == call_id:
                return c
        raise KeyError(call_id)  # pragma: no cover
