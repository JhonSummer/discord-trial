"""Identity keys, self-certificates, and Signal-style safety numbers."""

import pytest

from cryptocore import IdentityKeyPair, PublicIdentity, safety_number


def test_keypair_generate_and_public_shapes():
    kp = IdentityKeyPair.generate()
    pub = kp.public
    assert len(pub.signing_pub) == 32
    assert len(pub.agreement_pub) == 32
    assert len(pub.fingerprint) == 32
    assert pub.fingerprint_hex == pub.fingerprint.hex()


def test_public_identity_serialize_roundtrip():
    pub = IdentityKeyPair.generate().public
    blob = pub.serialize()
    assert len(blob) == 64
    assert PublicIdentity.deserialize(blob) == pub


def test_deserialize_rejects_wrong_length():
    with pytest.raises(ValueError):
        PublicIdentity.deserialize(b"\x00" * 63)


def test_distinct_identities_have_distinct_fingerprints():
    a = IdentityKeyPair.generate().public
    b = IdentityKeyPair.generate().public
    assert a.fingerprint != b.fingerprint


def test_sign_and_verify():
    kp = IdentityKeyPair.generate()
    msg = b"attach this device"
    sig = kp.sign(msg)
    assert kp.public.verify(sig, msg)
    assert not kp.public.verify(sig, msg + b"!")          # wrong message
    assert not kp.public.verify(bytes([sig[0] ^ 1]) + sig[1:], msg)  # tampered signature


def test_self_certificate_binds_signing_to_agreement_key():
    kp = IdentityKeyPair.generate()
    cert = kp.self_certificate()
    assert kp.public.verify_certificate(cert)
    # A different identity's cert must not validate against this public identity.
    other = IdentityKeyPair.generate()
    assert not kp.public.verify_certificate(other.self_certificate())


def test_safety_number_is_symmetric_and_deterministic():
    a = IdentityKeyPair.generate().public
    b = IdentityKeyPair.generate().public
    assert safety_number(a, b) == safety_number(b, a)        # order-independent
    assert safety_number(a, b) == safety_number(a, b)        # stable


def test_safety_number_format():
    a = IdentityKeyPair.generate().public
    b = IdentityKeyPair.generate().public
    sn = safety_number(a, b, digits=60)
    groups = sn.split(" ")
    assert len(groups) == 12                      # 60 digits in groups of 5
    assert all(len(g) == 5 and g.isdigit() for g in groups)


def test_safety_number_detects_a_swapped_identity():
    """The whole point of the safety number: if either party's key changes (a MITM),
    the compared number changes, so the out-of-band check fails."""
    alice = IdentityKeyPair.generate().public
    bob = IdentityKeyPair.generate().public
    attacker = IdentityKeyPair.generate().public
    legit = safety_number(alice, bob)
    mitm = safety_number(alice, attacker)
    assert legit != mitm
