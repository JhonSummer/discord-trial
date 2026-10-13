"""Double Ratchet for 1:1 messaging (Signal's algorithm) on X25519 + HKDF + ChaCha20-Poly1305.

Gives per-message forward secrecy (a leaked message key reveals nothing about past or future
messages) and post-compromise security (a DH ratchet step heals the session after a key
leak). Handles out-of-order and skipped messages up to a bound.

Reference prototype — production should use libsignal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .primitives import aead_decrypt, aead_encrypt, hkdf, hmac_sha256

MAX_SKIP = 1000


class RatchetError(Exception):
    pass


def _raw(priv: X25519PrivateKey) -> bytes:
    return priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _dh(priv: X25519PrivateKey, pub_raw: bytes) -> bytes:
    return priv.exchange(X25519PublicKey.from_public_bytes(pub_raw))


def _kdf_rk(rk: bytes, dh_out: bytes) -> Tuple[bytes, bytes]:
    out = hkdf(dh_out, 64, salt=rk, info=b"DoubleRatchet/rk")
    return out[:32], out[32:]


def _kdf_ck(ck: bytes) -> Tuple[bytes, bytes]:
    return hmac_sha256(ck, b"\x02"), hmac_sha256(ck, b"\x01")  # (next_ck, message_key)


@dataclass
class Header:
    dh: bytes
    pn: int
    n: int

    def serialize(self) -> bytes:
        return self.dh + self.pn.to_bytes(4, "big") + self.n.to_bytes(4, "big")

    @classmethod
    def deserialize(cls, data: bytes) -> "Header":
        return cls(data[:32], int.from_bytes(data[32:36], "big"), int.from_bytes(data[36:40], "big"))


class DoubleRatchet:
    def __init__(self) -> None:
        self.DHs: Optional[X25519PrivateKey] = None
        self.DHr: Optional[bytes] = None
        self.RK: bytes = b""
        self.CKs: Optional[bytes] = None
        self.CKr: Optional[bytes] = None
        self.Ns = 0
        self.Nr = 0
        self.PN = 0
        self.skipped: Dict[Tuple[bytes, int], bytes] = {}

    @property
    def ratchet_public(self) -> bytes:
        return _raw(self.DHs)

    @classmethod
    def init_alice(cls, root_key: bytes, bob_ratchet_pub: bytes) -> "DoubleRatchet":
        self = cls()
        self.DHs = X25519PrivateKey.generate()
        self.DHr = bob_ratchet_pub
        self.RK, self.CKs = _kdf_rk(root_key, _dh(self.DHs, self.DHr))
        return self

    @classmethod
    def init_bob(cls, root_key: bytes, bob_ratchet_priv: X25519PrivateKey) -> "DoubleRatchet":
        self = cls()
        self.DHs = bob_ratchet_priv
        self.RK = root_key
        return self

    def encrypt(self, plaintext: bytes, associated_data: bytes = b"") -> Tuple[Header, bytes]:
        if self.CKs is None:
            raise RatchetError("no sending chain yet (Bob must receive first)")
        self.CKs, mk = _kdf_ck(self.CKs)
        header = Header(self.ratchet_public, self.PN, self.Ns)
        self.Ns += 1
        nonce, ct = aead_encrypt(mk, plaintext, associated_data + header.serialize())
        return header, nonce + ct

    def decrypt(self, header: Header, body: bytes, associated_data: bytes = b"") -> bytes:
        nonce, ct = body[:12], body[12:]
        ad = associated_data + header.serialize()

        skipped_key = (header.dh, header.n)
        if skipped_key in self.skipped:
            mk = self.skipped.pop(skipped_key)
            return aead_decrypt(mk, nonce, ct, ad)

        if self.DHr is None or header.dh != self.DHr:
            self._skip(header.pn)
            self._dh_ratchet(header)
        self._skip(header.n)

        self.CKr, mk = _kdf_ck(self.CKr)
        self.Nr += 1
        return aead_decrypt(mk, nonce, ct, ad)

    def _skip(self, until: int) -> None:
        if self.Nr + MAX_SKIP < until:
            raise RatchetError("too many skipped messages")
        if self.CKr is not None:
            while self.Nr < until:
                self.CKr, mk = _kdf_ck(self.CKr)
                self.skipped[(self.DHr, self.Nr)] = mk
                self.Nr += 1

    def _dh_ratchet(self, header: Header) -> None:
        self.PN = self.Ns
        self.Ns = 0
        self.Nr = 0
        self.DHr = header.dh
        self.RK, self.CKr = _kdf_rk(self.RK, _dh(self.DHs, self.DHr))
        self.DHs = X25519PrivateKey.generate()
        self.RK, self.CKs = _kdf_rk(self.RK, _dh(self.DHs, self.DHr))
