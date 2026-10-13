// A pluggable carrier for serialized mesh frames. The internet relay and the BLE mesh are two
// implementations of this one interface; the app core talks only to `Transport`, so swapping the
// underlying carrier (or using the in-process loopback in dev/tests) changes nothing above it.
export interface Transport {
  send(frameBytes: Uint8Array): void;
  subscribe(handler: (frameBytes: Uint8Array) => void): () => void;
}
