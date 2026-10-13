"""Double Ratchet: ordered + out-of-order delivery, skipping bounds, and tamper rejection."""

import os

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from cryptocore import DoubleRatchet, Header, RatchetError


def _session():
    """A fresh Alice/Bob ratchet pair sharing a root key, with Bob holding a 'prekey'."""
    root = os.urandom(32)
    bob_prekey = X25519PrivateKey.generate()
    bob_pub = bob_prekey.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    alice = DoubleRatchet.init_alice(root, bob_pub)
    bob = DoubleRatchet.init_bob(root, bob_prekey)
    return alice, bob


def test_single_message_roundtrip():
    alice, bob = _session()
    header, body = alice.encrypt(b"hello bob")
    assert bob.decrypt(header, body) == b"hello bob"


def test_back_and_forth_conversation():
    alice, bob = _session()
    for i in range(5):
        h, b = alice.encrypt(f"a{i}".encode())
        assert bob.decrypt(h, b) == f"a{i}".encode()
        h, b = bob.encrypt(f"b{i}".encode())
        assert alice.decrypt(h, b) == f"b{i}".encode()


def test_bob_cannot_send_before_receiving():
    _, bob = _session()
    with pytest.raises(RatchetError):
        bob.encrypt(b"too early")


def test_out_of_order_delivery():
    alice, bob = _session()
    m1 = alice.encrypt(b"one")
    m2 = alice.encrypt(b"two")
    m3 = alice.encrypt(b"three")
    # Delivered 3, 1, 2 — the ratchet stashes skipped message keys.
    assert bob.decrypt(*m3) == b"three"
    assert bob.decrypt(*m1) == b"one"
    assert bob.decrypt(*m2) == b"two"


def test_tampered_ciphertext_is_rejected():
    alice, bob = _session()
    header, body = alice.encrypt(b"authentic")
    tampered = bytearray(body)
    tampered[-1] ^= 0x01
    with pytest.raises(Exception):     # AEAD authentication failure
        bob.decrypt(header, bytes(tampered))


def test_header_is_authenticated_as_associated_data():
    alice, bob = _session()
    header, body = alice.encrypt(b"bind the header")
    forged = Header(header.dh, header.pn, header.n + 1)   # lie about the message number
    with pytest.raises(Exception):
        bob.decrypt(forged, body)


def test_too_many_skipped_messages_is_bounded():
    alice, bob = _session()
    first = alice.encrypt(b"first")
    bob.decrypt(*first)
    # Fabricate a header far beyond MAX_SKIP ahead; the ratchet refuses to skip that far.
    runaway = Header(alice.ratchet_public, 0, 10_000)
    with pytest.raises(RatchetError):
        bob.decrypt(runaway, b"\x00" * 28)
