from messenger.protocol import DEFAULT_TTL, Frame
from messenger.protocol.frame import MSG_ID_LEN


def test_frame_roundtrips():
    f = Frame(ttl=5, payload=b"\x00hello\xff")
    assert Frame.from_bytes(f.to_bytes()) == f


def test_msg_id_is_content_addressed_and_ttl_independent():
    a = Frame(ttl=5, payload=b"same")
    b = Frame(ttl=1, payload=b"same")  # same payload, different ttl
    c = Frame(ttl=5, payload=b"other")
    assert a.msg_id == b.msg_id  # dedup must not depend on remaining hop budget
    assert a.msg_id != c.msg_id
    assert len(a.msg_id) == MSG_ID_LEN


def test_hop_decrements_ttl_until_dead():
    f = Frame(ttl=2, payload=b"x")
    assert f.alive
    f1 = f.hop()
    assert f1.ttl == 1 and f1.alive
    f2 = f1.hop()
    assert f2.ttl == 0 and not f2.alive


def test_default_ttl_is_positive():
    assert DEFAULT_TTL > 0
