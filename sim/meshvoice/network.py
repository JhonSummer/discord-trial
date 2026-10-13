"""Graph + BLE link model and topology builders.

A ``Link`` is a directed, stateful BLE server. Its parameters encode the three things that
actually bound BLE voice: effective app-layer capacity, connection-interval access latency,
and residual packet-error rate. Topologies are built as undirected graphs (two directed
links per edge) so routing and per-direction congestion are modelled honestly.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class LinkParams:
    """Effective, *already-usable* BLE link characteristics.

    ``capacity_bps`` is application-layer goodput after BLE link-layer overhead. Defaults
    are deliberately conservative (classic BLE); pass a higher capacity + shorter
    connection interval to model BLE 5 (2M PHY).
    """

    capacity_bps: float = 50_000.0
    connection_interval_ms: float = 15.0
    per: float = 0.0
    max_queue_delay_ms: float = 500.0

    def __post_init__(self) -> None:
        if self.capacity_bps <= 0:
            raise ValueError("capacity_bps must be positive")
        if self.connection_interval_ms < 0:
            raise ValueError("connection_interval_ms must be >= 0")
        if not (0.0 <= self.per < 1.0):
            raise ValueError("per must be in [0, 1)")
        if self.max_queue_delay_ms <= 0:
            raise ValueError("max_queue_delay_ms must be positive")


class Link:
    """A directed link with mutable simulation state."""

    __slots__ = ("src", "dst", "params", "free_at", "busy_time", "max_queue_delay", "admitted", "dropped_congestion")

    def __init__(self, src: int, dst: int, params: LinkParams):
        self.src = src
        self.dst = dst
        self.params = params
        self.reset()

    def reset(self) -> None:
        self.free_at: float = 0.0
        self.busy_time: float = 0.0
        self.max_queue_delay: float = 0.0
        self.admitted: int = 0
        self.dropped_congestion: int = 0

    def utilization(self, duration_s: float) -> float:
        return self.busy_time / duration_s if duration_s > 0 else 0.0

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Link({self.src}->{self.dst}, cap={self.params.capacity_bps:.0f})"


class Graph:
    def __init__(self) -> None:
        self.nodes: set[int] = set()
        self.links: Dict[Tuple[int, int], Link] = {}
        self._adj: Dict[int, List[int]] = {}

    def add_node(self, n: int) -> None:
        self.nodes.add(n)
        self._adj.setdefault(n, [])

    def add_link(self, src: int, dst: int, params: LinkParams) -> Link:
        self.add_node(src)
        self.add_node(dst)
        link = Link(src, dst, params)
        self.links[(src, dst)] = link
        if dst not in self._adj[src]:
            self._adj[src].append(dst)
        return link

    def add_edge(self, a: int, b: int, params: LinkParams) -> None:
        """Undirected edge = two directed links sharing the same params object."""
        self.add_link(a, b, params)
        self.add_link(b, a, params)

    def link(self, src: int, dst: int) -> Link:
        return self.links[(src, dst)]

    def neighbors(self, n: int) -> List[int]:
        return self._adj.get(n, [])

    def reset(self) -> None:
        for link in self.links.values():
            link.reset()

    @property
    def num_edges(self) -> int:
        return len(self.links)


def line(n: int, params: Optional[LinkParams] = None) -> Graph:
    params = params or LinkParams()
    g = Graph()
    for i in range(n):
        g.add_node(i)
    for i in range(n - 1):
        g.add_edge(i, i + 1, params)
    return g


def ring(n: int, params: Optional[LinkParams] = None) -> Graph:
    params = params or LinkParams()
    g = line(n, params)
    if n > 2:
        g.add_edge(n - 1, 0, params)
    return g


def star(n_leaves: int, params: Optional[LinkParams] = None) -> Graph:
    """Node 0 is the hub; 1..n_leaves are leaves."""
    params = params or LinkParams()
    g = Graph()
    g.add_node(0)
    for leaf in range(1, n_leaves + 1):
        g.add_edge(0, leaf, params)
    return g


def grid(rows: int, cols: int, params: Optional[LinkParams] = None) -> Graph:
    params = params or LinkParams()
    g = Graph()

    def node_id(r: int, c: int) -> int:
        return r * cols + c

    for r in range(rows):
        for c in range(cols):
            g.add_node(node_id(r, c))
    for r in range(rows):
        for c in range(cols):
            if c + 1 < cols:
                g.add_edge(node_id(r, c), node_id(r, c + 1), params)
            if r + 1 < rows:
                g.add_edge(node_id(r, c), node_id(r + 1, c), params)
    return g


def random_geometric(n: int, radius: float, params: Optional[LinkParams] = None,
                     seed: int = 0, side: float = 1.0) -> Graph:
    """``n`` nodes uniformly placed in a ``side``x``side`` square; edge if within ``radius``.

    Models a physical cluster of phones: connectivity falls out of geometry, so hop counts
    and relay fan-out reflect a realistic spatial layout rather than a hand-drawn graph.
    """
    params = params or LinkParams()
    rng = random.Random(seed)
    pts = [(rng.uniform(0, side), rng.uniform(0, side)) for _ in range(n)]
    g = Graph()
    for i in range(n):
        g.add_node(i)
    for i in range(n):
        for j in range(i + 1, n):
            dx = pts[i][0] - pts[j][0]
            dy = pts[i][1] - pts[j][1]
            if math.hypot(dx, dy) <= radius:
                g.add_edge(i, j, params)
    return g
