# discord-trial — hybrid internet + Bluetooth messenger

A sleek, lightweight iOS/Android messenger that works **with or without the internet**. It
fuses Matrix-style federated E2EE, bitchat-style Bluetooth LE mesh, Discord-grade real-time
system design, and Lyra-compressed voice.

The guiding constraint of this repo is **verifiability over hand-waving**: the Bluetooth mesh
transport is exercised headless on a real emulated BLE stack (Google's
[Bumble](https://github.com/google/bumble), which simulates the controller and link layer),
not just estimated with napkin math. Anything that genuinely needs physical hardware (the
Lyra codec's CPU/battery cost) is called out honestly rather than faked.

## Monorepo map

| Path | What lives here |
| --- | --- |
| [`apps/mobile`](apps/mobile) | The real phone app — React Native (Expo + TypeScript). UI, screens, and on-device wiring of the shared crypto/protocol/transport packages. |
| [`packages/crypto`](packages/crypto) | Identity (Ed25519/X25519), Noise-XX handshake, Double Ratchet (1:1), TreeKEM/MLS (groups), safety numbers. Python reference + TypeScript on-device impl, conformance-tested across both. |
| [`packages/protocol`](packages/protocol) | The wire format both transports carry: signed, content-opaque `Envelope`, mesh `Frame` (TTL + content-addressed dedup), event DAG (causal order + reconcile), CRDTs. |
| [`packages/transport`](packages/transport) | Moves frames: flood mesh router (TTL/dedup/store-and-forward), anti-entropy node sync, and the concrete **BLE GATT binding** (fragmentation/reassembly over the ATT MTU). Internet relay transport too. |
| [`packages/voice`](packages/voice) | Lyra-over-BLE-mesh voice path: framing, jitter model, integration points. Honest about the on-device codec cost that only hardware can settle. |
| [`emulation`](emulation) | **The automated verifier.** A headless BLE emulation harness on Bumble: spins up N virtual devices on one link, runs the transport's real GATT service, and exercises multi-node mesh (line / star / multi-hop) in CI with no radios. |
| [`sim`](sim) | Phase 0 discrete-event radio simulator (`meshvoice`): Lyra-over-BLE-mesh timing / throughput / loss, cross-checked against closed-form capacity. Radio realism to Bumble's stack realism. |
| [`tests`](tests) | Cross-cutting: cross-language conformance vectors (TypeScript ↔ Python) and end-to-end integration (E2EE ciphertext carried over the emulated BLE mesh). |
| [`docs`](docs) | Architecture and design notes, with an explicit public-sources-only sourcing stance. |

## Demarcation — three overloaded words, kept separate

"Emulator" and "simulator" mean three different things in this repo. Keeping them apart is why
the structure is split the way it is:

| Concept | Job | Where |
| --- | --- | --- |
| **BLE emulator** | Emulates the Bluetooth **stack** (controller + link layer) so the real transport code runs headless with no radios. The automated verifier. | [`emulation`](emulation) (Bumble) |
| **Physics / radio sim** | Models RF **timing, throughput, loss** analytically to answer capacity/latency questions. Not a real BLE stack. | [`sim`](sim) (meshvoice) |
| **iOS Simulator / Android emulator** | **External** build tools (Xcode / Android Studio) that run the **app's UI** on a desktop. **Not folders in this repo**, and they do **not** emulate Bluetooth between virtual phones. | not in repo |

And orthogonally: **app code** (`apps/mobile`, `packages/*`) is the product; the **BLE emulator**
(`emulation`) and **physics sim** (`sim`) are verification tooling, not shipped in the app.

## How correctness is checked

- **Unit / protocol tests** live beside each package (Python `pytest`, TypeScript `jest`).
- **BLE mesh behavior** is verified in [`emulation`](emulation) against Bumble's emulated
  controller + link layer — actual GATT writes/notifies between virtual devices, so routing,
  fragmentation, dedup, TTL, and reconciliation are tested on the stack, headless on CI.
- **Radio-level capacity/latency** is modeled in [`sim`](sim) and cross-checked against the
  analytic bound.
- **Cross-language parity** is enforced by shared test vectors in [`tests`](tests).

## What still needs real hardware (honest caveats)

- **Lyra codec CPU/battery** under many simultaneous mesh calls cannot be settled by
  emulation or simulation; it needs on-device profiling. The sim gives the *shape* of the
  limits; hardware sets the constants.
- Bumble emulates the BLE **stack** faithfully but is not an RF model — real-world range,
  interference, and co-channel collisions still require field testing. The [`sim`](sim) models
  loss/latency; neither replaces a radio.

## Security rules (always in force)

- Never commit keys, tokens, or credentials.
- No running unverified third-party code that has access to repo/GitHub credentials.
- Open-source libraries are installed as normal, pinned dependencies.
- The crypto here is a vetted-primitive **reference**; production should use audited stacks
  (libsignal / OpenMLS / platform secure enclaves). See [`packages/crypto`](packages/crypto).

## Origins

This repo began as a Discord reverse-engineering experiment (RE/REA on the macOS `.dmg`) — which
turned out useless, since the shipped Electron client holds none of Discord's backend/system
design. So the `.dmg` was dropped (it's `.gitignore`d now) and the repo pivoted to building the
messenger that experiment was actually after. Discord's *design ideas* here come only from its
public engineering write-ups, never from its binary.
