import pytest

from messenger.crypto.identity import IdentityKeyPair, PublicIdentity, safety_number


def test_keypair_and_public_shapes():
    kp = IdentityKeyPair.generate()
    pub = kp.public
    assert len(pub.signing_pub) == 32
    assert len(pub.agreement_pub) == 32


def test_sign_verify():
    kp = IdentityKeyPair.generate()
    sig = kp.sign(b"hello")
    assert kp.public.verify(sig, b"hello")
    assert not kp.public.verify(sig, b"tampered")


def test_fingerprint_is_stable_and_unique():
    a = IdentityKeyPair.generate()
    assert a.public.fingerprint == a.public.fingerprint
    b = IdentityKeyPair.generate()
    assert a.public.fingerprint != b.public.fingerprint


def test_self_certificate_binds_identity():
    kp = IdentityKeyPair.generate()
    cert = kp.self_certificate()
    assert kp.public.verify_certificate(cert)
    other = IdentityKeyPair.generate()
    assert not other.public.verify_certificate(cert)


def test_safety_number_symmetric_and_distinct():
    a, b, c = (IdentityKeyPair.generate().public for _ in range(3))
    assert safety_number(a, b) == safety_number(b, a)
    assert safety_number(a, b) != safety_number(a, c)
    sn = safety_number(a, b)
    assert sum(ch.isdigit() for ch in sn) == 60


def test_serialize_roundtrip():
    pub = IdentityKeyPair.generate().public
    assert PublicIdentity.deserialize(pub.serialize()) == pub
    with pytest.raises(ValueError):
        PublicIdentity.deserialize(b"too short")
