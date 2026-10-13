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

Landing after `packages/protocol`: pure router/node first (fast tests), then the Bumble-backed
BLE binding and the headless multi-node emulation suite.
