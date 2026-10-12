# 02 — Crypto & Identity

Covers your points 2, 3, 4, 11, 15: Bluetooth handshake, becoming friends by exchanging
keys, adding each other's hashes, server-only-sees-ciphertext, E2EE group chat, and
anonymous nth-degree friends.

## Identity

- Each device generates a long-term **identity keypair** (Ed25519 for signing, X25519 for
  key agreement) at first run. Private keys are stored in the platform secure enclave
  (iOS Keychain/Secure Enclave, Android Keystore/StrongBox) and **never leave the device**.
- A user = a set of devices they own; devices cross-sign each other (Matrix-style
  cross-signing) so a friend verifies the *person* once and trusts their devices.
- A device's public identity is addressed by a **hash of its public key** (`device_pubkey_hash`
  in the Envelope). "Adding each other's hashes" (your point 3) = storing the peer's
  verified identity-key fingerprint locally.

## The Bluetooth handshake → friendship (your points 1, 2, 4)

The out-of-band (OOB) Bluetooth channel is what makes key exchange trustworthy: you're
physically near the person, so a man-in-the-middle on the internet can't sit in between.

```
Alice                                   Bob
  │   1. BLE discover + connect (GATT)   │
  │─────────────────────────────────────▶│
  │   2. Noise XX handshake over BLE      │   (mutual auth, forward secrecy)
  │◀────────────────────────────────────▶│
  │   3. Exchange long-term identity pubkeys
  │◀────────────────────────────────────▶│
  │   4. Both compute Safety Number =
  │      SHA-256(sort(pubkeyA, pubkeyB))
  │      → short emoji/number string
  │   5. Compare on-screen / tap phones (NFC) to confirm — defeats MITM
  │   6. Each stores the other's verified fingerprint → "friends"
```

- **Transport session**: Noise Protocol `XX` pattern (the same family bitchat uses) gives a
  mutually-authenticated, forward-secret channel over BLE for the handshake itself.
- **Safety Number**: a deterministic hash of both identity keys rendered as a short
  comparable string (Signal's "safety numbers" idea). If Alice's screen and Bob's screen
  show the same string, there's no MITM. Optionally auto-confirm by NFC tap so users don't
  have to read digits.
- **Result**: both devices now hold each other's *verified* identity public key. From here
  on, messages between them are E2EE and the server/mesh only ever carries ciphertext
  (your point 4: "only keys transfer / only encrypted messages transfer").

The same handshake can be done without BLE (QR code, or server-mediated with safety-number
verification) — BLE is the premium, in-person path.

## Pairwise (1:1) messaging

- Double Ratchet (Signal) over the verified identity keys: per-message forward secrecy and
  post-compromise security. This is the well-trodden path and we don't reinvent it.
- The server stores the ciphertext envelope keyed by room; it cannot derive the message
  key. On the mesh, the same ciphertext hops node-to-node.

## Group E2EE (your point 11) — use MLS, not sender-keys

Matrix today mostly uses **Megolm** (sender-keys): each sender shares a ratcheting group
key; adding/removing members and re-keying is O(N) messages and gets expensive and
leaky for large, churny groups. We instead target **MLS (RFC 9420)**:

- Members form a **ratchet tree**; the group key is derived from the tree.
- Adds/removes/updates are **O(log N)** instead of O(N) — crucial for big or fast-changing
  groups.
- Gives **forward secrecy** (past messages safe if a key leaks later) and **post-compromise
  security** (one compromised member doesn't permanently own the group after the next
  update).
- Each Envelope carries its **MLS epoch**; a device that missed epochs fetches the key
  updates (ciphertext) and catches up. This epoch field is already in the Envelope
  (`01-architecture.md`).

Why this matters for us specifically: our groups can fork across a BLE island and the
internet and later merge. MLS's explicit epochs + tree deltas make "merge two divergent
group states" tractable; sender-keys would be a nightmare here.

## "Keys on device, server relays ciphertext" (your point 4), concretely

- Private keys: secure enclave, never transmitted.
- What transits the internet: **public keys / MLS key-packages / ciphertext**. The server
  is a key-*transparency* log + blob relay. It can't read messages, and we can publish a
  verifiable key-transparency log so it can't silently swap someone's key either.
- What transits the BLE mesh: identical ciphertext envelopes.

## Anonymous nth-degree friends (your point 15)

Goal: let you reach someone who is an *n-th mutual* (friend-of-friend-of-…) without
exposing your full social graph to the server.

Design:

- **Threshold rule**: a candidate becomes "introducible" only if you share ≥ `k` mutual
  connections within `n` hops (e.g. `n=2`, `k≥3`). Defaults are conservative and
  user-configurable.
- **Private mutual-count, not a graph dump**: compute the mutual-friend overlap with
  **private set intersection (PSI)** or Bloom-filter cardinality estimation, so each side
  learns only "we share ≥ k" — not *who* or the rest of the graph. The server never gets
  the plaintext graph (it only holds encrypted/committed contact sets).
- **Pseudonymous until mutual accept**: the candidate appears under a one-time pseudonym +
  "3 mutuals" badge. Real identity keys are exchanged only after both tap accept — i.e. the
  normal handshake, just bootstrapped online instead of over BLE.
- **Abuse limits**: rate-limit introductions, require proof-of-work on unsolicited
  introductions, and let users turn FoF discovery off entirely.

Open: PSI cost on mobile for large contact lists (may need bucketing / cuckoo filters);
Sybil resistance on mutual-count inflation.

## Threat model (brief)

- **Honest-but-curious server/relay**: defeated — sees only ciphertext + minimal routing
  metadata.
- **Network MITM**: defeated by OOB safety-number verification.
- **Compromised device**: forward secrecy + PCS (Double Ratchet / MLS) limit blast radius;
  cross-signing revocation removes a lost device.
- **Metadata**: hardest problem. Mitigate with sealed-sender-style envelopes, padding, and
  (on mesh) onion-style relay. Tracked as an open area, not "solved."
