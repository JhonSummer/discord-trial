from cryptocore.identity import IdentityKeyPair
from messenger.protocol import EPOCH_MS, Envelope, Snowflake, make_envelope


def test_snowflake_is_time_ordered_and_encodes_node():
    sf = Snowflake(node_id=42)
    a = sf.next(now_ms=EPOCH_MS + 1000)
    b = sf.next(now_ms=EPOCH_MS + 2000)
    assert b > a
    assert (a >> 12) & 0x3FF == 42
    assert Snowflake.timestamp_ms(a) == EPOCH_MS + 1000


def test_snowflake_sequence_distinct_within_same_ms():
    sf = Snowflake(1)
    ids = [sf.next(now_ms=EPOCH_MS + 5) for _ in range(5)]
    assert ids == sorted(ids)
    assert len(set(ids)) == 5


def test_snowflake_monotonic_even_if_clock_goes_backwards():
    sf = Snowflake(1)
    first = sf.next(now_ms=EPOCH_MS + 100)
    later = [sf.next(now_ms=EPOCH_MS + 50) for _ in range(3)]
    assert later == sorted(later)
    assert later[0] > first


def test_envelope_roundtrips():
    alice = IdentityKeyPair.generate()
    env = make_envelope(alice, room=b"general", prev=(123, 456), epoch=4,
                        ciphertext=b"\x00opaque\xff", snowflake=Snowflake(7))
    assert Envelope.from_bytes(env.to_bytes()) == env


def test_body_is_deterministic():
    e1 = Envelope(eid=1, room=b"r", sender=b"\x00" * 32, prev=(2, 3), epoch=1, ciphertext=b"x")
    e2 = Envelope(eid=1, room=b"r", sender=b"\x00" * 32, prev=(2, 3), epoch=1, ciphertext=b"x")
    assert e1.body() == e2.body()


def test_signature_verifies_for_author():
    alice = IdentityKeyPair.generate()
    env = make_envelope(alice, b"room", (), 0, b"ct", Snowflake(1))
    assert env.verify(alice.public)


def test_signature_rejects_wrong_author():
    alice = IdentityKeyPair.generate()
    mallory = IdentityKeyPair.generate()
    env = make_envelope(alice, b"room", (), 0, b"ct", Snowflake(1))
    assert not env.verify(mallory.public)


def test_signature_rejects_tampered_ciphertext():
    alice = IdentityKeyPair.generate()
    env = make_envelope(alice, b"room", (), 0, b"ct", Snowflake(1))
    env.ciphertext = b"CT"  # modified after signing
    assert not env.verify(alice.public)
