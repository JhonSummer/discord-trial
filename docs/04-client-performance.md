# 04 — Client Performance (sleek, low-RAM, no-flicker)

Covers your points 7, 8, 9, 10: seamless non-flickering chat, nice animations, less RAM
than Matrix clients, lightweight on phone, and Discord-style loading practices.

## RAM budget — why this beats typical Matrix clients

Element (the reference Matrix client) is Electron/web-heavy on desktop and historically
memory-hungry because it keeps large room state and timelines in memory and does expensive
E2EE bookkeeping. Our wins:

1. **Sliding-window sync** (Matrix's own newer "sliding sync" direction): hold only the
   rooms + message ranges currently visible, plus a small ring buffer around them. Idle
   rooms cost a row in SQLite, not a live timeline in RAM.
2. **Everything on disk first.** The encrypted SQLite store is the source of truth; the UI
   reads windows from it. Target a hard cap on in-memory messages per room (e.g. a few
   hundred) and evict aggressively on scroll-away.
3. **MLS over Megolm** reduces per-group key bookkeeping (see `02`), which is a real memory
   and CPU cost in large encrypted rooms.
4. **Native lists, not DOM.** React Native with a recycling list (FlashList-style) reuses a
   handful of row views regardless of history length.

Target: a cold room open and a 10k-message scroll should stay within a small, bounded
working set — measured, not assumed (RAM is a tracked metric in `06-roadmap.md`).

## No-flicker chat (your point 7)

Flicker comes from re-layout, re-keying, and content reflow. Rules:

- **Stable keys**: every message row keyed by its snowflake `id`, never by array index, so
  re-renders don't reshuffle the list.
- **Anchored scrolling**: when older messages load above, preserve the scroll anchor on the
  first visible message (maintain-visible-content-position) so the viewport doesn't jump.
- **Optimistic send**: the message appears instantly with a "sending" state keyed by a
  client-generated snowflake; when the ack arrives it's the *same* key, so no insert/remove
  flashes.
- **Reserve media dimensions**: images/video reserve their final box from known
  width/height before bytes arrive — no reflow when they decode.
- **Decode off the UI thread**: image/Lyra/media decode on worker threads; the UI thread
  only commits finished frames.

## Discord-style loading practices (your point 10)

From Discord's publicly described client behavior:

- **READY-then-lazy**: on connect, fetch a tiny bootstrap (which rooms exist, unread
  counts), *not* full history or full member lists.
- **"Lazy guild"/on-demand subscriptions**: subscribe to a room's member list and presence
  only while it's on screen; unsubscribe on leave. We apply this to rooms, member lists,
  and read-state.
- **Progressive + prefetch**: render the visible range immediately, prefetch the next
  window just before it scrolls in, and warm the *likely* next room (most-recent/most-active)
  in the background at low priority.
- **Sprite/atlas for emoji & avatars**: batch many tiny images to avoid per-asset overhead;
  animated avatars (below) only animate when on-screen.

## Animations (your point 8)

- Run all animations on the **native driver** (transforms/opacity only) so they stay at
  60–120fps independent of JS-thread load — a janky animation almost always means it's
  animating a layout property on the JS thread; we forbid that.
- **Shared-element transitions** for avatar→profile and chat→thread, **skeleton
  placeholders** (not spinners) during the sliding-sync fetch, and spring physics for the
  message-send and reaction pops.
- Respect "reduce motion" accessibility settings.

## Animated avatars (your point 18)

- Support animated GIF/WebP/APNG/Lottie avatars. Decode to a frame atlas once; cap frame
  rate and *pause when off-screen* (same rule as emoji) so a list full of animated avatars
  doesn't melt the CPU.
- Store the avatar as an encrypted blob like any other media; only friends can fetch the
  key.

## Measurement (so "lightweight" is a fact, not a vibe)

- CI perf gates: cold-start time, time-to-first-message, RAM after opening a large room,
  dropped-frame count during a fast scroll, scroll jank p95.
- A/B the sliding-sync window size vs RAM vs scroll-ahead smoothness.
