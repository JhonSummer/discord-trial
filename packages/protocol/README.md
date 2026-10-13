# packages/protocol — the wire format both transports carry

One format rides either the internet relay or the BLE mesh. Nothing in this layer can read
message content; it only carries, routes, and orders **opaque ciphertext** produced by
`packages/crypto`.

- **Envelope** — the unit both transports carry: a Snowflake id (time-sortable, generable
  offline), room, author fingerprint, causal `prev` parents, group-key epoch, the opaque
  `ciphertext`, and an author signature over a deterministic body. Signed by the author,
  content-opaque to every relay.
- **Frame** — the mesh hop unit wrapping an envelope with a **content-addressed message id**
  (for loop-safe dedup on cyclic graphs) and a **TTL** (hop budget).
- **Event DAG** — causal, deterministic ordering from the `prev` links, plus reconciliation so
  two devices that diverged on a disconnected BLE island converge to identical history.
- **CRDTs** — LWW-Register and OR-Set for convergent metadata (names, membership, reactions)
  that merges without a server.

## Layout

```
python/     reference implementation + tests (the ordering/serialization oracle)
ts/         on-device implementation used by apps/mobile + jest tests
```

Serialization is deterministic and versioned so the two languages are byte-identical; parity
is locked by the vectors in `../../tests`.

## Status

The Python `Envelope` + Snowflake exist; `Frame`, `EventDAG`, and the CRDTs are landing next,
then the TypeScript port. The mesh router/node that *moves* these frames lives in
`../transport`.
