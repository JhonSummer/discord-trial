# tests — CI-style integration & cross-language conformance

Unit tests live **beside each package** (Python `pytest`, TypeScript `jest`). This folder is for
the cross-cutting checks that span components:

- **Transport/crypto over the emulated BLE stack.** Scenario tests that drive the
  [`../emulation`](../emulation) Bumble harness: multi-hop delivery across a line, star fan-out,
  loop-safe dedup on a cyclic graph, TTL expiry, store-and-forward to a reconnecting node,
  anti-entropy reconciliation of two diverged islands, and **E2EE ciphertext (ratchet / MLS)
  carried end-to-end** so carriers only ever see opaque bytes. These are the "it actually works
  on a BLE stack" tests, run headless in CI.
- **Cross-language conformance vectors.** Shared, checked-in vectors so the TypeScript
  on-device code (`packages/*/ts`) and the Python reference (`packages/*/python`) agree
  **byte-for-byte** on envelope/frame serialization and crypto outputs. Either language can
  regenerate and both must match.

## Demarcation

This folder tests **integration against the BLE emulator** (`../emulation`, Bumble — the
Bluetooth stack) and **parity across languages**. It is distinct from `../sim` (radio-physics
modeling, not a stack) and from the iOS Simulator / Android emulator (external tools that run
the app UI, not part of this repo). Real-radio range/interference still needs field testing.

## Run

```bash
python3 -m pytest                      # Python unit + integration + conformance (whole repo)
npm test                               # TypeScript unit + conformance (jest, from repo root)
python3 tests/vectors/gen_vectors.py   # regenerate the shared conformance vectors
```

The conformance vectors in `vectors/conformance.json` are generated from the Python reference and
asserted by both `test_conformance.py` (Python) and `crosslang.conformance.test.ts` (TypeScript).
