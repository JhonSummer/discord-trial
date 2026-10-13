# packages/crypto — identity & end-to-end encryption

The cryptographic core, shared in spirit by the app and the reference tooling.

- **Identity** — Ed25519 signing + X25519 key agreement; stable fingerprints and Signal-style
  **safety numbers** compared out-of-band (or over the BLE handshake) to rule out a MITM.
- **Handshake** — a Noise-XX-style mutually-authenticated handshake
  (`Noise_XX_25519_ChaChaPoly_SHA256`) that establishes directional transport keys and binds
  each party's long-term identity.
- **Double Ratchet** — Signal's algorithm for 1:1 messaging: per-message forward secrecy and
  post-compromise security, with bounded out-of-order / skipped-message handling.
- **TreeKEM / MLS** — MLS-inspired group key agreement: every member derives one group key,
  epoch keys chain one-way (forward secrecy), add/remove re-key the tree, and steady-state
  commits cost O(log N).

## Layout

```
ts/         on-device implementation (built on @noble/*), used by apps/mobile + jest tests
```

The Python **reference implementation** (the spec oracle, built on PyCA `cryptography`) lives
at the repository's top-level [`crypto/`](../../crypto) directory (package `cryptocore`), and
additionally covers the untrusted relay and RFC known-answer tests. Both sides are pinned to
the **same cross-language vectors** in `../../tests` so the phone and the reference agree
byte-for-byte on the wire.

## Status & honesty

Working Python reference (identity, handshake, ratchet, MLS) with tests. The TypeScript port
(identity + primitives + **Double Ratchet**, on `@noble/*`) is in place and locked to the Python
reference by the cross-language vectors in `../../tests/vectors` — deterministic Ed25519 means even
signatures match byte-for-byte, and a session encrypted by the Python ratchet is decrypted by the
TypeScript ratchet (and its key schedule matches byte-for-byte). The handshake/MLS TS port follows.
This is a **reference built on vetted primitives**, not an audited protocol stack and
not constant-time-hardened — production should use **libsignal** (1:1) and **OpenMLS** (group),
with private keys held in the platform secure enclave, never in process as they are here.
