"""Generate cross-language conformance vectors from the Python reference implementation.

Run:  python3 tests/vectors/gen_vectors.py
Writes tests/vectors/conformance.json, which both the Python (`test_conformance.py`) and the
TypeScript (`crosslang.conformance.test.ts`) suites assert against. All inputs are fixed, so the
output is deterministic (Ed25519 signatures included), giving byte-exact parity across languages.
"""

import contextlib
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in ("packages/crypto/python", "packages/protocol/python"):
    sys.path.insert(0, os.path.join(_ROOT, _p))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from messenger.crypto.identity import IdentityKeyPair, safety_number
from messenger.crypto.primitives import aead_encrypt, hkdf, sha256
from messenger.crypto.ratchet import DoubleRatchet, _dh, _kdf_ck, _kdf_rk, _raw
from messenger.protocol import EPOCH_MS, Envelope, Frame, Snowflake

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conformance.json")


def kp(sign_seed: bytes, agree_scalar: bytes) -> IdentityKeyPair:
    return IdentityKeyPair(
        Ed25519PrivateKey.from_private_bytes(sign_seed),
        X25519PrivateKey.from_private_bytes(agree_scalar),
    )


@contextlib.contextmanager
def deterministic_urandom(seed: int = 0xA11CE):
    """Make os.urandom deterministic so the captured ratchet session (random AEAD nonces) is
    reproducible — keeping the whole vector file byte-stable across regenerations."""
    counter = seed
    original = os.urandom

    def fake(n: int) -> bytes:
        nonlocal counter
        out = bytearray()
        while len(out) < n:
            out += (counter & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "big")
            counter += 1
        return bytes(out[:n])

    os.urandom = fake
    try:
        yield
    finally:
        os.urandom = original


def ratchet_vectors() -> dict:
    rk_in, dh_in = bytes(range(32)), bytes(range(32, 64))
    out_rk, out_ck = _kdf_rk(rk_in, dh_in)
    ck_in = bytes([0x11]) * 32
    next_ck, mk = _kdf_ck(ck_in)

    root_key = bytes([0x07]) * 32
    bob_ratchet_priv = bytes([0x03]) * 32
    alice_ratchet_priv = bytes([0x05]) * 32
    ad = b"room:general"

    bob_pub = _raw(X25519PrivateKey.from_private_bytes(bob_ratchet_priv))
    alice = DoubleRatchet()
    alice.DHs = X25519PrivateKey.from_private_bytes(alice_ratchet_priv)
    alice.DHr = bob_pub
    alice.RK, alice.CKs = _kdf_rk(root_key, _dh(alice.DHs, bob_pub))

    messages = []
    with deterministic_urandom():
        for plaintext in (b"first", b"second", b"third", b"fourth"):
            header, body = alice.encrypt(plaintext, ad)
            messages.append({
                "pn": header.pn, "n": header.n, "dh_hex": header.dh.hex(),
                "body_hex": body.hex(), "plaintext_hex": plaintext.hex(),
            })

    # Sanity-check that a fresh Bob decrypts the captured session before writing it out.
    bob = DoubleRatchet.init_bob(root_key, X25519PrivateKey.from_private_bytes(bob_ratchet_priv))
    from messenger.crypto.ratchet import Header
    for m in messages:
        assert bob.decrypt(Header(bytes.fromhex(m["dh_hex"]), m["pn"], m["n"]),
                           bytes.fromhex(m["body_hex"]), ad) == bytes.fromhex(m["plaintext_hex"])

    return {
        "kdf_rk": {"rk_hex": rk_in.hex(), "dh_hex": dh_in.hex(),
                   "out_rk_hex": out_rk.hex(), "out_ck_hex": out_ck.hex()},
        "kdf_ck": {"ck_hex": ck_in.hex(), "out_ck_hex": next_ck.hex(), "out_mk_hex": mk.hex()},
        "session": {
            "root_key_hex": root_key.hex(), "bob_ratchet_priv_hex": bob_ratchet_priv.hex(),
            "alice_ratchet_pub_hex": _raw(alice.DHs).hex(), "ad_hex": ad.hex(),
            "messages": messages,
        },
    }


def build() -> dict:
    alice_sign, alice_agree = bytes(range(0, 32)), bytes(range(32, 64))
    bob_sign, bob_agree = bytes(range(64, 96)), bytes(range(96, 128))
    alice, bob = kp(alice_sign, alice_agree), kp(bob_sign, bob_agree)

    s_in = b"hybrid messenger conformance"
    h_ikm, h_salt, h_info, h_len = bytes(range(32)), b"salt-bytes", b"info-bytes", 64
    ae_key, ae_nonce, ae_ad, ae_pt = bytes(range(32)), bytes(range(12)), b"assoc", b"plaintext payload!"

    eid, room, prev, epoch, ct = 1_234_567_890_123, b"general", (11, 22, 33), 7, b"\x00opaque\xff"
    env = Envelope(eid, room, alice.public.fingerprint, prev, epoch, ct)
    env.sig = alice.sign(env.body())

    frame = Frame(5, env.to_bytes())

    sf = Snowflake(42)
    calls = []
    for now in (EPOCH_MS + 100, EPOCH_MS + 100, EPOCH_MS + 50, EPOCH_MS + 200):
        calls.append({"now_ms": now, "id": str(sf.next(now))})

    return {
        "sha256": {"input_hex": s_in.hex(), "output_hex": sha256(s_in).hex()},
        "hkdf": {
            "ikm_hex": h_ikm.hex(), "salt_hex": h_salt.hex(), "info_hex": h_info.hex(),
            "length": h_len, "out_hex": hkdf(h_ikm, h_len, h_salt, h_info).hex(),
        },
        "aead": {
            "key_hex": ae_key.hex(), "nonce_hex": ae_nonce.hex(), "ad_hex": ae_ad.hex(),
            "plaintext_hex": ae_pt.hex(), "ciphertext_hex": aead_encrypt(ae_key, ae_pt, ae_ad, ae_nonce)[1].hex(),
        },
        "identity": {
            "alice_sign_seed_hex": alice_sign.hex(), "alice_agree_scalar_hex": alice_agree.hex(),
            "alice_signing_pub_hex": alice.public.signing_pub.hex(),
            "alice_agreement_pub_hex": alice.public.agreement_pub.hex(),
            "alice_fingerprint_hex": alice.public.fingerprint.hex(),
            "bob_sign_seed_hex": bob_sign.hex(), "bob_agree_scalar_hex": bob_agree.hex(),
            "safety_number": safety_number(alice.public, bob.public),
        },
        "envelope": {
            "eid": str(eid), "room_hex": room.hex(), "sender_hex": alice.public.fingerprint.hex(),
            "prev": [str(p) for p in prev], "epoch": epoch, "ciphertext_hex": ct.hex(),
            "sig_hex": env.sig.hex(), "body_hex": env.body().hex(), "bytes_hex": env.to_bytes().hex(),
        },
        "frame": {
            "ttl": 5, "payload_hex": frame.payload.hex(),
            "msg_id_hex": frame.msg_id.hex(), "bytes_hex": frame.to_bytes().hex(),
        },
        "snowflake": {"node_id": 42, "epoch_ms": EPOCH_MS, "calls": calls},
        "ratchet": ratchet_vectors(),
    }


if __name__ == "__main__":
    with open(OUT, "w") as f:
        json.dump(build(), f, indent=2, sort_keys=True)
        f.write("\n")
    print("wrote", OUT)
