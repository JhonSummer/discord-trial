"""Phase 1 — crypto & identity core.

Identity keys + safety numbers (``identity``), a Noise-XX-style mutually-authenticated
handshake (``handshake``), the Double Ratchet for 1:1 messaging (``ratchet``), and a
TreeKEM-style group key agreement for E2EE groups (``mls``). All built on the vetted
primitives in ``primitives``.
"""

from .primitives import aead_decrypt, aead_encrypt, hkdf, hmac_sha256, kdf_n, sha256
from .identity import IdentityKeyPair, PublicIdentity, safety_number
from .handshake import HandshakeError, noise_xx_initiator, noise_xx_responder, run_handshake
from .ratchet import DoubleRatchet, RatchetError
from .mls import Commit, Group, GroupError, GroupMember

__all__ = [
    "aead_decrypt", "aead_encrypt", "hkdf", "hmac_sha256", "kdf_n", "sha256",
    "IdentityKeyPair", "PublicIdentity", "safety_number",
    "HandshakeError", "noise_xx_initiator", "noise_xx_responder", "run_handshake",
    "DoubleRatchet", "RatchetError",
    "Commit", "Group", "GroupError", "GroupMember",
]
