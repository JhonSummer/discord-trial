# packages/voice — Lyra voice over the BLE mesh

The voice pipeline: capture → **Lyra** encode (3.2 / 6 / 9.2 kbps, 20 ms frames) → frame for
the mesh → jitter buffer → decode → playout, plus the adaptive-bitrate logic that drops the
rate under mesh load and the hand-off to WebRTC when an internet path appears.

Platform-agnostic logic only (framing, pacing, jitter-buffer policy, rate adaptation, call
signaling). The native Lyra codec and the OS audio I/O are bound per-platform by `apps/mobile`.

## Demarcation — three different "it works" questions

- **Does the pipeline logic work?** Unit-tested here (framing, jitter buffer, rate control).
- **Does the mesh carry N concurrent calls within latency/loss budgets?** Modeled in
  [`../../sim`](../../sim) (radio timing/throughput/loss) and exercisable over the emulated BLE
  stack in [`../../emulation`](../../emulation).
- **Is the codec cheap enough on a real phone?** Not answerable by emulation or simulation.

## Status & honest hardware caveat

The pipeline logic is the scope here. **Lyra's CPU and battery cost under many simultaneous
mesh calls is the single biggest open risk and can only be settled by on-device profiling** —
the simulator gives the shape of the limits, hardware sets the constants. This package ships
the logic and integration points; the native codec binding and the device bench come with the
app and real hardware.
