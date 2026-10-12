# Hybrid Internet + Bluetooth Messenger — Design Notes

Living design notes for a sleek, lightweight iOS/Android messenger that fuses:

- **Matrix-style** federated, end-to-end-encrypted messaging,
- **bitchat-style** Bluetooth LE mesh (works with no internet),
- **Discord-grade** system design, real-time feel, bot platform, and rich presence,
- **Lyra**-compressed voice that can ride a BLE mesh and hand off to WebRTC.

These are *active notes*: they evolve as decisions are made. Each doc states what we
know, what we've decided, and what's still open.

## Sourcing stance (read this first)

Everything here is synthesized from **public, authoritative sources** and standard
engineering practice — not from decompiling anyone's shipped app:

- Discord's *system design* is drawn from their public engineering posts and talks
  (message storage on Cassandra→ScyllaDB, the Elixir real-time gateway, Go→Rust for
  tail-latency-sensitive services, the WebRTC SFU for voice). The `Discord.dmg` in this
  repo is only the Electron **client** installer and contains **none** of that backend
  design, so it is not a useful or appropriate source and is left untouched.
- Matrix (Olm/Megolm, MLS adoption, sliding sync) and bitchat (BLE mesh + Noise) are
  referenced from their **public** protocol specs and open-source designs.
- Lyra from Google's public codec release and paper; MLS from RFC 9420; WebRTC from the
  W3C/IETF specs.

Where a claim comes from a specific public write-up, it's named inline so decisions are
traceable and legitimate.

## Index

| Doc | Scope |
| --- | --- |
| [`01-architecture.md`](01-architecture.md) | End-to-end system: transports (internet + BLE mesh), backend distilled from Discord's public design, data model, federation/p2p, offline-first sync |
| [`02-crypto-identity.md`](02-crypto-identity.md) | Bluetooth handshake, pairwise Noise sessions, MLS group E2EE, safety numbers, "keys on device, server relays ciphertext", nth-degree anonymous friends |
| [`03-voice-lyra-mesh.md`](03-voice-lyra-mesh.md) | Lyra over BLE mesh, bandwidth/latency napkin math, concurrent-call load model, WebRTC handoff, and a small working load test plan |
| [`04-client-performance.md`](04-client-performance.md) | Discord-grade loading, no-flicker chat, low RAM vs Matrix clients, 60fps animations, mobile list virtualization |
| [`05-social-bots-presence-backups.md`](05-social-bots-presence-backups.md) | Status rules, anonymous friends, Discord-style bot model + why its constraints exist, Spotify/YouTube/Claude rich presence, local backup + responsible import |
| [`06-roadmap.md`](06-roadmap.md) | Phasing, what to prototype first, load-test plan, risks, open questions |

## Design principles

1. **Offline-first.** The mesh path is not a fallback; it's a first-class transport.
   Internet is "the mesh with a very long cable."
2. **Server sees ciphertext only.** Private keys never leave the device. The server is a
   dumb, untrusted relay + store-and-forward queue for encrypted blobs.
3. **Lightweight beats feature-complete.** A strict RAM/CPU budget per screen; we'd
   rather ship fewer features that stay at 60fps than a clunky everything-client.
4. **Borrow proven design, write original code.** We copy *ideas* from public sources,
   not bytes from anyone's binary.
