# apps/mobile — the phone app

The **single** runnable messenger — one TypeScript source that builds for **both iOS and
Android** — built with **React Native (Expo + TypeScript)**.

React Native (over Flutter) because the shared protocol/crypto logic is TypeScript, so the app
and the `packages/*` libraries share one language and one set of tests; the view-models can be
unit-tested with `jest` headlessly in CI, and the same wire format is validated against the
Python reference via `tests/`.

## Not to be confused with the BLE emulator

This app runs on the **iOS Simulator / Android emulator** — **external** tools from Xcode /
Android Studio that render the app's UI on a desktop. Those are not part of this repo and they
do **not** emulate Bluetooth between virtual phones. The Bluetooth **stack** is emulated
separately and headlessly in [`../../emulation`](../../emulation) (Bumble) to verify the mesh
transport; see the root README's demarcation table.

## Responsibilities

- **UI / UX:** chat list, conversation view, call screen, contact handshake (scan/tap to
  exchange identity + verify safety number), group management, presence/status.
- **On-device wiring:** instantiate `@messenger/crypto`, `@messenger/protocol`, and
  `@messenger/transport`; pick the live transport (internet relay or BLE mesh) and keep the
  local event DAG/CRDT state in sync.
- **Platform glue:** BLE peripheral/central (e.g. `react-native-ble-plx` on device), secure
  key storage (Keychain / Keystore), background delivery.

## Status

Runnable Expo app with a **headless-tested core**. The `Conversation` view-model turns typed text
into signed (Ed25519), end-to-end-encrypted envelopes on the shared `@messenger/protocol` wire
format and carries them over a pluggable `Transport` — so the **same** code that passes the Bumble
emulation tests is what runs on the phone. Encryption is the real **Double Ratchet** from
`@messenger/crypto` (forward secrecy + post-compromise security), bootstrapped per 1:1 session in
`src/core/session.ts`. The core and its transport abstraction are unit-tested with `jest` in CI
(`__tests__/conversation.test.ts`, including a forward-secrecy check); the React UI is a thin layer
over that core.

What still needs hardware / external tools, and is **not** faked here: running the UI needs the
**iOS Simulator / Android emulator** (external, see above) or a real device; on-device BLE needs a
native module (e.g. `react-native-ble-plx`); the demo bootstraps the ratchet from the two known
in-process identities (a real build gets the root key + prekey from the authenticated handshake);
and the Lyra voice path (see [`docs/03-voice-lyra-mesh.md`](../../docs/03-voice-lyra-mesh.md)) is
CPU/battery-bound, only settleable by on-device profiling.

## Layout

```
App.tsx          root component
index.ts         Expo entry (registerRootComponent)
src/
  core/          Conversation view-model (headless, jest-tested)
  transport/     Transport interface + in-process LoopbackBus (dev/tests)
  ui/            React Native screens + the useConversation hook
__tests__/       jest: core + transport tests (headless, run from repo root)
```

## Run

```bash
npm install                 # from the repo root (workspaces); installs Expo + the shared packages
npm --workspace @messenger/mobile run typecheck   # typecheck the RN/UI layer
cd apps/mobile && npx expo start                   # then press i (iOS sim) / a (Android emulator)
```

The headless core tests run from the repo root with `npm test` (jest), alongside the rest of the
TypeScript suite.
