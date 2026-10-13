"""Python side of the cross-language conformance suite.

Asserts the Python reference reproduces every value in ``tests/vectors/conformance.json``
byte-for-byte. The TypeScript suite (``tests/crosslang.conformance.test.ts``) asserts the same
file, so a green run on both sides proves the app and the reference share one wire format and one
set of crypto primitives. Regenerate the vectors with ``python3 tests/vectors/gen_vectors.py``.
"""

import json
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from cryptocore.identity import IdentityKeyPair, PublicIdentity, safety_number
from cryptocore.primitives import aead_decrypt, aead_encrypt, hkdf, sha256
from cryptocore.ratchet import DoubleRatchet, Header, _kdf_ck, _kdf_rk
from messenger.protocol import Envelope, Frame, Snowflake

_VECTORS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors", "conformance.json")


def _load():
    with open(_VECTORS) as f:
        return json.load(f)


def _hex(s: str) -> bytes:
    return bytes.fromhex(s)


def _kp(sign_seed: bytes, agree_scalar: bytes) -> IdentityKeyPair:
    return IdentityKeyPair(
        Ed25519PrivateKey.from_private_bytes(sign_seed),
        X25519PrivateKey.from_private_bytes(agree_scalar),
    )


def test_sha256_vector():
    v = _load()["sha256"]
    assert sha256(_hex(v["input_hex"])).hex() == v["output_hex"]


def test_hkdf_vector():
    v = _load()["hkdf"]
    out = hkdf(_hex(v["ikm_hex"]), v["length"], _hex(v["salt_hex"]), _hex(v["info_hex"]))
    assert out.hex() == v["out_hex"]


def test_aead_vector():
    v = _load()["aead"]
    key, nonce, ad, pt = (_hex(v[k]) for k in ("key_hex", "nonce_hex", "ad_hex", "plaintext_hex"))
    _, ct = aead_encrypt(key, pt, ad, nonce)
    assert ct.hex() == v["ciphertext_hex"]
    assert aead_decrypt(key, nonce, _hex(v["ciphertext_hex"]), ad) == pt


def test_identity_vector():
    v = _load()["identity"]
    alice = _kp(_hex(v["alice_sign_seed_hex"]), _hex(v["alice_agree_scalar_hex"]))
    bob = _kp(_hex(v["bob_sign_seed_hex"]), _hex(v["bob_agree_scalar_hex"]))
    assert alice.public.signing_pub.hex() == v["alice_signing_pub_hex"]
    assert alice.public.agreement_pub.hex() == v["alice_agreement_pub_hex"]
    assert alice.public.fingerprint.hex() == v["alice_fingerprint_hex"]
    assert safety_number(alice.public, bob.public) == v["safety_number"]


def test_envelope_vector():
    v = _load()["envelope"]
    alice = _kp(bytes(range(0, 32)), bytes(range(32, 64)))
    env = Envelope(
        eid=int(v["eid"]),
        room=_hex(v["room_hex"]),
        sender=_hex(v["sender_hex"]),
        prev=tuple(int(p) for p in v["prev"]),
        epoch=v["epoch"],
        ciphertext=_hex(v["ciphertext_hex"]),
    )
    env.sig = alice.sign(env.body())
    assert env.body().hex() == v["body_hex"]
    assert env.sig.hex() == v["sig_hex"]
    assert env.to_bytes().hex() == v["bytes_hex"]

    back = Envelope.from_bytes(_hex(v["bytes_hex"]))
    assert back.verify(alice.public)
    assert back == env


def test_frame_vector():
    v = _load()["frame"]
    frame = Frame(v["ttl"], _hex(v["payload_hex"]))
    assert frame.msg_id.hex() == v["msg_id_hex"]
    assert frame.to_bytes().hex() == v["bytes_hex"]
    assert Frame.from_bytes(_hex(v["bytes_hex"])) == frame


def test_snowflake_vector():
    v = _load()["snowflake"]
    sf = Snowflake(v["node_id"])
    for call in v["calls"]:
        assert str(sf.next(call["now_ms"])) == call["id"]


def test_ratchet_kdf_vectors():
    v = _load()["ratchet"]
    rk = v["kdf_rk"]
    out_rk, out_ck = _kdf_rk(_hex(rk["rk_hex"]), _hex(rk["dh_hex"]))
    assert out_rk.hex() == rk["out_rk_hex"]
    assert out_ck.hex() == rk["out_ck_hex"]
    ck = v["kdf_ck"]
    next_ck, mk = _kdf_ck(_hex(ck["ck_hex"]))
    assert next_ck.hex() == ck["out_ck_hex"]
    assert mk.hex() == ck["out_mk_hex"]


def test_ratchet_session_decrypts():
    s = _load()["ratchet"]["session"]
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    bob = DoubleRatchet.init_bob(
        _hex(s["root_key_hex"]),
        X25519PrivateKey.from_private_bytes(_hex(s["bob_ratchet_priv_hex"])),
    )
    ad = _hex(s["ad_hex"])
    for m in s["messages"]:
        header = Header(_hex(m["dh_hex"]), m["pn"], m["n"])
        assert bob.decrypt(header, _hex(m["body_hex"]), ad) == _hex(m["plaintext_hex"])
