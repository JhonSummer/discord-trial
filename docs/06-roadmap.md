# 06 — Roadmap, Prototype Plan, Risks

How we get from notes to an app that's "a no-brainer above expectations," ordered by
**de-risking the hardest claims first** rather than by easiest-to-build.

## Phasing (dependency order, not calendar)

**Phase 0 — De-risk the physics (software only, in this repo).**
- Build the **BLE-mesh voice simulator** from `03-voice-lyra-mesh.md`: N-node topologies,
  Lyra-sized frames, per-link budget + latency/jitter/loss, ramp concurrent calls to find
  the breaking point. Output the (topology, bitrate, #calls) → (p95 latency, loss) table.
- Why first: "Lyra voice over a BLE mesh at scale" is the riskiest, most differentiating
  claim. Prove the model before building hardware integrations. Pure software, no
  third-party code, no devices.

**Phase 1 — Crypto + identity core.**
- Identity keys in secure enclave; Noise XX handshake; safety-number verification; Double
  Ratchet 1:1; **MLS** group core with epochs. Unit-tested against RFC test vectors.
- Deliverable: two simulated devices become friends and exchange E2EE messages with the
  server holding only ciphertext.

**Phase 2 — Sync engine + transports.**
- Event DAG + CRDT ordering; encrypted SQLite store; sliding-window sync; the internet
  gateway (BEAM) relaying ciphertext; store-and-forward. Then the BLE transport carrying the
  same Envelope with TTL/dedup flood routing.
- Deliverable: a message authored offline on the mesh reconciles after reconnect.

**Phase 3 — Client shell (sleek, low-RAM).**
- RN app with recycling list, optimistic send, anchored scroll, skeletons, native-driver
  animations, animated avatars. Perf gates wired into CI (`04-client-performance.md`).
- Deliverable: a 10k-message room scrolls at 60fps within the RAM budget.

**Phase 4 — Voice for real.**
- Lyra native module; SRTP over BLE GATT; jitter buffer + adaptive bitrate + PLC/FEC;
  hop-aware routing. Then WebRTC leg + seamless handoff + SFU for multiparty.
- Deliverable: a 2–3 hop mesh call under 200 ms that hands off to WebRTC without a glitch.

**Phase 5 — Social & platform.**
- Statuses + rich presence (local SDK + OAuth connections), bot platform (gateway + intents
  + rate limits + membership-as-access), anonymous nth-degree discovery (PSI), local backup
  + WhatsApp-export importer, p2p/cluster hosting.

## Recommended first build (what I'll start on your go-ahead)

The **Phase 0 mesh-voice simulator** — it's the single highest-leverage, fully-safe
artifact: it validates the app's most ambitious promise with nothing but original code in
this repo, and its output directly shapes the routing/codec design. I can start it
immediately as a small, self-contained program with a results table + a few topology
scenarios.

Alternative first build if you'd rather see crypto first: the **Phase 1 handshake + MLS
group demo** (two in-process "devices" that do the Bluetooth-style handshake, verify safety
numbers, and exchange MLS-encrypted group messages through an untrusted relay stub).

## Top risks (and how we're pre-empting them)

| Risk | Pre-emption |
| --- | --- |
| Mesh voice latency blows past 200 ms over multiple hops | Phase 0 sim finds real hop caps; hop-aware routing + spill to WebRTC |
| Lyra decode CPU/battery on mid-range Android under multiple calls | Measure early (Phase 4 bench); adaptive bitrate; cap simultaneous decodes |
| MLS group state split-brain across mesh island ↔ internet | Explicit epochs + defined merge rules (open item in `01`/`02`) |
| Metadata leakage despite E2EE | Sealed-sender envelopes, padding, onion relay on mesh (tracked, not "solved") |
| iOS BLE background limits kill long mesh calls | CoreBluetooth background modes; design around iOS constraints early |
| "Lightweight" regresses as features land | RAM/scroll/cold-start perf gates in CI from Phase 3 |

## Open questions to resolve with you

1. **Platform first**: iOS or Android for the first on-device bench? (Affects BLE + Lyra
   native-module work order.)
2. **First prototype**: mesh-voice simulator (my recommendation) or crypto handshake+MLS
   demo?
3. **OSS reuse policy**: do you want to explicitly authorize cloning specific
   permissively-licensed repos (e.g. an MLS library, a Lyra build) for reference/use? Your
   standing rule is "don't touch any repo other than this one," so I'll keep writing
   original code until you say otherwise.
4. **Scope of the backup importer**: WhatsApp text-export only to start, or also
   Signal/Telegram exports?
