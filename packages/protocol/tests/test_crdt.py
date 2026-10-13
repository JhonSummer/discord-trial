import os

from messenger.protocol import LWWRegister, ORSet


def test_lww_last_write_wins():
    r = LWWRegister()
    r.set("a", ts=1, actor=b"x")
    r.set("b", ts=2, actor=b"x")
    assert r.value == "b"
    r.set("stale", ts=1, actor=b"x")
    assert r.value == "b"


def test_lww_tie_break_is_deterministic_and_convergent():
    r1, r2 = LWWRegister(), LWWRegister()
    r1.set("alice", ts=5, actor=b"\x01")
    r2.set("bob", ts=5, actor=b"\x02")
    r1.merge(r2)
    r2.merge(r1)
    assert r1.value == r2.value == "bob"  # equal timestamps -> higher actor id wins


def test_lww_merge_is_commutative_and_idempotent():
    w1, w2 = LWWRegister(), LWWRegister()
    w1.set("x", 3, b"a")
    w2.set("y", 7, b"b")
    left = LWWRegister()
    left.merge(w1)
    left.merge(w2)
    left.merge(w2)  # idempotent
    right = LWWRegister()
    right.merge(w2)
    right.merge(w1)  # commutative
    assert left.value == right.value == "y"


def test_orset_add_then_remove():
    s = ORSet()
    s.add("alice", os.urandom(8))
    assert "alice" in s
    s.remove("alice")
    assert "alice" not in s
    assert s.elements() == set()


def test_orset_is_add_wins_under_concurrency():
    s1, s2 = ORSet(), ORSet()
    t1 = os.urandom(8)
    s1.add("alice", t1)
    s2.merge(s1)        # s2 observes t1
    s2.remove("alice")  # and removes it
    s1.add("alice", os.urandom(8))  # concurrently, s1 re-adds with an unobserved tag
    s1.merge(s2)
    s2.merge(s1)
    assert ("alice" in s1) == ("alice" in s2)
    assert "alice" in s1  # the fresh add was never seen by the remove
    assert s1.elements() == s2.elements()


def test_orset_merge_converges():
    s1, s2 = ORSet(), ORSet()
    s1.add("a", os.urandom(8))
    s1.add("b", os.urandom(8))
    s2.add("c", os.urandom(8))
    s2.remove("c")
    s1.merge(s2)
    s2.merge(s1)
    assert s1.elements() == s2.elements() == {"a", "b"}
