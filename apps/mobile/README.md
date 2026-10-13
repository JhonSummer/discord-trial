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

Scaffold. The transport/crypto/protocol packages are implemented and emulator-verified first;
the app consumes them behind a `Transport` interface so the **same** mesh code that passes the
Bumble emulation tests runs on the phone. On-device BLE and the Lyra voice path are the parts
that ultimately require hardware (see `packages/voice` and the root README caveats).

## Planned layout

```
app/            Expo Router screens
src/
  transport/    Transport interface + BLE (native) and relay adapters
  state/        view-models over the protocol DAG/CRDTs
  ui/           components, theme
__tests__/      jest: view-model + protocol-wiring tests (headless)
```
