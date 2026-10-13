"""Phase 1 — the end-to-end crypto core of the hybrid messenger.

Everything two devices need to become friends and exchange ciphertext that the server can
only relay, never read:

- ``primitives`` — auditable wrappers over PyCA ``cryptography`` + stdlib (SHA-256, HMAC,
  HKDF, ChaCha20-Poly1305, X25519, Ed25519). No primitive is re-implemented.
- ``identity`` — long-term Ed25519 signing + X25519 agreement keys, and Signal-style
  ``safety_number`` verification.
- ``handshake`` — a Noise XX mutually-authenticated, forward-secret handshake.
- ``ratchet`` — the Double Ratchet for forward-secret 1:1 messaging.
- ``mls`` — a TreeKEM-style group key agreement with epochs, plus group application messages.
- ``relay`` — an untrusted store-and-forward relay that holds no keys.

Reference prototype, not security-audited; production should use vetted stacks (libsignal,
a conformant MLS implementation).
"""

from .primitives import (
    aead_decrypt,
    aead_encrypt,
    ed25519_public,
    ed25519_sign,
    ed25519_verify,
    hkdf,
    hmac_sha256,
    kdf_n,
    sha256,
    x25519_dh,
    x25519_public,
)
from .identity import IdentityKeyPair, PublicIdentity, safety_number
from .handshake import (
    HandshakeError,
    HandshakeResult,
    noise_xx_initiator,
    noise_xx_responder,
    run_handshake,
)
from .ratchet import DoubleRatchet, Header, RatchetError
from .mls import Commit, Group, GroupError, GroupMember
from .relay import RelayMessage, UntrustedRelay

__all__ = [
    "aead_decrypt", "aead_encrypt", "hkdf", "hmac_sha256", "kdf_n", "sha256",
    "x25519_dh", "x25519_public", "ed25519_public", "ed25519_sign", "ed25519_verify",
    "IdentityKeyPair", "PublicIdentity", "safety_number",
    "HandshakeError", "HandshakeResult", "noise_xx_initiator", "noise_xx_responder",
    "run_handshake",
    "DoubleRatchet", "Header", "RatchetError",
    "Commit", "Group", "GroupError", "GroupMember",
    "RelayMessage", "UntrustedRelay",
]
