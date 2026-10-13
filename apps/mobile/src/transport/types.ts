// A pluggable carrier for opaque payloads (serialized envelopes). The internet relay and the BLE
// mesh are two implementations of this one interface; the app core talks only to `Transport`, so
// swapping the carrier (loopback for dev/tests, a MeshRouter for multi-hop, a BLE adapter on device)
// changes nothing above it. A mesh carrier owns its own hop framing (TTL/dedup) internally.
export interface Transport {
  send(payload: Uint8Array): void;
  subscribe(handler: (payload: Uint8Array) => void): () => void;
}
