import os

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from messenger.crypto.ratchet import MAX_SKIP, DoubleRatchet, Header, RatchetError


def _session():
    """A fresh pair sharing a root key, as the Noise handshake would hand off."""
    root = os.urandom(32)
    bob_priv = X25519PrivateKey.generate()
    bob_pub = bob_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    alice = DoubleRatchet.init_alice(root, bob_pub)
    bob = DoubleRatchet.init_bob(root, bob_priv)
    return alice, bob


def test_basic_back_and_forth():
    alice, bob = _session()
    h, body = alice.encrypt(b"hello bob")
    assert bob.decrypt(h, body) == b"hello bob"
    h, body = bob.encrypt(b"hi alice")
    assert alice.decrypt(h, body) == b"hi alice"


def test_long_interleaved_conversation():
    alice, bob = _session()

    def a2b(m):
        assert bob.decrypt(*alice.encrypt(m)) == m

    def b2a(m):
        assert alice.decrypt(*bob.encrypt(m)) == m

    a2b(b"1")
    a2b(b"2")
    b2a(b"3")
    b2a(b"4")
    a2b(b"5")
    b2a(b"6")
    a2b(b"7")


def test_out_of_order_within_a_chain():
    alice, bob = _session()
    msgs = [alice.encrypt(f"m{i}".encode()) for i in range(6)]
    for i in (0, 3, 1, 5, 2, 4):  # jumbled arrival order
        assert bob.decrypt(*msgs[i]) == f"m{i}".encode()


def test_skipped_messages_across_a_dh_step():
    alice, bob = _session()
    a0 = alice.encrypt(b"a0")
    a1 = alice.encrypt(b"a1")
    assert bob.decrypt(*a0) == b"a0"  # bob establishes a receive chain
    reply = bob.encrypt(b"b0")  # bob ratchets to a new sending key
    assert alice.decrypt(*reply) == b"b0"
    a2 = alice.encrypt(b"a2")  # alice ratchets again after hearing bob
    assert bob.decrypt(*a2) == b"a2"
    assert bob.decrypt(*a1) == b"a1"  # the straggler from the earlier chain still opens


def test_associated_data_roundtrip():
    alice, bob = _session()
    h, body = alice.encrypt(b"payload", b"room-42")
    assert bob.decrypt(h, body, b"room-42") == b"payload"


def test_wrong_associated_data_rejected():
    alice, bob = _session()
    h, body = alice.encrypt(b"payload", b"room-42")
    with pytest.raises(Exception):
        bob.decrypt(h, body, b"room-99")


def test_tampered_ciphertext_rejected():
    alice, bob = _session()
    h, body = alice.encrypt(b"secret")
    tampered = bytearray(body)
    tampered[-1] ^= 0x01
    with pytest.raises(Exception):
        bob.decrypt(h, bytes(tampered))


def test_bob_cannot_send_before_receiving():
    alice, bob = _session()
    with pytest.raises(RatchetError):
        bob.encrypt(b"too early")


def test_too_many_skips_is_bounded():
    alice, bob = _session()
    last = None
    for _ in range(MAX_SKIP + 2):
        last = alice.encrypt(b"x")
    with pytest.raises(RatchetError):
        bob.decrypt(*last)


def test_header_serialize_roundtrip():
    alice, _ = _session()
    h, _body = alice.encrypt(b"x")
    again = Header.deserialize(h.serialize())
    assert (again.dh, again.pn, again.n) == (h.dh, h.pn, h.n)


def test_message_keys_differ_per_message():
    alice, bob = _session()
    _, b0 = alice.encrypt(b"same")
    _, b1 = alice.encrypt(b"same")
    assert b0 != b1  # forward secrecy: identical plaintext, distinct keystreams
