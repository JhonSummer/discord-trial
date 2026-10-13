"""Noise_XX_25519_ChaChaPoly_SHA256 — a mutually-authenticated, forward-secret handshake.

This is the same Noise XX pattern bitchat uses, implemented over the vetted primitives in
``primitives``. XX authenticates each party's X25519 static key; we bind the full identity
(Ed25519 signing key) to it with a self-certificate carried in the encrypted handshake
payload. The resulting ``handshake_hash`` is a channel binding, and a man-in-the-middle who
swaps a static key is caught either by the certificate check here or, in person, by the
``safety_number`` comparison.

Reference prototype — not a line-for-line Noise spec implementation and not security-audited.
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .identity import IdentityKeyPair, PublicIdentity
from .primitives import aead_decrypt, aead_encrypt, kdf_n, sha256

PROTOCOL = b"Noise_XX_25519_ChaChaPoly_SHA256"
PATTERNS = [["e"], ["e", "ee", "s", "es"], ["s", "se"]]


class HandshakeError(Exception):
    pass


def _raw(pub) -> bytes:
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw)


class _SymmetricState:
    def __init__(self) -> None:
        name = PROTOCOL
        self.h = name + b"\x00" * (32 - len(name)) if len(name) <= 32 else sha256(name)
        self.ck = self.h
        self.k: bytes | None = None
        self.n = 0

    def mix_key(self, ikm: bytes) -> None:
        self.ck, self.k = kdf_n(self.ck, ikm, 2)
        self.n = 0

    def mix_hash(self, data: bytes) -> None:
        self.h = sha256(self.h + data)

    def _nonce(self) -> bytes:
        return b"\x00\x00\x00\x00" + self.n.to_bytes(8, "little")

    def encrypt_and_hash(self, plaintext: bytes) -> bytes:
        if self.k is None:
            self.mix_hash(plaintext)
            return plaintext
        ct = aead_encrypt(self.k, plaintext, self.h, self._nonce())[1]
        self.n += 1
        self.mix_hash(ct)
        return ct

    def decrypt_and_hash(self, ciphertext: bytes) -> bytes:
        if self.k is None:
            self.mix_hash(ciphertext)
            return ciphertext
        try:
            pt = aead_decrypt(self.k, self._nonce(), ciphertext, self.h)
        except Exception as exc:  # AEAD failure => tamper / wrong key
            raise HandshakeError("handshake AEAD failure") from exc
        self.n += 1
        self.mix_hash(ciphertext)
        return pt

    def split(self):
        return kdf_n(self.ck, b"", 2)


class HandshakeState:
    def __init__(self, initiator: bool, static_priv: X25519PrivateKey):
        self.ss = _SymmetricState()
        self.ss.mix_hash(b"")  # empty prologue
        self.initiator = initiator
        self.s_priv = static_priv
        self.s_pub = _raw(static_priv.public_key())
        self.e_priv: X25519PrivateKey | None = None
        self.re: bytes | None = None
        self.rs: bytes | None = None
        self.index = 0

    def _dh(self, priv: X25519PrivateKey, pub_raw: bytes) -> bytes:
        return priv.exchange(X25519PublicKey.from_public_bytes(pub_raw))

    def _apply_dh(self, token: str) -> None:
        if token == "ee":
            self.ss.mix_key(self._dh(self.e_priv, self.re))
        elif token == "es":
            self.ss.mix_key(self._dh(self.e_priv, self.rs) if self.initiator
                            else self._dh(self.s_priv, self.re))
        elif token == "se":
            self.ss.mix_key(self._dh(self.s_priv, self.re) if self.initiator
                            else self._dh(self.e_priv, self.rs))

    def write_message(self, payload: bytes) -> bytes:
        tokens = PATTERNS[self.index]
        self.index += 1
        buf = b""
        for t in tokens:
            if t == "e":
                self.e_priv = X25519PrivateKey.generate()
                e_pub = _raw(self.e_priv.public_key())
                buf += e_pub
                self.ss.mix_hash(e_pub)
            elif t == "s":
                buf += self.ss.encrypt_and_hash(self.s_pub)
            else:
                self._apply_dh(t)
        return buf + self.ss.encrypt_and_hash(payload)

    def read_message(self, message: bytes) -> bytes:
        tokens = PATTERNS[self.index]
        self.index += 1
        off = 0
        for t in tokens:
            if t == "e":
                self.re = message[off:off + 32]
                off += 32
                self.ss.mix_hash(self.re)
            elif t == "s":
                length = 32 + (16 if self.ss.k is not None else 0)
                self.rs = self.ss.decrypt_and_hash(message[off:off + length])
                off += length
            else:
                self._apply_dh(t)
        return self.ss.decrypt_and_hash(message[off:])

    def split(self):
        return self.ss.split()

    @property
    def handshake_hash(self) -> bytes:
        return self.ss.h


def noise_xx_initiator(identity: IdentityKeyPair) -> HandshakeState:
    return HandshakeState(True, identity.agreement_private())


def noise_xx_responder(identity: IdentityKeyPair) -> HandshakeState:
    return HandshakeState(False, identity.agreement_private())


@dataclass
class HandshakeResult:
    send_key: bytes
    recv_key: bytes
    peer: PublicIdentity
    handshake_hash: bytes


def _identity_payload(identity: IdentityKeyPair) -> bytes:
    return identity.public.serialize() + identity.self_certificate()


def _verify_peer(payload: bytes, expected_static: bytes) -> PublicIdentity:
    if len(payload) != 128:
        raise HandshakeError("bad identity payload length")
    peer = PublicIdentity.deserialize(payload[:64])
    cert = payload[64:]
    if peer.agreement_pub != expected_static:
        raise HandshakeError("identity agreement key does not match authenticated static")
    if not peer.verify_certificate(cert):
        raise HandshakeError("identity self-certificate invalid")
    return peer


def run_handshake(initiator: IdentityKeyPair, responder: IdentityKeyPair):
    """Drive the full 3-message XX exchange in-process; return (init_result, resp_result)."""
    hi = noise_xx_initiator(initiator)
    hr = noise_xx_responder(responder)

    msg1 = hi.write_message(b"")
    hr.read_message(msg1)

    msg2 = hr.write_message(_identity_payload(responder))
    payload2 = hi.read_message(msg2)
    resp_peer = _verify_peer(payload2, hi.rs)

    msg3 = hi.write_message(_identity_payload(initiator))
    payload3 = hr.read_message(msg3)
    init_peer = _verify_peer(payload3, hr.rs)

    k1, k2 = hi.split()
    rk1, rk2 = hr.split()
    assert (k1, k2) == (rk1, rk2)

    init_result = HandshakeResult(send_key=k1, recv_key=k2, peer=resp_peer,
                                  handshake_hash=hi.handshake_hash)
    resp_result = HandshakeResult(send_key=k2, recv_key=k1, peer=init_peer,
                                  handshake_hash=hr.handshake_hash)
    return init_result, resp_result
