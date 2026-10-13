"""The Phase 1 deliverable, end to end.

Two simulated devices become friends over the Noise handshake, verify their safety number,
and then exchange end-to-end-encrypted messages — 1:1 (Double Ratchet) and group (MLS) —
through an untrusted store-and-forward relay that only ever handles opaque ciphertext.
"""

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from cryptocore import (
    DoubleRatchet,
    Group,
    GroupError,
    Header,
    IdentityKeyPair,
    UntrustedRelay,
    hkdf,
    run_handshake,
    safety_number,
)


def _assert_relay_is_blind(relay: UntrustedRelay, plaintext: bytes) -> None:
    """The relay can only ever leak what it stores; prove that's opaque ciphertext."""
    payloads = relay.stored_payloads()
    assert payloads, "expected the relay to be holding something in transit"
    for blob in payloads:
        assert isinstance(blob, bytes)
        assert blob != plaintext
        assert plaintext not in blob
    # The relay has no field capable of holding key material.
    for value in vars(relay).values():
        assert not isinstance(value, (x25519.X25519PrivateKey, ed25519.Ed25519PrivateKey))


def _ratchet_root(result) -> bytes:
    """Both parties derive the same 1:1 root key from the handshake's directional keys."""
    lo, hi = sorted([result.send_key, result.recv_key])
    return hkdf(lo + hi, 32, info=b"phase1/ratchet-root")


def test_two_devices_become_friends_and_message_1to1_through_the_relay():
    alice_id, bob_id = IdentityKeyPair.generate(), IdentityKeyPair.generate()

    # 1) Handshake + safety-number verification = "becoming friends".
    alice_hs, bob_hs = run_handshake(alice_id, bob_id)
    assert safety_number(alice_id.public, alice_hs.peer) == \
        safety_number(bob_id.public, bob_hs.peer)

    # 2) Bring up a Double Ratchet seeded from the handshake; Bob published a ratchet prekey.
    root = _ratchet_root(alice_hs)
    assert root == _ratchet_root(bob_hs)
    bob_prekey = X25519PrivateKey.generate()
    bob_prekey_pub = bob_prekey.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    alice = DoubleRatchet.init_alice(root, bob_prekey_pub)
    bob = DoubleRatchet.init_bob(root, bob_prekey)

    alice_handle = alice_id.public.fingerprint_hex
    bob_handle = bob_id.public.fingerprint_hex
    relay = UntrustedRelay()

    # 3) Alice -> relay -> Bob. The relay stores only the opaque blob.
    secret = b"meet at the usual place, 9pm"
    header, body = alice.encrypt(secret)
    relay.post(bob_handle, header.serialize() + body, sender=alice_handle)
    _assert_relay_is_blind(relay, secret)

    (msg,) = relay.deliver(bob_handle)
    blob = msg.payload
    assert bob.decrypt(Header.deserialize(blob[:40]), blob[40:]) == secret

    # 4) Bob replies the same way.
    reply = b"see you there"
    h2, b2 = bob.encrypt(reply)
    relay.post(alice_handle, h2.serialize() + b2, sender=bob_handle)
    (msg2,) = relay.deliver(alice_handle)
    blob2 = msg2.payload
    assert alice.decrypt(Header.deserialize(blob2[:40]), blob2[40:]) == reply


def test_tampering_in_the_relay_is_detected():
    alice_id, bob_id = IdentityKeyPair.generate(), IdentityKeyPair.generate()
    alice_hs, bob_hs = run_handshake(alice_id, bob_id)
    root = _ratchet_root(alice_hs)
    bob_prekey = X25519PrivateKey.generate()
    bob_prekey_pub = bob_prekey.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    alice = DoubleRatchet.init_alice(root, bob_prekey_pub)
    bob = DoubleRatchet.init_bob(root, bob_prekey)

    relay = UntrustedRelay()
    header, body = alice.encrypt(b"authentic payload")
    relay.post("bob", header.serialize() + body, sender="alice")

    (msg,) = relay.deliver("bob")
    tampered = bytearray(msg.payload)
    tampered[-1] ^= 0x01                       # a byte flipped somewhere between the devices
    with pytest.raises(Exception):
        bob.decrypt(Header.deserialize(bytes(tampered[:40])), bytes(tampered[40:]))


def test_mls_group_messages_fan_out_through_the_relay():
    # alice=slot0, bob=slot1, carol=slot2
    g = Group.create(3)
    handles = {0: "alice", 1: "bob", 2: "carol"}
    relay = UntrustedRelay()

    secret = b"group plans the surprise party"
    blob = g.member(0).encrypt_message(secret)
    relay.fanout([handles[1], handles[2]], blob, sender=handles[0])
    _assert_relay_is_blind(relay, secret)

    (to_bob,) = relay.deliver("bob")
    (to_carol,) = relay.deliver("carol")
    assert g.member(1).decrypt_message(to_bob.payload) == secret
    assert g.member(2).decrypt_message(to_carol.payload) == secret


def test_removed_member_cannot_read_group_traffic_relayed_after_removal():
    g = Group.create(4)
    relay = UntrustedRelay()
    carol, _ = g.remove(2, remover=0)          # Carol is evicted; the group re-keys.

    secret = b"post-eviction group message"
    blob = g.member(0).encrypt_message(secret)
    relay.fanout(["bob", "carol"], blob, sender="alice")
    _assert_relay_is_blind(relay, secret)

    (to_bob,) = relay.deliver("bob")
    assert g.member(1).decrypt_message(to_bob.payload) == secret

    (to_carol,) = relay.deliver("carol")       # the relay still forwards her the bytes...
    with pytest.raises(GroupError):            # ...but she can't decrypt them.
        carol.decrypt_message(to_carol.payload)
