# discord-trial — hybrid internet + Bluetooth messenger

A sleek, lightweight iOS/Android messenger that works **with or without the internet**. It
fuses Matrix-style federated E2EE, bitchat-style Bluetooth LE mesh, Discord-grade real-time
system design, and Lyra-compressed voice.

The guiding constraint of this repo is **verifiability over hand-waving**: the Bluetooth mesh
transport is exercised headless on a real emulated BLE stack (Google's
[Bumble](https://github.com/google/bumble), which simulates the controller and link layer),
not just estimated with napkin math; the crypto core is pinned to published RFC vectors; and the
**voice path is scored on real audio** by a committed quality harness ([`voice/`](voice)) that
runs speech through the codec + mesh impairments + jitter buffer + packet-loss concealment and
grades the result with STOI, PESQ, ViSQOL and neural MOS (DNSMOS/PLCMOS). Anything that genuinely
needs physical hardware (the Lyra codec's CPU/battery cost) is called out honestly rather than
faked.

## Quickstart

```bash
# Python side — crypto core, protocol, transport, BLE-emulator verifier, conformance, voice gate
pip install -r requirements.txt            # (for the voice metrics: apt-get install python3.12-dev first)
python3 -m pytest                          # full suite, incl. the Lyra voice-quality gate
PYTHONPATH=voice python3 -m voiceq.bench    # Lyra voice-quality before/after matrix -> voice/results/
python3 crypto/demo.py                      # runnable Phase 1 deliverable transcript

# TypeScript side — shared packages + the phone app
npm install
npm test                                    # jest: 39 tests (incl. cross-language conformance)
npm run typecheck
cd apps/mobile && npx expo export --platform ios   # bundles the app (Hermes)
```

## Monorepo map

| Path | What lives here |
| --- | --- |
| [`apps/mobile`](apps/mobile) | The real phone app — React Native (Expo + TypeScript). UI, screens, and on-device wiring of the shared crypto/protocol/transport packages onto the real Double Ratchet and mesh router. |
| [`crypto`](crypto) | **The Phase 1 crypto core (Python reference).** Identity (Ed25519/X25519), Noise-XX handshake, Double Ratchet (1:1), TreeKEM/MLS (groups), safety numbers, and an **untrusted relay** — on PyCA `cryptography` + stdlib. Pinned to RFC/FIPS known-answer vectors, with a runnable `demo.py`. |
| [`packages/crypto`](packages/crypto) | The **on-device TypeScript** crypto (identity + primitives + Double Ratchet, on `@noble/*`), conformance-locked to the `crypto/` reference byte-for-byte. |
| [`packages/protocol`](packages/protocol) | The wire format both transports carry: signed, content-opaque `Envelope`, mesh `Frame` (TTL + content-addressed dedup), event DAG (causal order + reconcile), CRDTs. Python + TypeScript. |
| [`packages/transport`](packages/transport) | Moves frames: flood mesh router (TTL/dedup/store-and-forward), node sync, and the concrete **BLE GATT binding** (fragmentation/reassembly over the ATT MTU). Python + TypeScript. |
| [`emulation`](emulation) | **The automated verifier.** A headless BLE emulation harness on Bumble: spins up N virtual devices on one link, runs the transport's real GATT service, and exercises multi-node mesh (line / star / multi-hop) with no radios. |
| [`sim`](sim) | Phase 0 discrete-event radio simulator (`meshvoice`): Lyra-over-BLE-mesh timing / throughput / loss, cross-checked against closed-form capacity. |
| [`voice`](voice) | **The Lyra voice-quality harness + committed gate (`voiceq`).** Runs real speech through a low-bitrate parametric codec, the mesh channel (loss/jitter/multi-hop), an adaptive jitter buffer and packet-loss concealment, and scores it with STOI, PESQ, a ViSQOL-style NSIM proxy, and neural MOS (DNSMOS/PLCMOS) — offline. Strong thresholds are enforced as a hard test-suite gate. |
| [`tests`](tests) | Cross-cutting: cross-language conformance vectors (TypeScript ↔ Python), and end-to-end integration (E2EE ciphertext carried over the emulated BLE mesh). |
| [`docs`](docs) | Architecture and design notes, with an explicit public-sources-only sourcing stance. |

## Demarcation — three overloaded words, kept separate

"Emulator" and "simulator" mean three different things in this repo. Keeping them apart is why
the structure is split the way it is:

| Concept | Job | Where |
| --- | --- | --- |
| **BLE emulator** | Emulates the Bluetooth **stack** (controller + link layer) so the real transport code runs headless with no radios. The automated verifier. | [`emulation`](emulation) (Bumble) |
| **Physics / radio sim** | Models RF **timing, throughput, loss** analytically to answer capacity/latency questions. Not a real BLE stack. | [`sim`](sim) (meshvoice) |
| **iOS Simulator / Android emulator** | **External** build tools (Xcode / Android Studio) that run the **app's UI** on a desktop. **Not folders in this repo**, and they do **not** emulate Bluetooth between virtual phones. | not in repo |

And orthogonally: **app code** (`apps/mobile`, `packages/*`, `crypto/`) is the product; the
**BLE emulator** (`emulation`) and **physics sim** (`sim`) are verification tooling, not shipped
in the app.

## How correctness is checked

- **Unit / protocol tests** live beside each package (Python `pytest`, TypeScript `jest`).
- **Crypto primitives** are pinned to their specifications with known-answer tests (SHA-256,
  HMAC, HKDF, X25519, Ed25519, ChaCha20-Poly1305) in [`crypto/tests`](crypto/tests); the Noise
  and MLS layers — spec-inspired reference prototypes, not wire-compatible — are validated
  behaviorally. See [`crypto/README.md`](crypto/README.md) for the honest scope.
- **BLE mesh behavior** is verified in [`emulation`](emulation) against Bumble's emulated
  controller + link layer — actual GATT writes/notifies between virtual devices, so routing,
  fragmentation, dedup, TTL, and reconciliation are tested on the stack, headless.
- **Radio-level capacity/latency** is modeled in [`sim`](sim) and cross-checked against the
  analytic bound.
- **Voice quality** is scored objectively in [`voice`](voice): real speech is run through the
  codec, the mesh channel (loss / jitter / multi-hop), a jitter buffer, and packet-loss
  concealment, then graded with STOI, PESQ, a ViSQOL-style NSIM proxy, and neural MOS
  (DNSMOS/PLCMOS) — all offline. Strong per-condition, per-bitrate thresholds are enforced as a
  committed gate, so a codec / jitter-buffer / PLC regression fails the build.
- **Cross-language parity** is enforced by shared vectors in [`tests`](tests): the same
  envelope/frame/crypto outputs are reproduced byte-for-byte by both Python and TypeScript
  (deterministic Ed25519 means even signatures match), and a session encrypted by the Python
  ratchet is decrypted by the TypeScript ratchet.
- **The app** is jest-tested headless, typechecks clean, and the Expo app is checked to
  actually **bundle** (Metro resolves the workspace TypeScript packages into a Hermes bundle) —
  so "runnable" is verified, not just asserted. Launching the UI itself still needs the
  external iOS Simulator / Android emulator.

## What still needs real hardware (honest caveats)

- **Lyra codec CPU/battery** under many simultaneous mesh calls cannot be settled by
  emulation or simulation; it needs on-device profiling. The sim gives the *shape* of the
  limits; hardware sets the constants. Voice *quality* is no longer hand-waved — the mesh voice
  path (codec framing + loss/jitter/multi-hop + jitter buffer + PLC) is objectively scored and
  gated in [`voice`](voice) — but that harness runs a parametric codec at Lyra's operating points
  as a pluggable stand-in, so the real neural Lyra's absolute fidelity and its CPU/battery cost
  are what still need on-device measurement.
- Bumble emulates the BLE **stack** faithfully but is not an RF model — real-world range,
  interference, and co-channel collisions still require field testing.

## Security rules (always in force)

- Never commit keys, tokens, or credentials.
- No running unverified third-party code that has access to repo/GitHub credentials.
- Open-source libraries are installed as normal, pinned dependencies.
- The crypto here is a vetted-primitive **reference**; production should use audited stacks
  (libsignal / OpenMLS / platform secure enclaves). See [`crypto/README.md`](crypto/README.md).

## Origins

This repo began as a Discord reverse-engineering experiment (RE/REA on the macOS `.dmg`) — which
turned out useless, since the shipped Electron client holds none of Discord's backend/system
design. So the `.dmg` was dropped (it's `.gitignore`d now) and the repo pivoted to building the
messenger that experiment was actually after. Discord's *design ideas* here come only from its
public engineering write-ups, never from its binary.
