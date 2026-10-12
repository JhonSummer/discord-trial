# 03 — Voice: Lyra over BLE Mesh + WebRTC Handoff

Covers your points 1, 5, 6, 20: calling over Bluetooth with Lyra, napkin math over
distance and under N concurrent calls, a small working load test, seamless WebRTC handoff,
and "very high standards of calling, beat them on Bluetooth."

## Why Lyra

Lyra is Google's neural speech codec built for *very* low bitrate while staying
intelligible (public release, 2021). Rates: **Lyra v2 ≈ 3.2 / 6 / 9.2 kbps** (v1 was
~3 kbps). For comparison, Opus for speech is usually 16–32 kbps. On a bandwidth-starved
BLE mesh, an order-of-magnitude smaller stream is the difference between "works" and
"doesn't."

Trade-off to respect: Lyra uses a neural decoder, so it costs CPU/battery and adds
algorithmic latency. On mobile we run it as a native module (the reference implementation
is C++); we budget its frame size into the latency math below.

## Napkin math — does a voice call fit over BLE?

**One stream is tiny.**

| Lyra rate | Bytes/sec | Per 20 ms frame |
| --- | --- | --- |
| 3.2 kbps | 400 B/s | 8 bytes |
| 9.2 kbps | 1,150 B/s | 23 bytes |

**What a BLE link actually gives us.** PHY rates are 1 Mbps (BLE 4.2) / 2 Mbps (BLE 5), but
*application-layer* GATT throughput after overhead is far less. Plan conservatively:

- Conservative sustained app-layer budget per link: **~50–100 kbps**.
- Optimistic (BLE 5, 2M PHY, good conditions, tuned connection interval): several hundred
  kbps.

So **one 9.2 kbps stream ≈ 10–18%** of a conservative link; at 3.2 kbps it's ~3–6%. Raw
bitrate is *not* the binding constraint.

**N concurrent calls through one relay node.** The bottleneck is a node that must *forward*
other people's streams. At a conservative 50 kbps budget per link and ~25% reserved for
overhead/retransmits:

```
usable ≈ 0.75 × 50 kbps ≈ 37.5 kbps per link
streams at 9.2 kbps: ⌊37.5 / 9.2⌋ ≈ 4 simultaneous relayed streams
streams at 3.2 kbps: ⌊37.5 / 3.2⌋ ≈ 11 simultaneous relayed streams
```

With BLE 5's higher budget those numbers multiply several-fold. Takeaway: a single
mid-mesh node can relay a handful of calls at 9.2 kbps or ~a dozen at 3.2 kbps before its
link saturates — and we can *drop each relayed stream to 3.2 kbps adaptively* precisely
when a node is carrying many calls.

**The real constraint is latency, not bandwidth.** Interactive voice wants **< ~150–250 ms**
mouth-to-ear. Per hop we spend roughly:

```
Lyra encode frame (20 ms) + BLE connection-interval queueing (~7.5–30 ms)
+ propagation (~0) + jitter buffer (~40–60 ms) + decode (~few ms)
```

Each extra hop adds mostly the connection-interval + a little jitter margin. Budgeting
~30–40 ms of *added* delay per relayed hop on top of a ~80–100 ms fixed cost, we get:

```
~2–3 hops: comfortably under 200 ms  → great call
~4–5 hops: ~200–280 ms               → usable, noticeably laggy
>5 hops:   route to WebRTC if any node has internet
```

**Distance.** BLE range is ~10–30 m indoors, up to 100 m+ line-of-sight with BLE 5 coded
PHY (at reduced rate). Mesh multiplies reach by hop count, but each hop spends latency
budget — so "reliable over distance" means ~2–3 hops of BLE, i.e. tens of meters through
walls or ~100–300 m line-of-sight, before we prefer an internet leg.

**Conclusion:** Lyra makes the bitrate a non-issue; our engineering effort goes into
**hop-count-aware routing, jitter buffering, and adaptive bitrate**, which is exactly where
we can beat naive BLE voice.

## Beating the bar on Bluetooth (your point 20)

- **Adaptive bitrate per stream**: 9.2 kbps on a short/healthy path, auto-drop to 3.2 kbps
  as hop-count or loss rises. A relay under load signals upstream to downshift.
- **Hop-count-aware routing**: prefer the *lowest-latency* path, not the strongest signal;
  cap interactive voice at a configurable hop limit and spill to WebRTC past it.
- **Forward error correction + PLC**: tiny FEC (cheap at these bitrates) + packet-loss
  concealment so a dropped mesh frame doesn't click.
- **Tuned BLE**: negotiate the fastest safe connection interval and largest MTU; use BLE 5
  2M PHY when both ends support it.

## Seamless WebRTC handoff (your point 6)

A call is a **media session** independent of its path. We keep one logical call and swap
legs under it:

- Media is SRTP either way; on the mesh we carry Lyra-in-SRTP frames over BLE GATT, on the
  internet we carry them over a standard WebRTC peer connection / SFU.
- When a mesh participant gains internet (or the path degrades), we **pre-establish** the
  WebRTC leg, then switch the jitter buffer's input from the BLE leg to the WebRTC leg at a
  frame boundary. Because both legs speak the same Lyra frames + sequence numbers, the
  handoff is a buffer swap, not a renegotiation the user can hear.
- For multiparty, reuse Discord's public approach: a **WebRTC SFU** (selective forwarding
  unit) for the internet side — forward each sender's stream to others without mixing, so
  CPU stays on clients and the server just routes. The mesh side is effectively a
  distributed SFU (each relay forwards).

## Small working load test (your point 5: "need to see load")

Before any phones, validate the *model* in software, then on-device:

1. **Sim harness (host machine).** Simulate a mesh graph of N nodes; each call is a stream
   of 20 ms Lyra-sized frames (8 B @ 3.2 kbps, 23 B @ 9.2 kbps). Give each link the
   conservative 37.5 kbps usable budget + a latency/jitter/loss distribution. Ramp
   concurrent calls until p95 mouth-to-ear exceeds 200 ms or loss exceeds target; record
   the breaking point per topology (line, star, random-geometric).
2. **Two-phone BLE bench.** Real Lyra encode/decode + real GATT link: measure actual
   app-layer throughput, one-hop latency, and battery drain per call-minute.
3. **Three-phone relay bench.** A→B→C where B relays: measure the *added* per-hop latency
   and B's max concurrent relayed streams before degradation — i.e. validate the "~4 @ 9.2
   kbps / ~11 @ 3.2 kbps per node" estimate above.

Deliverable of the test: a table of (topology, bitrate, #concurrent calls) → (p95 latency,
loss, battery), which tells us the real hop/stream caps to encode into the router.

This sim harness is the recommended **first prototype** (pure software, in-repo, no
third-party code, no hardware) — it de-risks the riskiest claim in the whole app.

## Open questions

- Lyra decode CPU/battery budget for *multiple* simultaneous decodes on mid-range Android.
- iOS BLE background execution limits for long calls (CoreBluetooth background modes).
- Echo cancellation / AGC pipeline placement relative to Lyra (before encode).
