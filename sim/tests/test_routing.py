import pytest

from meshvoice.network import Graph, LinkParams, line
from meshvoice.routing import lowest_latency_path, shortest_path


def test_shortest_path_on_line():
    g = line(6)
    assert shortest_path(g, 0, 5) == [0, 1, 2, 3, 4, 5]


def test_shortest_path_src_equals_dst():
    g = line(3)
    assert shortest_path(g, 1, 1) == [1]


def test_shortest_path_unreachable():
    g = Graph()
    g.add_node(0)
    g.add_node(1)
    assert shortest_path(g, 0, 1) is None


def test_shortest_path_hop_limit():
    g = line(6)
    assert shortest_path(g, 0, 5, hop_limit=3) is None
    assert shortest_path(g, 0, 3, hop_limit=3) == [0, 1, 2, 3]


def _diamond():
    g = Graph()
    cheap = LinkParams(capacity_bps=1_000_000, connection_interval_ms=0)
    slow = LinkParams(capacity_bps=1_000, connection_interval_ms=0)
    g.add_edge(0, 2, slow)       # 1 hop, but very slow to serialize
    g.add_edge(0, 1, cheap)
    g.add_edge(1, 2, cheap)      # 2 hops, but fast
    return g


def test_lowest_latency_prefers_fast_two_hop_over_slow_one_hop():
    g = _diamond()
    assert shortest_path(g, 0, 2) == [0, 2]            # fewest hops
    assert lowest_latency_path(g, 0, 2, packet_bits=1000) == [0, 1, 2]  # least delay


def test_lowest_latency_respects_hop_limit():
    g = _diamond()
    assert lowest_latency_path(g, 0, 2, packet_bits=1000, hop_limit=1) == [0, 2]


def test_lowest_latency_unreachable():
    g = Graph()
    g.add_node(0)
    g.add_node(9)
    assert lowest_latency_path(g, 0, 9, packet_bits=100) is None
