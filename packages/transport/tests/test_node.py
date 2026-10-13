from messenger.crypto.identity import IdentityKeyPair
from messenger.transport import MeshNode


def wire(a: MeshNode, b: MeshNode) -> None:
    a.router.connect(b.router.node_id, lambda d: b.router.on_frame(d, from_id=a.router.node_id))
    b.router.connect(a.router.node_id, lambda d: a.router.on_frame(d, from_id=b.router.node_id))


def test_post_floods_into_neighbor_dag():
    a = MeshNode(IdentityKeyPair.generate(), 1)
    b = MeshNode(IdentityKeyPair.generate(), 2)
    wire(a, b)
    env = a.post(b"room", b"ciphertext")
    assert env.eid in b.dag
    assert b.dag.events[env.eid].ciphertext == b"ciphertext"


def test_posts_chain_via_prev_heads():
    a = MeshNode(IdentityKeyPair.generate(), 1)
    e1 = a.post(b"r", b"m1")
    e2 = a.post(b"r", b"m2")
    assert e2.prev == (e1.eid,)  # each post builds on the current frontier


def test_recipient_verifies_known_author():
    a = MeshNode(IdentityKeyPair.generate(), 1)
    b = MeshNode(IdentityKeyPair.generate(), 2)
    wire(a, b)
    env = a.post(b"r", b"ct")
    assert b.dag.events[env.eid].verify(a.identity.public)  # b holds a's public identity (contact)


def test_anti_entropy_converges_after_partition():
    a = MeshNode(IdentityKeyPair.generate(), 1)
    b = MeshNode(IdentityKeyPair.generate(), 2)
    # partitioned (never wired): neither flood reaches the other
    a.post(b"r", b"a1")
    a.post(b"r", b"a2")
    b.post(b"r", b"b1")
    assert a.dag.ids() != b.dag.ids()
    a.sync_with(b)
    assert a.dag.ids() == b.dag.ids()
    assert [e.eid for e in a.dag.causal_order()] == [e.eid for e in b.dag.causal_order()]
