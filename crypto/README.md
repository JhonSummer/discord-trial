# cryptocore — Phase 1 end-to-end crypto core

The cryptographic heart of the hybrid messenger (see
[`../docs/02-crypto-identity.md`](../docs/02-crypto-identity.md) and the Phase 1 entry in
[`../docs/06-roadmap.md`](../docs/06-roadmap.md)). It is everything two devices need to
**become friends and exchange ciphertext the server can only relay, never read**:

- identity keys + **safety-number** verification,
- a **Noise XX** mutually-authenticated, forward-secret handshake,
- the **Double Ratchet** for 1:1 messaging,
- an **MLS/TreeKEM-style** group key agreement with epochs, and
- an **untrusted store-and-forward relay** that holds no keys.

All original in-repo code, built on thin auditable wrappers over
[PyCA `cryptography`](https://cryptography.io) + the Python standard library. No primitive is
re-implemented, nothing touches the network, and there are no credentials anywhere.

## Run

```bash
cd crypto
pip install -r requirements.txt
python3 -m pytest -q          # 44 tests
python3 demo.py               # runnable deliverable: a transcript of the scenario below
```

`demo.py` runs the Phase 1 deliverable live — the Noise handshake, the safety-number check,
1:1 and MLS group messages through the relay — and prints what each party sends and reads and
what the relay stores (opaque ciphertext). It prints no keys or secrets.

## What's in here

- **`cryptocore/primitives.py`** — SHA-256, HMAC-SHA256, HKDF, ChaCha20-Poly1305, X25519,
  Ed25519, and the Noise KDF, as small adapters over the library.
- **`cryptocore/identity.py`** — long-term Ed25519 signing + X25519 agreement keys, identity
  fingerprints, self-certificates, and Signal-style numeric safety numbers (compared
  out-of-band to rule out a man-in-the-middle).
- **`cryptocore/handshake.py`** — `Noise_XX_25519_ChaChaPoly_SHA256`. XX authenticates each
  party's X25519 static key; the full identity (Ed25519 key) is bound to it by a
  self-certificate carried in the encrypted payload, and the `handshake_hash` is a channel
  binding.
- **`cryptocore/ratchet.py`** — the Double Ratchet: per-message forward secrecy plus
  post-compromise healing, tolerant of out-of-order and skipped messages.
- **`cryptocore/mls.py`** — a TreeKEM-style ratchet tree with epoch keys: create, commit,
  add, remove, and per-epoch application-message encrypt/decrypt.
- **`cryptocore/relay.py`** — the untrusted relay: per-recipient mailboxes that store and
  forward opaque blobs and fan out group ciphertext, with no field able to hold a key.

## Testing against RFC vectors

`tests/test_rfc_vectors.py` pins every primitive to its published specification with
known-answer tests:

| Primitive | Source |
|---|---|
| SHA-256 | FIPS 180-4 / RFC 6234 |
| HMAC-SHA256 | RFC 4231 |
| HKDF-SHA256 | RFC 5869 (cases 1 & 3) |
| X25519 | RFC 7748 §5.2 and §6.1 |
| Ed25519 sign/verify | RFC 8032 §7.1 |
| ChaCha20-Poly1305 (AEAD) | RFC 8439 §2.8.2 |

**Honest scope note.** The *primitives* are tested against their official RFC vectors above.
The Noise handshake and the MLS/TreeKEM layer are *inspired by* their specifications (the
[Noise Protocol Framework](https://noiseprotocol.org) and
[RFC 9420](https://www.rfc-editor.org/rfc/rfc9420)) but are reference prototypes and are
**not wire-compatible** with them — so they cannot and do not claim to pass those standards'
own wire test vectors. Instead they are validated *behaviorally* (key agreement, mutual
authentication, forward secrecy, channel binding, tamper rejection, and removed-member
exclusion) in `tests/test_handshake.py`, `tests/test_ratchet.py`, and `tests/test_mls.py`.

## The Phase 1 deliverable

`tests/test_relay.py` is the roadmap's Phase 1 deliverable as an executable scenario:

1. Two devices run the Noise handshake and verify they compute the **same safety number** —
   i.e. they become friends with no man-in-the-middle.
2. They bring up a Double Ratchet seeded from the handshake and exchange **1:1 messages
   through the relay**; the relay stores only opaque ciphertext and each side decrypts.
3. A three-member MLS group sends an **application message fanned out by the relay**; every
   current member decrypts it, and the relay still sees only ciphertext.
4. Tampering with a relayed blob is rejected, and a **removed member can no longer read**
   group traffic the relay forwards after the eviction.

Each scenario asserts the relay is *blind*: everything it holds is bytes that neither equal
nor contain the plaintext, and it owns no key material.

## Security & limitations

This is a **reference prototype, not security-audited.** In production, private keys live in
the platform secure enclave, and the 1:1 and group layers should be a vetted stack
(libsignal, a conformant MLS implementation such as OpenMLS) rather than these teaching
implementations. The relay here is an in-process model of the honest-but-curious server; it
demonstrates the confidentiality property (ciphertext-only) but not availability, metadata
protection, or the key-transparency log described in the design notes.

`cryptography` and `pytest` are installed as normal open-source dependencies; no third-party
protocol code is vendored into this repository.
