from messenger.transport import MeshRouter


def wire(a: MeshRouter, b: MeshRouter) -> None:
    a.connect(b.node_id, lambda data: b.on_frame(data, from_id=a.node_id))
    b.connect(a.node_id, lambda data: a.on_frame(data, from_id=b.node_id))


def chain(*routers: MeshRouter) -> None:
    for x, y in zip(routers, routers[1:]):
        wire(x, y)


def test_line_multi_hop_delivery():
    a, b, c, d = (MeshRouter(n) for n in "ABCD")
    chain(a, b, c, d)
    a.originate(b"ping")
    for r in (b, c, d):
        assert r.delivered == [b"ping"]
    assert a.delivered == []  # originator does not self-deliver


def test_star_fanout():
    hub = MeshRouter("H")
    leaves = [MeshRouter(f"L{i}") for i in range(4)]
    for leaf in leaves:
        wire(hub, leaf)
    leaves[0].originate(b"hello")
    assert hub.delivered == [b"hello"]
    for leaf in leaves[1:]:
        assert leaf.delivered == [b"hello"]
    assert leaves[0].delivered == []


def test_cyclic_graph_delivers_exactly_once():
    a, b, c = (MeshRouter(n) for n in "ABC")
    wire(a, b)
    wire(b, c)
    wire(c, a)  # triangle: a frame can arrive by two paths
    a.originate(b"once")
    assert b.delivered == [b"once"]
    assert c.delivered == [b"once"]  # dedup kept it to a single delivery despite the loop


def test_ttl_limits_reach():
    a, b, c, d = (MeshRouter(n, ttl=2) for n in "ABCD")
    chain(a, b, c, d)
    a.originate(b"short")
    assert b.delivered == [b"short"]  # 1 hop
    assert c.delivered == [b"short"]  # 2 hops
    assert d.delivered == []          # 3 hops: beyond the TTL budget


def test_store_and_forward_after_reconnect():
    a, b = MeshRouter("A"), MeshRouter("B")
    wire(a, b)
    a.set_online("B", False)  # link to B is down
    a.originate(b"later")
    assert b.delivered == []   # queued, not lost
    a.set_online("B", True)    # B comes back
    assert b.delivered == [b"later"]


def test_dedup_cache_is_bounded():
    r = MeshRouter("R", seen_cap=4)
    for i in range(10):
        r._remember(bytes([i]))
    assert len(r._seen) == 4  # LRU eviction keeps memory bounded on long-lived nodes
