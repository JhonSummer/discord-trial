"""Phase 0 sim -> Phase 4 voice bridge: score what the simulator's packet delivery sounds like.

The discrete-event simulator ([`sim/`](../../sim)) answers *"how many calls fit on the BLE mesh?"*
in timing/capacity terms; this harness answers *"how good does it sound?"*. ``SimParams(trace=True)``
makes the simulator emit a per-packet delivery trace per call, and ``voiceq.channel.from_sim_delays``
turns one call's trace into a ``DeliveryTrace`` — so real speech can be replayed over the *exact*
loss/delay pattern the simulator produced, and scored.

The payoff is the adaptive-bitrate story, end to end and perceptual: on an oversubscribed relay a
fixed 9.2 kbps call drowns in congestion (packets queue, arrive after the jitter-buffer deadline,
and are dropped), while downshifting the rate — the sim's capacity lever — keeps the very same call
intelligible. These tests use STOI + present-rate rather than the neural MOS, which are unreliable on
the near-silent output of a near-totally-lost call.
"""

from __future__ import annotations

import numpy as np

from meshvoice.codec import LYRA_V2_9200
from meshvoice.network import LinkParams
from meshvoice.scenarios import adaptive_codec_for, shared_relay
from meshvoice.simulator import SimParams, Simulator

from voiceq import SAMPLE_RATE, corpus
from voiceq.channel import from_sim_delays
from voiceq.metrics import score_pair
from voiceq.pipeline import OPTIMIZED, PipelineConfig, run_pipeline

# A conservative classic-BLE relay: ~5.4 streams of 9.2 kbps fit before it saturates.
RELAY = LinkParams(capacity_bps=50_000, connection_interval_ms=15, per=0.01)
OVERLOAD = 7           # calls — oversubscribes the relay at 9.2 kbps, fits at a lower rate
_RATE_NAME = {3200: "3.2k", 6000: "6.0k", 9200: "9.2k"}


def _call0_trace(codec_sim, n_calls: int, seed: int = 1):
    g, calls = shared_relay(n_calls, codec_sim, RELAY, seed=seed)
    res = Simulator(g, calls, SimParams(duration_s=5.2, trace=True, seed=seed)).run()
    ct = res.packet_trace[0]
    return from_sim_delays(np.array(ct.send_s), np.array(ct.delay_s), np.array(ct.lost))


def _replay(bitrate: str, trace):
    """Replay every corpus clip over one sim delivery trace; return mean (STOI, present-rate)."""
    cfg = PipelineConfig(**{**OPTIMIZED.__dict__, "bitrate": bitrate})
    stoi, present = [], []
    for sig in corpus.all_references().values():
        out = run_pipeline(sig, cfg, trace=trace)
        present.append(out.present_rate)
        stoi.append(score_pair(sig, out.audio, SAMPLE_RATE, include={"stoi": True})["stoi"].value)
    return float(np.mean(stoi)), float(np.mean(present))


def test_lone_call_replays_cleanly_through_the_voice_path():
    # One call alone on the relay has spare capacity, so the sim delivers it intact and the
    # replayed speech is clean end-to-end — proving the bridge itself adds no spurious loss.
    stoi, present = _replay("9.2k", _call0_trace(LYRA_V2_9200, 1))
    assert present > 0.98, f"lone-call present-rate {present:.3f} too low"
    assert stoi > 0.70, f"lone-call STOI {stoi:.3f} too low"


def test_adaptive_bitrate_saves_the_call_on_an_overloaded_relay():
    fixed_stoi, fixed_present = _replay("9.2k", _call0_trace(LYRA_V2_9200, OVERLOAD))

    adapt_codec = adaptive_codec_for(OVERLOAD, RELAY)
    assert adapt_codec.bitrate_bps < 9200, "the adaptive lever should downshift under this load"
    adapt_rate = _RATE_NAME[adapt_codec.bitrate_bps]
    adapt_stoi, adapt_present = _replay(adapt_rate, _call0_trace(adapt_codec, OVERLOAD))

    # Fixed 9.2 kbps drowns in congestion; the adaptive downshift keeps the same call intelligible.
    assert fixed_present < 0.5, f"fixed 9.2k present-rate {fixed_present:.3f} (expected a collapse)"
    assert adapt_present > 0.90, f"adaptive present-rate {adapt_present:.3f} too low"
    assert adapt_stoi > fixed_stoi + 0.3, (
        f"adaptive bitrate did not rescue the call: adaptive STOI {adapt_stoi:.3f} "
        f"vs fixed {fixed_stoi:.3f}")
