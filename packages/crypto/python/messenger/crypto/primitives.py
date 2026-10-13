"""Low-level primitive wrappers: SHA-256, HMAC, HKDF (RFC 5869), and ChaCha20-Poly1305 AEAD.

Thin, auditable adapters over PyCA ``cryptography`` + stdlib ``hmac``/``hashlib`` so the
protocol code above reads like the specs. No primitive is re-implemented here.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import List

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

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
