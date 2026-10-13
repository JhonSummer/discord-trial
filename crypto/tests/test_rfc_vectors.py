"""Known-answer tests pinning our primitive wrappers to the published RFC/FIPS vectors.

Every value below is copied from the standard it cites. These tests are the foundation the
whole crypto core rests on: the Noise handshake, the Double Ratchet, and the MLS group schedule
are all built from SHA-256, HMAC, HKDF, X25519, Ed25519, and ChaCha20-Poly1305, so pinning
those six to their specifications is what makes the higher layers trustworthy.

  - SHA-256          FIPS 180-4 / RFC 6234
  - HMAC-SHA-256     RFC 4231
  - HKDF-SHA-256     RFC 5869
  - X25519           RFC 7748 (sections 5.2 and 6.1)
  - Ed25519          RFC 8032 (section 7.1)
  - ChaCha20-Poly1305 (AEAD)  RFC 8439 (section 2.8.2)
"""

from cryptocore import (
    aead_decrypt,
    aead_encrypt,
    ed25519_public,
    ed25519_sign,
    ed25519_verify,
    hkdf,
    hmac_sha256,
    sha256,
    x25519_dh,
    x25519_public,
)
from cryptocore.primitives import hkdf_expand, hkdf_extract


def h(s: str) -> bytes:
    return bytes.fromhex(s)


# --- SHA-256 : FIPS 180-4 / RFC 6234 -----------------------------------------------------
def test_sha256_vectors():
    assert sha256(b"abc").hex() == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert sha256(b"").hex() == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert sha256(b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq").hex() == (
        "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"
    )


# --- HMAC-SHA-256 : RFC 4231 -------------------------------------------------------------
def test_hmac_sha256_rfc4231():
    # Test Case 1
    assert hmac_sha256(bytes([0x0B]) * 20, b"Hi There").hex() == (
        "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"
    )
    # Test Case 2
    assert hmac_sha256(b"Jefe", b"what do ya want for nothing?").hex() == (
        "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"
    )


# --- HKDF-SHA-256 : RFC 5869 -------------------------------------------------------------
def test_hkdf_sha256_rfc5869_case1():
    ikm = bytes([0x0B]) * 22
    salt = h("000102030405060708090a0b0c")
    info = h("f0f1f2f3f4f5f6f7f8f9")
    prk = hkdf_extract(salt, ikm)
    assert prk.hex() == "077709362c2e32df0ddc3f0dc47bba6390b6c73bb50f9c3122ec844ad7c2b3e5"
    okm = hkdf(ikm, 42, salt=salt, info=info)
    assert okm.hex() == (
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
        "34007208d5b887185865"
    )
    # extract-then-expand should equal the one-shot helper
    assert hkdf_expand(prk, info, 42) == okm


def test_hkdf_sha256_rfc5869_case3_zero_salt():
    ikm = bytes([0x0B]) * 22
    prk = hkdf_extract(b"", ikm)
    assert prk.hex() == "19ef24a32c717b167f33a91d6f648bdf96596776afdb6377ac434c1c293ccb04"
    okm = hkdf(ikm, 42)
    assert okm.hex() == (
        "8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d"
        "9d201395faa4b61a96c8"
    )


# --- X25519 : RFC 7748 -------------------------------------------------------------------
def test_x25519_rfc7748_section_5_2():
    # X25519(scalar, u-coordinate) known answers.
    out1 = x25519_dh(
        h("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4"),
        h("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c"),
    )
    assert out1.hex() == "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552"
    out2 = x25519_dh(
        h("4b66e9d4d1b4673c5ad22691957d6af5c11b6421e0ea01d42ca4169e7918ba0d"),
        h("e5210f12786811d3f4b7959d0538ae2c31dbe7106fc03c3efc4cd549c715a493"),
    )
    assert out2.hex() == "95cbde9476e8907d7aade45cb4b873f88b595a68799fa152e6f8f7647aac7957"


def test_x25519_rfc7748_section_6_1_diffie_hellman():
    alice_priv = h("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
    bob_priv = h("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb")
    alice_pub = x25519_public(alice_priv)
    bob_pub = x25519_public(bob_priv)
    assert alice_pub.hex() == "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"
    assert bob_pub.hex() == "de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f"
    shared = "4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742"
    assert x25519_dh(alice_priv, bob_pub).hex() == shared
    assert x25519_dh(bob_priv, alice_pub).hex() == shared  # both sides agree


# --- Ed25519 : RFC 8032 section 7.1 ------------------------------------------------------
# (seed, public key, message, signature) — full sign-and-verify known-answer tests.
_ED25519_KATS = [
    (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
    (
        "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
        "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
    ),
]


def test_ed25519_rfc8032_sign_and_verify():
    for seed_hex, pub_hex, msg_hex, sig_hex in _ED25519_KATS:
        seed, pub, msg, sig = h(seed_hex), h(pub_hex), h(msg_hex), h(sig_hex)
        assert ed25519_public(seed) == pub          # seed -> public key
        assert ed25519_sign(seed, msg) == sig        # deterministic signature
        assert ed25519_verify(pub, sig, msg)         # verifies


def test_ed25519_rejects_tampering():
    seed_hex, pub_hex, msg_hex, sig_hex = _ED25519_KATS[1]
    pub, msg, sig = h(pub_hex), h(msg_hex), h(sig_hex)
    assert not ed25519_verify(pub, sig, msg + b"\x00")        # wrong message
    assert not ed25519_verify(pub, bytes([sig[0] ^ 1]) + sig[1:], msg)  # flipped sig bit


# --- ChaCha20-Poly1305 AEAD : RFC 8439 section 2.8.2 -------------------------------------
def test_chacha20poly1305_rfc8439():
    key = h("808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9f")
    nonce = h("070000004041424344454647")
    aad = h("50515253c0c1c2c3c4c5c6c7")
    plaintext = (
        b"Ladies and Gentlemen of the class of '99: If I could offer you only one tip for "
        b"the future, sunscreen would be it."
    )
    expected_ct = (
        "d31a8d34648e60db7b86afbc53ef7ec2a4aded51296e08fea9e2b5a736ee62d6"
        "3dbea45e8ca9671282fafb69da92728b1a71de0a9e060b2905d6a5b67ecd3b36"
        "92ddbd7f2d778b8c9803aee328091b58fab324e4fad675945585808b4831d7bc"
        "3ff4def08e4b7a9de576d26586cec64b6116"
    )
    expected_tag = "1ae10b594f09e26a7e902ecbd0600691"

    _, ct = aead_encrypt(key, plaintext, aad, nonce)
    # PyCA appends the 16-byte tag to the ciphertext; RFC 8439 lists them separately.
    assert ct.hex() == expected_ct + expected_tag
    assert aead_decrypt(key, nonce, ct, aad) == plaintext
