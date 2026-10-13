"""End-to-end mesh voice path: clean speech in, recovered speech out.

    clean -> encode (parametric codec) -> packets
          -> mesh channel (loss / jitter / multi-hop)
          -> jitter buffer (fixed or adaptive playout)
          -> [optional FEC recovery from the next packet's redundancy]
          -> PLC (silence or parametric concealment)
          -> phase-continuous synthesizer -> recovered audio

Two presets bracket the optimization the user asked for:

* ``BASELINE`` — a small fixed jitter buffer and silence concealment (drop-outs become gaps).
* ``OPTIMIZED`` — an adaptive jitter buffer and parametric concealment.
* ``OPTIMIZED_FEC`` — adds one-frame in-band redundancy (costs +3.2 kbps) for the hardest losses.

``run_pipeline`` is deterministic in ``seed`` and returns both the audio and the operating
statistics (effective bitrate, loss, frames concealed, added latency) so the bench can report the
latency cost that buys the quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from .channel import DeliveryTrace, MeshChannel, MeshCondition, condition
from .codec import FrameParams, ParametricCodec, Synthesizer, unpack
from .dsp import mel_centers
from .jitterbuffer import AdaptiveJitterBuffer, FixedJitterBuffer
from .plc import make_plc


@dataclass
class PipelineConfig:
    bitrate: str = "9.2k"
    jitter_buffer: str = "adaptive"     # "fixed" | "adaptive"
    fixed_target_ms: float = 40.0
    plc: str = "parametric"             # "silence" | "parametric"
    fec: bool = False
    aperiodicity: float = 0.08
    label: str = ""


BASELINE = PipelineConfig(jitter_buffer="fixed", fixed_target_ms=60.0, plc="silence", fec=False, label="baseline")
OPTIMIZED = PipelineConfig(jitter_buffer="adaptive", plc="parametric", fec=False, label="optimized")
OPTIMIZED_FEC = PipelineConfig(jitter_buffer="adaptive", plc="parametric", fec=True, label="optimized+fec")
PRESETS = {"baseline": BASELINE, "optimized": OPTIMIZED, "optimized_fec": OPTIMIZED_FEC}


@dataclass
class PipelineResult:
    audio: np.ndarray
    effective_bitrate_bps: int
    channel_loss: float
    present_rate: float
    concealed_frames: int
    mean_latency_ms: float
    condition_name: str
    config: PipelineConfig


def _apply_fec(received: List[Optional[object]], present: np.ndarray,
               clean: np.ndarray, aperiodicity: float, main_bands: int, fs: int):
    """One-frame in-band redundancy: recover an absent frame from the next packet's coarse copy.

    The redundant copy is coded at 3.2 kbps (a 16-band envelope); re-grid it onto the main
    profile's band centres so the synthesizer can render it.
    """
    coarse = ParametricCodec("3.2k", aperiodicity=aperiodicity)
    coarse_params = [unpack(p, coarse.profile) for p in coarse.encode(clean)]
    coarse_centers = mel_centers(coarse.profile.n_bands, fs)
    main_centers = mel_centers(main_bands, fs)
    n = len(received)
    for k in range(n):
        if received[k] is None and k + 1 < n and present[k + 1] and k < len(coarse_params):
            cp = coarse_params[k]
            shape = np.interp(main_centers, coarse_centers, cp.shape)
            received[k] = FrameParams(voiced=cp.voiced, f0=cp.f0, gain=cp.gain, shape=shape)
    return received


def run_pipeline(clean: np.ndarray, config: PipelineConfig,
                 cond: MeshCondition | str, seed: int = 0) -> PipelineResult:
    cond = condition(cond) if isinstance(cond, str) else cond
    codec = ParametricCodec(config.bitrate, aperiodicity=config.aperiodicity)
    profile = codec.profile
    packets = codec.encode(clean)
    params = [unpack(p, profile) for p in packets]
    n = len(packets)

    trace: DeliveryTrace = MeshChannel(cond).simulate(n, seed)
    jb = (AdaptiveJitterBuffer() if config.jitter_buffer == "adaptive"
          else FixedJitterBuffer(config.fixed_target_ms))
    playout = jb.process(trace)
    present = playout.present

    received: List[Optional[object]] = [params[k] if present[k] else None for k in range(n)]
    effective_bitrate = profile.bitrate_bps
    if config.fec:
        received = _apply_fec(received, present, clean, config.aperiodicity, profile.n_bands, codec.fs)
        effective_bitrate += 3200

    stream = make_plc(config.plc).conceal(received)

    synth = Synthesizer(profile, aperiodicity=config.aperiodicity)
    audio = np.concatenate([synth.render(s) for s in stream]).astype(np.float32) if stream else np.zeros(0, np.float32)

    return PipelineResult(
        audio=audio,
        effective_bitrate_bps=effective_bitrate,
        channel_loss=trace.loss_rate,
        present_rate=float(np.mean(present)),
        concealed_frames=int(np.sum(~present)),
        mean_latency_ms=playout.mean_delay_ms,
        condition_name=cond.name,
        config=config,
    )
