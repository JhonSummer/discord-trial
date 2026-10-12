"""Path selection over the mesh graph.

Two policies matter for voice: fewest hops (minimise accumulated per-hop latency) and
lowest expected latency (hop count weighted by each link's service + connection-interval
cost). A ``hop_limit`` lets the caller express "past this many BLE hops, spill to WebRTC".
"""

from __future__ import annotations

import heapq
from collections import deque
from typing import List, Optional

from .network import Graph


def shortest_path(g: Graph, src: int, dst: int, hop_limit: Optional[int] = None) -> Optional[List[int]]:
    """Fewest-hop path via BFS. Returns ``None`` if unreachable or beyond ``hop_limit``."""
    if src == dst:
        return [src]
    prev = {src: src}
    q = deque([src])
    while q:
        node = q.popleft()
        for nxt in g.neighbors(node):
            if nxt not in prev:
                prev[nxt] = node
                if nxt == dst:
                    path = _reconstruct(prev, src, dst)
                    if hop_limit is not None and len(path) - 1 > hop_limit:
                        return None
                    return path
                q.append(nxt)
    return None


def lowest_latency_path(g: Graph, src: int, dst: int, packet_bits: int,
                        hop_limit: Optional[int] = None) -> Optional[List[int]]:
    """Dijkstra over expected per-hop delay (serialization + half a connection interval)."""
    if src == dst:
        return [src]
    dist = {src: 0.0}
    hops = {src: 0}
    prev = {src: src}
    pq: list[tuple[float, int]] = [(0.0, src)]
    while pq:
        d, node = heapq.heappop(pq)
        if d > dist.get(node, float("inf")):
            continue
        if node == dst:
            break
        for nxt in g.neighbors(node):
            link = g.link(node, nxt)
            p = link.params
            serialize = packet_bits / p.capacity_bps
            access = (p.connection_interval_ms / 1000.0) / 2.0
            w = serialize + access
            nd = d + w
            nh = hops[node] + 1
            if hop_limit is not None and nh > hop_limit:
                continue
            if nd < dist.get(nxt, float("inf")):
                dist[nxt] = nd
                hops[nxt] = nh
                prev[nxt] = node
                heapq.heappush(pq, (nd, nxt))
    if dst not in prev:
        return None
    path = _reconstruct(prev, src, dst)
    if hop_limit is not None and len(path) - 1 > hop_limit:
        return None
    return path


def _reconstruct(prev: dict, src: int, dst: int) -> List[int]:
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    path.reverse()
    return path
