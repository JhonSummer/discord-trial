# 05 — Social, Bots, Rich Presence, Backups

Covers your points 12, 13, 14, 16, 17 (and ties to 15 from `02`).

## Statuses (your point 14) — rules

Two layers, Discord-like but privacy-first:

- **Availability**: `online`, `idle` (auto after N minutes of no input), `do-not-disturb`
  (suppresses notifications, still receives), `invisible` (appear offline, still use the
  app), `offline`.
- **Custom status**: free text + emoji + optional **expiry** (30 min / 1 hr / today / until
  cleared). Auto-expire so stale "On vacation" statuses die on their own.
- **Privacy**: presence is **friends-only by default** and configurable per-friend / per-list
  (e.g. show real status to close friends, "offline" to acquaintances). Because the server
  is untrusted, presence is shared as signed, friend-encrypted blobs — not a public field
  the server broadcasts.
- **Auto rules**: "in a call" / "on the mesh, offline-internet" are system-derived statuses;
  rich-presence (below) can set an activity status like "Listening to …".

## Anonymous nth-degree friends (your point 15)

Fully specified in `02-crypto-identity.md` (threshold `k` mutuals within `n` hops, private
set intersection so only "≥ k shared" leaks, pseudonymous until mutual accept, abuse
limits). Social-layer note: surface them in a separate "Suggested via mutuals" tray, never
mixed into real friends, always with the mutual count and a one-tap block/decline.

## Bots (your point 16) — adopt Discord's model *and* its constraints

Discord's bot platform is the reference. Its shape and the *reasons* for its constraints
(from Discord's public developer docs/blog):

- **Two surfaces**: a **Gateway** (WebSocket) for real-time events and a **REST** API for
  actions. Bots hold a **bot token** (scoped, revocable) — never a user password.
- **Gateway Intents**: a bot must *opt in* to the event categories it wants. Why: it stops
  every bot from receiving every event (massive needless fan-out) and gates sensitive data.
  **Privileged intents** (e.g. message content, presence, member lists) require explicit
  approval. Why: privacy — message content is sensitive, so you must justify needing it.
- **Rate limits**: per-route + global limits with `429` + `Retry-After`, and buckets so one
  endpoint's spam can't starve others. Why: protect shared infrastructure from a buggy or
  abusive bot (a single misbehaving bot shouldn't DoS everyone).
- **Sharding**: large bots split guilds across multiple gateway connections. Why: one socket
  can't carry millions of guilds' events; sharding spreads load deterministically.

Our twist (because we're E2EE): a bot is **just another member** of a room with its own
identity key. If it needs to read message content, it must be **added to the room's MLS
group** — i.e. a bot can only read what it's cryptographically entitled to, and users *see*
the bot as a member. No server-side bot can silently read content, because the server can't
read content. "Constraints" here are both platform-protection (intents/rate-limits/sharding,
as above) and cryptographic (membership = access).

## Rich presence / app connections (your point 17)

Discord's Rich Presence works via a **local IPC socket**: a game/app on your machine tells
the Discord client "user is doing X," and Discord shows it. Spotify is a special **OAuth
account connection** that syncs now-playing. We mirror both:

- **Local presence SDK**: a small local socket/SDK other apps (or a companion desktop
  helper) can push activity to ("Playing …", "In Claude", custom buttons). The client turns
  it into a friend-encrypted presence blob (same privacy model as statuses).
- **OAuth connections**: Spotify / YouTube Music / etc. connected via **OAuth with minimal
  scopes** (read now-playing only). Tokens live on-device in the secure store; the server
  never sees them. "Claude status" is the same pattern — a connection that reports an
  activity label, nothing more.
- **Privacy**: every rich-presence source is individually toggleable and respects the
  per-friend presence visibility rules.

(Security rule reminder for implementation: OAuth tokens are credentials — they stay in the
device secure store, are never logged, printed, or committed.)

## Backups (your points 12, 13) — local-first, and *responsible* import

### Local backup (point 12)

- The source of truth is the on-device **encrypted SQLite** (SQLCipher-style) store.
- **Backup** = an encrypted snapshot (DB + media blobs) under a **user-held key**
  (passphrase-derived via Argon2id, or an OS-synced key in Keychain/Keystore). Because it's
  already ciphertext, the snapshot can live anywhere — local file, user's own cloud, or a
  volunteer cluster — without trusting the host.
- Incremental: snapshot the event DAG since the last backup; restore replays the DAG into a
  fresh store. Deterministic because the DAG is content-addressed.

### Importing other apps' history (point 13) — what we will and won't do

Goal: let a user bring *their own* chat history in. Boundary: we only ingest data the user
can **legitimately export themselves**, never by defeating another app's encryption.

- **WhatsApp**: WhatsApp has a built-in **"Export chat"** that produces a user-owned
  `.txt` (+ media `.zip`). We write a **parser for that export format** → maps lines to our
  Envelope/message model, attaches media, preserves timestamps and sender labels. This is
  the supported, user-consented path and is straightforward to prototype.
- **What we won't do**: decrypt WhatsApp's `.crypt14/.crypt15` database backups or otherwise
  bypass its encryption — that requires circumventing another service's protections and is
  out of scope on principle.
- **General importer architecture**: a pluggable `Importer` interface (parse → normalize →
  dedup → insert into the event DAG) so Signal/Telegram exports, etc. are just additional
  parsers over the same pipeline. Imported history is marked provenance=`imported` and is
  *local* (not re-federated as if authored on our network).

## Open questions

- Presence fan-out cost when it must be friend-encrypted (N friends × status changes) —
  batch + debounce, maybe a "presence epoch" like MLS.
- Import fidelity: WhatsApp text export loses reactions/replies structure; how much to
  reconstruct heuristically vs. leave flat.
