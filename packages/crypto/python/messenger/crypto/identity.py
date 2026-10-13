"""Identity: a device's long-term signing (Ed25519) + key-agreement (X25519) keys.

The public bundle is what a peer verifies in person via the Bluetooth handshake. A
``safety_number`` is a deterministic function of both parties' public keys — compare it on
two screens (or tap phones) to rule out a man-in-the-middle, exactly as in the design notes.
In production the private keys live in the platform secure enclave and never leave the
device; here they are in-process for the prototype.
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .primitives import sha256


def _raw(public_key) -> bytes:
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)


@dataclass(frozen=True)
class PublicIdentity:
    """A peer's verifiable public identity (what crosses the wire / the BLE handshake)."""
    signing_pub: bytes   # Ed25519, 32 bytes
    agreement_pub: bytes  # X25519, 32 bytes

    def __post_init__(self) -> None:
        if len(self.signing_pub) != 32 or len(self.agreement_pub) != 32:
            raise ValueError("public keys must be 32 raw bytes each")

    @property
    def fingerprint(self) -> bytes:
        """Stable 32-byte identity hash ('their hash' in the design notes)."""
        return sha256(b"idfp", self.signing_pub, self.agreement_pub)

    @property
    def fingerprint_hex(self) -> str:
        return self.fingerprint.hex()

    def verify(self, signature: bytes, message: bytes) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(self.signing_pub).verify(signature, message)
            return True
        except InvalidSignature:
            return False

    def verify_certificate(self, cert: bytes) -> bool:
        """Check the self-certificate binding this signing key to its agreement key."""
        return self.verify(cert, b"idbind" + self.agreement_pub)

    def serialize(self) -> bytes:
        return self.signing_pub + self.agreement_pub

    @classmethod
    def deserialize(cls, data: bytes) -> "PublicIdentity":
        if len(data) != 64:
            raise ValueError("serialized PublicIdentity must be 64 bytes")
        return cls(data[:32], data[32:])

    def x25519(self) -> X25519PublicKey:
        return X25519PublicKey.from_public_bytes(self.agreement_pub)


class IdentityKeyPair:
    def __init__(self, signing: Ed25519PrivateKey, agreement: X25519PrivateKey):
        self._signing = signing
        self._agreement = agreement

    @classmethod
    def generate(cls) -> "IdentityKeyPair":
        return cls(Ed25519PrivateKey.generate(), X25519PrivateKey.generate())

    @property
    def public(self) -> PublicIdentity:
        return PublicIdentity(_raw(self._signing.public_key()), _raw(self._agreement.public_key()))

    def sign(self, message: bytes) -> bytes:
        return self._signing.sign(message)

    def agreement_private(self) -> X25519PrivateKey:
        return self._agreement

    def dh(self, peer_agreement_pub: bytes) -> bytes:
        return self._agreement.exchange(X25519PublicKey.from_public_bytes(peer_agreement_pub))

    def self_certificate(self) -> bytes:
        """Ed25519 signature binding this identity's signing key to its agreement key, so a
        peer that authenticated the X25519 static via Noise can trust the whole identity."""
        return self.sign(b"idbind" + self.public.agreement_pub)


def safety_number(a: PublicIdentity, b: PublicIdentity, digits: int = 60) -> str:
    """Signal-style numeric safety number: symmetric in (a, b), compared out-of-band."""
    lo, hi = sorted([a.fingerprint, b.fingerprint])
    material = sha256(b"safetynumber", lo, hi)
    # expand deterministically to enough digits
    acc = material
    out = []
    while len(out) < digits:
        acc = sha256(acc)
        for byte in acc:
            out.append(str(byte % 10))
            if len(out) >= digits:
                break
    grouped = "".join(out)
    return " ".join(grouped[i:i + 5] for i in range(0, digits, 5))
