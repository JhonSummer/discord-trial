# packages/transport — moving frames across internet and BLE mesh

The protocol layer defines *what* a frame is; this package *moves* it, and does so the same way
whether the link is a WebSocket or a Bluetooth GATT connection.

- **Mesh router** — flood with a **TTL** hop budget and **content-addressed dedup** so frames
  don't loop on cyclic topologies; **store-and-forward** for neighbors that are currently
  offline.
- **Node / anti-entropy** — ties the router to the event DAG and periodically reconciles with
  neighbors (have/want digests) so islands that reconnect converge.
- **BLE GATT binding** — the concrete Bluetooth transport: a mesh service/characteristic,
  **length-prefixed fragmentation and reassembly** over the negotiated ATT MTU (default 23
  bytes, so large envelopes must be chunked), and subscribe/notify for the return path.
- **Relay transport** — the internet path (WebSocket to a dumb store-and-forward relay that
  only ever sees ciphertext), with the identical frame semantics.

## Why this split matters

The router/node logic is **transport-agnostic and pure**, so it is unit-tested directly and
then exercised unchanged over the emulated BLE stack in [`../../emulation`](../../emulation).
The exact same code path that passes the Bumble multi-node tests is what the phone runs over
`react-native-ble-plx`.

## Layout

```
python/     reference router/node + BLE GATT binding (verified against Bumble in ../../emulation)
ts/         on-device transport (BLE native adapter + relay adapter) for apps/mobile
```

## Status

Python reference complete: pure router/node (fast tests) plus the Bumble-backed BLE GATT binding
and the headless multi-node emulation suite (`../../emulation`, `../../tests`). The **TypeScript
flood router is ported** (`ts/`) with jest tests mirroring the Python/emulation coverage — line,
star, cyclic (loop-safe dedup), TTL limiting, and store-and-forward — so the same routing logic can
run on the phone over `react-native-ble-plx`. The TS node/anti-entropy + BLE native adapter follow.
