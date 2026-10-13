"""Noise XX mutually-authenticated handshake: agreement, authentication, tamper rejection."""

import pytest

from cryptocore import (
    HandshakeError,
    IdentityKeyPair,
    aead_decrypt,
    aead_encrypt,
    noise_xx_initiator,
    noise_xx_responder,
    run_handshake,
    safety_number,
)
from cryptocore.handshake import _identity_payload


def test_handshake_derives_matching_directional_keys():
    alice, bob = IdentityKeyPair.generate(), IdentityKeyPair.generate()
    ar, br = run_handshake(alice, bob)
    # Alice's send channel is Bob's receive channel and vice versa.
    assert ar.send_key == br.recv_key
    assert ar.recv_key == br.send_key
    assert ar.send_key != ar.recv_key


def test_handshake_authenticates_both_identities():
    alice, bob = IdentityKeyPair.generate(), IdentityKeyPair.generate()
    ar, br = run_handshake(alice, bob)
    assert ar.peer.fingerprint == bob.public.fingerprint     # initiator learned the responder
    assert br.peer.fingerprint == alice.public.fingerprint   # responder learned the initiator


def test_handshake_hash_is_a_shared_channel_binding():
    alice, bob = IdentityKeyPair.generate(), IdentityKeyPair.generate()
    ar, br = run_handshake(alice, bob)
    assert ar.handshake_hash == br.handshake_hash
    assert len(ar.handshake_hash) == 32


def test_derived_keys_actually_encrypt_between_the_parties():
    alice, bob = IdentityKeyPair.generate(), IdentityKeyPair.generate()
    ar, br = run_handshake(alice, bob)
    nonce, ct = aead_encrypt(ar.send_key, b"ping over the noise channel")
    assert aead_decrypt(br.recv_key, nonce, ct) == b"ping over the noise channel"


def test_independent_handshakes_produce_independent_keys():
    alice, bob = IdentityKeyPair.generate(), IdentityKeyPair.generate()
    first, _ = run_handshake(alice, bob)
    second, _ = run_handshake(alice, bob)
    assert first.send_key != second.send_key     # fresh ephemerals each time


def test_tampered_handshake_message_is_rejected():
    alice, bob = IdentityKeyPair.generate(), IdentityKeyPair.generate()
    hi = noise_xx_initiator(alice)
    hr = noise_xx_responder(bob)

    msg1 = hi.write_message(b"")
    hr.read_message(msg1)
    msg2 = hr.write_message(_identity_payload(bob))

    corrupted = bytearray(msg2)
    corrupted[-1] ^= 0x01                      # flip one bit of the responder's message
    with pytest.raises(HandshakeError):
        hi.read_message(bytes(corrupted))


def test_man_in_the_middle_is_caught_by_the_safety_number():
    """A relay that terminates Noise on both sides can complete a handshake with each party,
    but it ends up authenticated as *itself* — so the safety number Alice computes for her
    peer no longer matches the one she'd compute for the real Bob. That mismatch is exactly
    what the out-of-band safety-number comparison surfaces."""
    alice, bob = IdentityKeyPair.generate(), IdentityKeyPair.generate()
    attacker = IdentityKeyPair.generate()

    # Alice unknowingly handshakes with the attacker, not Bob.
    alice_result, _ = run_handshake(alice, attacker)

    # The handshake succeeds, but Alice authenticated the attacker's identity, not Bob's.
    assert alice_result.peer.fingerprint == attacker.public.fingerprint
    assert alice_result.peer.fingerprint != bob.public.fingerprint

    # So the safety number for the session differs from the one for the intended peer.
    session_sn = safety_number(alice.public, alice_result.peer)
    intended_sn = safety_number(alice.public, bob.public)
    assert session_sn != intended_sn
