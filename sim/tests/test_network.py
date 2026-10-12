import pytest

from meshvoice.network import (
    Graph, LinkParams, grid, line, random_geometric, ring, star,
)


def test_line_structure():
    g = line(5)
    assert len(g.nodes) == 5
    assert g.num_edges == 2 * 4  # directed, both ways
    assert g.neighbors(0) == [1]
    assert sorted(g.neighbors(2)) == [1, 3]


def test_ring_structure():
    g = ring(5)
    assert g.num_edges == 2 * 5
    assert set(g.neighbors(0)) == {1, 4}


def test_star_structure():
    g = star(6)
    assert len(g.nodes) == 7
    assert g.num_edges == 2 * 6
    assert sorted(g.neighbors(0)) == [1, 2, 3, 4, 5, 6]
    assert g.neighbors(3) == [0]


def test_grid_structure():
    rows, cols = 3, 4
    g = grid(rows, cols)
    assert len(g.nodes) == rows * cols
    expected_edges = rows * (cols - 1) + cols * (rows - 1)
    assert g.num_edges == 2 * expected_edges


def test_random_geometric_is_deterministic():
    g1 = random_geometric(20, 0.3, seed=42)
    g2 = random_geometric(20, 0.3, seed=42)
    assert set(g1.links.keys()) == set(g2.links.keys())


def test_random_geometric_radius_extremes():
    full = random_geometric(8, radius=10.0, seed=1)  # everyone in range
    assert full.num_edges == 8 * 7
    empty = random_geometric(8, radius=0.0, seed=1)
    assert empty.num_edges == 0


def test_linkparams_validation():
    with pytest.raises(ValueError):
        LinkParams(capacity_bps=0)
    with pytest.raises(ValueError):
        LinkParams(per=1.0)
    with pytest.raises(ValueError):
        LinkParams(connection_interval_ms=-1)
    with pytest.raises(ValueError):
        LinkParams(max_queue_delay_ms=0)


def test_link_utilization_and_reset():
    g = line(2)
    link = g.link(0, 1)
    link.busy_time = 4.0
    assert link.utilization(8.0) == pytest.approx(0.5)
    g.reset()
    assert link.busy_time == 0.0
    assert link.free_at == 0.0


def test_shared_params_object_across_edge_directions():
    p = LinkParams(capacity_bps=12345)
    g = Graph()
    g.add_edge(0, 1, p)
    assert g.link(0, 1).params is g.link(1, 0).params
