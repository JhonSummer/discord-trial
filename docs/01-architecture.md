# 01 — System Architecture

## Goal

One app, two transports, one consistent data model:

- **Internet transport**: federated servers (Matrix-like) that store-and-forward
  *ciphertext* and relay real-time events.
- **Bluetooth LE mesh transport**: device-to-device, multi-hop, no internet required
  (bitchat-like). Same message objects, same crypto, different pipe.

The two share one local event log so a message authored offline on the mesh reconciles
cleanly when the device later reaches the internet (and vice-versa).

## Layering

```
┌─────────────────────────────────────────────────────────────┐
│ UI (React Native + native modules)                           │
├─────────────────────────────────────────────────────────────┤
│ App core: chat, calls, presence, bots, backups               │
├───────────────┬───────────────────────────────┬─────────────┤
│ Sync engine   │ Crypto engine                 │ Media engine │
│ (CRDT log,    │ (Noise pairwise, MLS groups,  │ (Lyra voice, │
│  sliding sync)│  identity, safety numbers)    │  WebRTC)     │
├───────────────┴───────────────────────────────┴─────────────┤
│ Transport abstraction  ── same Envelope over either pipe ──  │
│   ┌────────────────────────┐   ┌─────────────────────────┐   │
│   │ Internet transport      │   │ BLE mesh transport      │   │
│   │ (WebSocket gateway,     │   │ (GATT, multi-hop relay, │   │
│   │  store-and-forward,     │   │  store-and-forward,     │   │
│   │  federation)            │   │  gossip/flood-with-TTL) │   │
│   └────────────────────────┘   └─────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│ Local encrypted store (SQLCipher-style) + backup/import       │
└─────────────────────────────────────────────────────────────┘
```

The **Envelope** is the unit both transports carry:

```
Envelope {
  id:          snowflake,          // time-sortable, see "IDs"
  room_id:     opaque,
  sender:      device_pubkey_hash,
  prev:        [envelope_ids],     // causal parents (CRDT / DAG)
  epoch:       mls_epoch,          // which group key era
  ciphertext:  bytes,             // server/mesh never sees plaintext
  sig:         bytes               // sender signature over the above
}
```

Because the Envelope is transport-agnostic and content-opaque, the server and every mesh
relay are *untrusted carriers*. They route and persist blobs; they cannot read them.

## Backend, distilled from Discord's public engineering design

We don't need Discord's code; their *approach* is documented. What we adopt and why:

- **Real-time gateway on the BEAM (Elixir/Erlang).** Discord scaled Elixir to millions of
  concurrent sessions ("How Discord Scaled Elixir to 5,000,000 Concurrent Users"), using
  per-connection lightweight processes, `GenStage` for backpressure, and fan-out helpers
  (Manifold) to push one event to many sessions cheaply. We adopt the same model: one BEAM
  process per connected device, supervised, with backpressure so a slow client can't stall
  a room. For us the gateway only ever ships **ciphertext** envelopes + presence.
- **Hot-path services in Rust.** Discord moved tail-latency-sensitive services from Go to
  Rust to escape GC pauses ("Why Discord is switching from Go to Rust") and used Rust NIFs
  to speed the BEAM. Our fan-out/relay and the store-and-forward queue are Rust for
  predictable p99.
- **Messages in a wide-column store (ScyllaDB).** Discord moved billions→trillions of
  messages from Cassandra to ScyllaDB ("How Discord Stores Trillions of Messages"), keyed
  by `(channel_id, bucket)` with the message snowflake as clustering key. We store
  *ciphertext* envelopes the same way: partition by `(room_id, time_bucket)`, cluster by
  `envelope_id`. This gives cheap "recent messages in a room" reads and time-range paging.
- **Snowflake IDs.** 64-bit, time-ordered IDs (timestamp | worker | seq). Time-sortable
  primary keys make paging and causal ordering cheap, and they're generable offline on the
  mesh (each device is a "worker"), which matters for our offline-first model.
- **"Lazy guild" subscriptions.** Discord's client doesn't load every member of every
  server up front; it subscribes to slices on demand. We do the same for rooms, member
  lists, and read-state to keep the mobile client light (see `04-client-performance.md`).

What we deliberately **don't** copy: a central authority that can read content. Discord's
servers can see messages; ours can't, by construction (E2EE, `02-crypto-identity.md`).

## Federation + p2p survivability (item 19)

Three overlapping ways the network stays alive:

1. **Federated homeservers (Matrix-like).** Anyone can run a server; rooms replicate
   across the servers whose members participate. No single company is a chokepoint.
2. **Volunteer p2p clusters.** Beyond classic homeservers, a room can be backed by a
   DHT-addressed cluster of volunteer nodes (libp2p-style). The room's event DAG is
   content-addressed, so any node holding the blobs can serve them; losing one node loses
   nothing.
3. **BLE mesh islands.** With no internet at all, devices in BLE range form a mesh and
   still deliver messages/calls locally; when any member of the island later gets
   internet, the island's event DAG syncs outward (and inward).

Because every layer carries the *same* content-addressed, signed Envelope, these are not
three systems — they're one event log with three delivery substrates.

## Sync engine (offline-first, no-flicker)

- **Event DAG + CRDT semantics.** Each Envelope lists causal parents (`prev`). Ordering is
  derived (Lamport/snowflake timestamps + DAG), so two devices that were offline on the
  mesh converge without a server referee. Reactions, edits, deletes, and read-markers are
  CRDTs (LWW-register / OR-set) so they never conflict destructively.
- **Sliding-window sync (Matrix "sliding sync" idea).** The client syncs only the rooms
  and ranges currently on screen, expanding as the user scrolls. This is the backbone of
  low RAM and instant startup (detailed in `04-client-performance.md`).
- **Store-and-forward on both pipes.** If a recipient is offline, the server queues
  ciphertext; on the mesh, intermediate nodes hold-and-relay (with TTL + dedup) until the
  target or a better-connected relay appears.

## Open questions

- MLS epoch coordination when a group spans both an internet server and a disconnected
  BLE island simultaneously (split-brain group state → merge rules).
- Spam/abuse control when the server can't read content (reputation + rate-limit on
  *metadata* + proof-of-work on invites; sender-key revocation lists).
- DHT privacy: room discovery without leaking the social graph.
