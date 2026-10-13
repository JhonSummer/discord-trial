"""Low-level primitive wrappers: SHA-256, HMAC, HKDF (RFC 5869), and ChaCha20-Poly1305 AEAD.

Thin, auditable adapters over PyCA ``cryptography`` + stdlib ``hmac``/``hashlib`` so the
protocol code above reads like the specs. No primitive is re-implemented here.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import List

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

AEAD_KEY_LEN = 32
NONCE_LEN = 12
HASH_LEN = 32


def sha256(*chunks: bytes) -> bytes:
    h = hashlib.sha256()
    for c in chunks:
        h.update(c)
    return h.digest()


def hmac_sha256(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    if not salt:
        salt = b"\x00" * HASH_LEN
    return hmac_sha256(salt, ikm)


def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    out = b""
    t = b""
    counter = 1
    while len(out) < length:
        t = hmac_sha256(prk, t + info + bytes([counter]))
        out += t
        counter += 1
    return out[:length]


def hkdf(ikm: bytes, length: int, salt: bytes = b"", info: bytes = b"") -> bytes:
    """RFC 5869 extract-then-expand."""
    return hkdf_expand(hkdf_extract(salt, ikm), info, length)


def kdf_n(chaining_key: bytes, ikm: bytes, num_outputs: int) -> List[bytes]:
    """Noise HKDF: derive ``num_outputs`` 32-byte keys from (chaining_key, ikm)."""
    if num_outputs not in (2, 3):
        raise ValueError("Noise HKDF yields 2 or 3 outputs")
    prk = hmac_sha256(chaining_key, ikm)
    blob = hkdf_expand(prk, b"", num_outputs * HASH_LEN)
    return [blob[i * HASH_LEN:(i + 1) * HASH_LEN] for i in range(num_outputs)]


def aead_encrypt(key: bytes, plaintext: bytes, associated_data: bytes = b"",
                 nonce: bytes | None = None) -> tuple[bytes, bytes]:
    if nonce is None:
        nonce = os.urandom(NONCE_LEN)
    ct = ChaCha20Poly1305(key).encrypt(nonce, plaintext, associated_data)
    return nonce, ct


def aead_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, associated_data: bytes = b"") -> bytes:
    return ChaCha20Poly1305(key).decrypt(nonce, ciphertext, associated_data)


# --- Raw asymmetric helpers -------------------------------------------------------------
# Thin wrappers over PyCA's X25519 / Ed25519 so the protocol layers (and the RFC
# known-answer tests) can work in raw 32-byte key material without re-plumbing the library's
# key objects at every call site. No curve or signature math is re-implemented here.

def x25519_public(private_scalar: bytes) -> bytes:
    """X25519 public key: clamp(scalar) * basepoint (RFC 7748 §6.1)."""
    priv = X25519PrivateKey.from_private_bytes(private_scalar)
    return priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def x25519_dh(private_scalar: bytes, peer_public: bytes) -> bytes:
    """X25519 Diffie-Hellman shared secret: clamp(scalar) * peer_point (RFC 7748 §5)."""
    priv = X25519PrivateKey.from_private_bytes(private_scalar)
    return priv.exchange(X25519PublicKey.from_public_bytes(peer_public))


def ed25519_public(seed: bytes) -> bytes:
    """Ed25519 public key from a 32-byte secret seed (RFC 8032 §5.1.5)."""
    return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )


def ed25519_sign(seed: bytes, message: bytes) -> bytes:
    """Deterministic Ed25519 signature over ``message`` (RFC 8032 §5.1.6); 64 bytes."""
    return Ed25519PrivateKey.from_private_bytes(seed).sign(message)


def ed25519_verify(public_key: bytes, signature: bytes, message: bytes) -> bool:
    """Verify an Ed25519 signature (RFC 8032 §5.1.7)."""
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
        return True
    except InvalidSignature:
        return False
