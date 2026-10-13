"""End-to-end: E2EE ciphertext carried over the emulated BLE mesh, opaque to every relay.

Ties the whole stack together — crypto (handshake + Double Ratchet) produces ciphertext, the
protocol wraps it in a signed envelope, and the transport floods it across multiple BLE hops. The
relays carry the bytes but cannot read them; only the addressed recipient verifies the author and
decrypts.
"""

import asyncio

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from harness import EmulatedMesh
from messenger.crypto import DoubleRatchet, IdentityKeyPair, run_handshake
from messenger.crypto.ratchet import Header
from messenger.protocol import Envelope, Snowflake, make_envelope


def _raw(priv: X25519PrivateKey) -> bytes:
    return priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _seal(ratchet: DoubleRatchet, plaintext: bytes) -> bytes:
    header, body = ratchet.encrypt(plaintext)
    return header.serialize() + body  # 40-byte header then AEAD body


def _open(ratchet: DoubleRatchet, ciphertext: bytes) -> bytes:
    return ratchet.decrypt(Header.deserialize(ciphertext[:40]), ciphertext[40:])


def test_e2ee_message_rides_the_mesh_and_only_bob_can_read_it():
    alice_id, bob_id = IdentityKeyPair.generate(), IdentityKeyPair.generate()
    ar, br = run_handshake(alice_id, bob_id)  # mutually-authenticated session keys

    bob_ratchet = X25519PrivateKey.generate()
    alice_dr = DoubleRatchet.init_alice(ar.send_key, _raw(bob_ratchet))
    bob_dr = DoubleRatchet.init_bob(br.recv_key, bob_ratchet)

    plaintext = b"meet me off-grid at 9"
    env = make_envelope(alice_id, room=b"dm:ab", prev=(), epoch=0,
                        ciphertext=_seal(alice_dr, plaintext), snowflake=Snowflake(0))
    wire_bytes = env.to_bytes()

    async def scenario():
        m = EmulatedMesh(4)  # 0=alice, 1&2=relays, 3=bob
        await m.start()
        await m.line()
        m.originate(0, wire_bytes)
        await m.settle()
        return [m.delivered(i) for i in range(4)]

    delivered = asyncio.run(scenario())

    # the relays carried the exact bytes across the mesh...
    assert delivered[1] == [wire_bytes]
    assert delivered[2] == [wire_bytes]
    # ...but the plaintext never appears on the wire, and a relay has no key to recover it
    assert plaintext not in wire_bytes
    relay_view = Envelope.from_bytes(delivered[1][0])
    with pytest.raises(Exception):
        _open(DoubleRatchet.init_bob(b"\x00" * 32, X25519PrivateKey.generate()), relay_view.ciphertext)

    # bob verifies Alice's signature and decrypts
    at_bob = Envelope.from_bytes(delivered[3][0])
    assert at_bob.verify(alice_id.public)
    assert _open(bob_dr, at_bob.ciphertext) == plaintext


def test_tampered_ciphertext_on_the_mesh_is_detected_by_recipient():
    alice_id, bob_id = IdentityKeyPair.generate(), IdentityKeyPair.generate()
    ar, br = run_handshake(alice_id, bob_id)
    bob_ratchet = X25519PrivateKey.generate()
    alice_dr = DoubleRatchet.init_alice(ar.send_key, _raw(bob_ratchet))
    bob_dr = DoubleRatchet.init_bob(br.recv_key, bob_ratchet)

    env = make_envelope(alice_id, b"dm:ab", (), 0, _seal(alice_dr, b"authentic"), Snowflake(0))

    # a malicious relay flips a bit in the ciphertext and re-signs with its own key
    mallory = IdentityKeyPair.generate()
    forged = Envelope.from_bytes(env.to_bytes())
    forged.ciphertext = bytearray(forged.ciphertext)
    forged.ciphertext[-1] ^= 0x01
    forged.ciphertext = bytes(forged.ciphertext)
    forged.sig = mallory.sign(forged.body())

    # bob rejects it as not coming from Alice (signature check fails against Alice's identity)
    assert not forged.verify(alice_id.public)
    # and even if structure is accepted, the AEAD tag fails to open
    with pytest.raises(Exception):
        _open(bob_dr, forged.ciphertext)
