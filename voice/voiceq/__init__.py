"""voiceq — the Lyra voice-quality harness.

This package renders *real audio* through the voice path the mesh messenger would use —
a low-bitrate parametric speech codec, packetization into 20 ms frames, a mesh channel
(packet loss, jitter, multi-hop reordering), an adaptive jitter buffer and packet-loss
concealment — and scores the recovered waveform with objective and neural voice-quality
metrics (STOI, PESQ, DNSMOS, PLCMOS, and a ViSQOL-style NSIM proxy).

It is deliberately decoupled from ``sim.meshvoice`` (the Phase 0 *timing* simulator): the
simulator answers "does a call fit on the BLE mesh?" in discrete-event time, while this
harness answers "how good does it *sound* after the mesh has had its way with it?" They
share the same codec bitrates (3.2 / 6.0 / 9.2 kbps) and the same 20 ms frame grid, and
``channel.MeshChannel`` can be driven from a ``sim`` delivery trace for end-to-end fidelity.

Nothing here reaches the network at run time; the neural-MOS model weights are vendored
inside their pip packages. See ``voice/README.md`` for the quality bar and how to run it.
"""

from __future__ import annotations

SAMPLE_RATE = 16_000
FRAME_MS = 20.0
FRAME_LEN = int(round(SAMPLE_RATE * FRAME_MS / 1000.0))  # 320 samples @ 16 kHz

__all__ = ["SAMPLE_RATE", "FRAME_MS", "FRAME_LEN"]
