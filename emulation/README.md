# emulation — the BLE emulator harness (the automated verifier)

The point of this folder: **exercise the real Bluetooth mesh transport headless, on CI, with
no radios and no phones.** It is the harness the `tests/` suite drives to prove the mesh works
on an actual BLE stack instead of on napkin math.

Built on Google's [**Bumble**](https://github.com/google/bumble), an open-source Python
Bluetooth stack that **emulates the controller and link layer**. The harness:

- spins up N virtual devices sharing one in-process link (`LocalLink`),
- mounts the transport's **real GATT mesh service** (`packages/transport`) on each one,
- builds topologies (line / star / multi-hop chains) and connects them,
- and lets the actual router flood, fragment/reassemble over the ATT MTU, dedup, and reconcile
  — all the way through genuine GATT writes and notifications.

Optionally, **ns-3's BLE model** can drive realistic radio timing / loss / multi-node physics
for larger meshes (heavier to install; kept optional and out of the default CI path).

## Demarcation — do not confuse these three things

| Thing | What it is | Where |
| --- | --- | --- |
| **BLE emulator** | Emulates the Bluetooth **stack** (controller + link layer) so transport code runs with no radios. **This folder.** | `emulation/` (Bumble) |
| **Physics / radio sim** | Models RF **timing, throughput, and loss** analytically. Not a real BLE stack; answers capacity/latency questions. | `sim/` (meshvoice) |
| **iOS Simulator / Android emulator** | **External** build tools (Xcode / Android Studio) that run the **app's UI** on a desktop. They are **not** in this repo and do **not** emulate Bluetooth between virtual phones. | not a repo folder |

In one line: `emulation/` emulates *Bluetooth*, `sim/` simulates *radio physics*, and the iOS
Simulator / Android emulator run *the app's screens* — three different jobs.

## Run

```bash
pip install bumble            # open-source, pinned; no credentials, no network at test time
python3 -m pytest ../tests    # CI-style transport/crypto-over-emulated-BLE scenarios
```

## Layout

```
harness/     reusable fixtures: build virtual devices, mount the GATT mesh service, wire topologies
```

The CI-style scenarios that *use* this harness (multi-hop delivery, dedup, TTL, reconcile,
E2EE end-to-end) live in [`../tests`](../tests).
