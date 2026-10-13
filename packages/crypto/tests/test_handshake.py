import pytest

from messenger.crypto.identity import IdentityKeyPair, safety_number
from messenger.crypto.handshake import (
    HandshakeError, _identity_payload, _verify_peer, noise_xx_initiator, noise_xx_responder,
    run_handshake,
)
from messenger.crypto.primitives import aead_decrypt, aead_encrypt


def test_handshake_agrees_on_keys_and_identities():
    alice = IdentityKeyPair.generate()
    bob = IdentityKeyPair.generate()
    ar, br = run_handshake(alice, bob)

    assert ar.send_key == br.recv_key
    assert ar.recv_key == br.send_key
    assert ar.handshake_hash == br.handshake_hash
    assert ar.peer == bob.public      # initiator learned responder
    assert br.peer == alice.public    # responder learned initiator


def test_transport_keys_work():
    ar, br = run_handshake(IdentityKeyPair.generate(), IdentityKeyPair.generate())
    nonce, ct = aead_encrypt(ar.send_key, b"ping")
    assert aead_decrypt(br.recv_key, nonce, ct) == b"ping"
    nonce, ct = aead_encrypt(br.send_key, b"pong")
    assert aead_decrypt(ar.recv_key, nonce, ct) == b"pong"


def test_safety_number_matches_on_both_ends():
    alice = IdentityKeyPair.generate()
    bob = IdentityKeyPair.generate()
    ar, br = run_handshake(alice, bob)
    assert safety_number(alice.public, ar.peer) == safety_number(br.peer, bob.public)


def test_tampered_handshake_message_is_rejected():
    alice = IdentityKeyPair.generate()
    bob = IdentityKeyPair.generate()
    hi = noise_xx_initiator(alice)
    hr = noise_xx_responder(bob)
    hi_msg1 = hi.write_message(b"")
    hr.read_message(hi_msg1)
    msg2 = bytearray(hr.write_message(_identity_payload(bob)))
    msg2[-1] ^= 0x01
    with pytest.raises(HandshakeError):
        hi.read_message(bytes(msg2))


def test_identity_binding_rejects_mismatch():
    bob = IdentityKeyPair.generate()
    payload = _identity_payload(bob)
    with pytest.raises(HandshakeError):
        _verify_peer(payload, b"\x00" * 32)  # static does not match certified key
    forged = bob.public.serialize() + b"\x00" * 64  # invalid certificate
    with pytest.raises(HandshakeError):
        _verify_peer(forged, bob.public.agreement_pub)
