from messenger.crypto.identity import IdentityKeyPair
from messenger.protocol import EventDAG, Snowflake, make_envelope


def _chain(author, sf, room, n, start_prev=()):
    envs, prev = [], start_prev
    for _ in range(n):
        e = make_envelope(author, room, prev, 0, b"m", sf)
        envs.append(e)
        prev = (e.eid,)
    return envs


def test_add_is_idempotent():
    dag = EventDAG()
    e = make_envelope(IdentityKeyPair.generate(), b"r", (), 0, b"m", Snowflake(1))
    assert dag.add(e) is True
    assert dag.add(e) is False
    assert len(dag) == 1


def test_causal_order_respects_parents_not_insertion_order():
    chain = _chain(IdentityKeyPair.generate(), Snowflake(1), b"r", 5)
    dag = EventDAG()
    for e in reversed(chain):  # insert children before parents
        dag.add(e)
    assert [e.eid for e in dag.causal_order()] == [e.eid for e in chain]


def test_heads_are_the_frontier():
    chain = _chain(IdentityKeyPair.generate(), Snowflake(1), b"r", 3)
    dag = EventDAG()
    dag.merge(chain)
    assert dag.heads() == [chain[-1].eid]


def test_anti_entropy_reconciles_two_diverged_islands():
    a, b = IdentityKeyPair.generate(), IdentityKeyPair.generate()
    sfa, sfb = Snowflake(1), Snowflake(2)
    base = make_envelope(a, b"r", (), 0, b"base", sfa)

    da, db = EventDAG(), EventDAG()
    da.add(base)
    db.add(base)
    for e in _chain(a, sfa, b"r", 2, start_prev=(base.eid,)):  # A's offline island
        da.add(e)
    for e in _chain(b, sfb, b"r", 3, start_prev=(base.eid,)):  # B's offline island
        db.add(e)
    assert da.ids() != db.ids()

    # exchange exactly the missing events in both directions
    da.merge(db.missing_for(da.ids()))
    db.merge(da.missing_for(db.ids()))

    assert da.ids() == db.ids()
    assert len(da) == 6  # base + 2 + 3
    assert [e.eid for e in da.causal_order()] == [e.eid for e in db.causal_order()]


def test_missing_for_returns_causal_order():
    a = IdentityKeyPair.generate()
    sf = Snowflake(1)
    chain = _chain(a, sf, b"r", 4)
    dag = EventDAG()
    dag.merge(chain)
    missing = dag.missing_for(set())  # peer has nothing
    # a child never precedes its parent
    positions = {e.eid: i for i, e in enumerate(missing)}
    for e in chain:
        for p in e.prev:
            assert positions[p] < positions[e.eid]
