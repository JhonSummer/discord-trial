"""A low-bitrate parametric speech codec — an honest, pluggable stand-in for Lyra.

Google's Lyra is a *neural* codec (a generative decoder over learned features) that needs a
Bazel/TensorFlow-Lite build plus trained weights, none of which can be built in this sandbox.
This module implements a classical **harmonic + noise** parametric coder at the same operating
points (3.2 / 6.0 / 9.2 kbps, 20 ms frames) so the mesh voice path can be exercised end to end
on real audio today. Like Lyra it transmits a compact per-frame *parameterization* (pitch,
voicing, a mel spectral envelope and a gain) rather than a waveform, so:

* bitrate genuinely trades against quality — the envelope is scalar-quantized to the per-frame
  byte budget, so 3.2 kbps is audibly coarser than 9.2 kbps; and
* packet loss is concealable by *extrapolating parameters* (continue the pitch, decay the gain)
  which is exactly what a strong PLC does — see ``plc.py``.

``Codec`` is a tiny Protocol; drop in a real Lyra binding by implementing ``encode``/``decode``
with the same 20 ms framing and this whole harness (channel, jitter buffer, PLC, metrics, gate)
applies unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Sequence

import numpy as np

from . import FRAME_LEN, SAMPLE_RATE
from .dsp import cepstral_envelope, estimate_pitch, lpc_envelope, mel_centers

_F0_LOG_MIN = np.log(55.0)
_F0_LOG_MAX = np.log(400.0)
_GAIN_LOG_MIN = -9.5   # ~ -82 dBFS RMS
_GAIN_LOG_MAX = 0.0    # 0 dBFS RMS
_SHAPE_RANGE = 6.0     # mean-removed log-envelope swing (±)
_KMAX = 160            # harmonics ceiling (covers F0 down to 50 Hz at 16 kHz)


@dataclass(frozen=True)
class CodecProfile:
    name: str
    bitrate_bps: int
    n_bands: int
    shape_bits: int
    gain_bits: int = 6
    f0_bits: int = 7
    frame_ms: float = 20.0

    @property
    def payload_bytes(self) -> int:
        return int(round(self.bitrate_bps * self.frame_ms / 1000.0 / 8.0))

    @property
    def param_bits(self) -> int:
        return 1 + self.f0_bits + self.gain_bits + self.n_bands * self.shape_bits

    def __post_init__(self) -> None:
        if self.param_bits > self.payload_bytes * 8:
            raise ValueError(
                f"{self.name}: param bits {self.param_bits} exceed payload "
                f"{self.payload_bytes * 8} bits"
            )


PROFILES = {
    "3.2k": CodecProfile("lyraq_3.2k", 3200, n_bands=16, shape_bits=3, gain_bits=6),
    "6.0k": CodecProfile("lyraq_6.0k", 6000, n_bands=24, shape_bits=4, gain_bits=6),
    "9.2k": CodecProfile("lyraq_9.2k", 9200, n_bands=32, shape_bits=5, gain_bits=7),
}
BITRATES = {"3.2k": 3200, "6.0k": 6000, "9.2k": 9200}


def profile_for(bitrate: str | int) -> CodecProfile:
    if isinstance(bitrate, int):
        inv = {v: k for k, v in BITRATES.items()}
        bitrate = inv.get(bitrate, str(bitrate))
    if bitrate not in PROFILES:
        raise KeyError(f"unknown bitrate {bitrate!r}; known: {sorted(PROFILES)}")
    return PROFILES[bitrate]


@dataclass
class FrameParams:
    """One 20 ms frame's coded parameters (dequantized)."""

    voiced: bool
    f0: float
    gain: float                 # log-RMS
    shape: np.ndarray           # mean-removed log spectral envelope at the profile mel centres


# ------------------------------------------------------------------------------------------
# Bit packing
# ------------------------------------------------------------------------------------------
class _BitWriter:
    def __init__(self) -> None:
        self.bits: List[int] = []

    def put(self, value: int, nbits: int) -> None:
        value = int(value) & ((1 << nbits) - 1)
        for i in range(nbits - 1, -1, -1):
            self.bits.append((value >> i) & 1)

    def bytes(self, n_bytes: int) -> bytes:
        bits = self.bits + [0] * (n_bytes * 8 - len(self.bits))
        out = bytearray(n_bytes)
        for i, b in enumerate(bits[: n_bytes * 8]):
            out[i // 8] |= b << (7 - (i % 8))
        return bytes(out)


class _BitReader:
    def __init__(self, data: bytes) -> None:
        self.bits = [(byte >> (7 - i)) & 1 for byte in data for i in range(8)]
        self.pos = 0

    def get(self, nbits: int) -> int:
        v = 0
        for _ in range(nbits):
            v = (v << 1) | self.bits[self.pos]
            self.pos += 1
        return v


def _quant(value: float, lo: float, hi: float, bits: int) -> int:
    levels = (1 << bits) - 1
    t = (float(value) - lo) / (hi - lo)
    return int(round(np.clip(t, 0.0, 1.0) * levels))


def _dequant(index: int, lo: float, hi: float, bits: int) -> float:
    levels = (1 << bits) - 1
    return lo + (index / levels) * (hi - lo)


def pack(params: FrameParams, profile: CodecProfile) -> bytes:
    w = _BitWriter()
    w.put(1 if params.voiced else 0, 1)
    f0 = params.f0 if params.voiced and params.f0 > 0 else 55.0
    w.put(_quant(np.log(f0), _F0_LOG_MIN, _F0_LOG_MAX, profile.f0_bits), profile.f0_bits)
    w.put(_quant(params.gain, _GAIN_LOG_MIN, _GAIN_LOG_MAX, profile.gain_bits), profile.gain_bits)
    for s in params.shape[: profile.n_bands]:
        w.put(_quant(s, -_SHAPE_RANGE, _SHAPE_RANGE, profile.shape_bits), profile.shape_bits)
    return w.bytes(profile.payload_bytes)


def unpack(data: bytes, profile: CodecProfile) -> FrameParams:
    r = _BitReader(data)
    voiced = bool(r.get(1))
    f0 = float(np.exp(_dequant(r.get(profile.f0_bits), _F0_LOG_MIN, _F0_LOG_MAX, profile.f0_bits)))
    gain = _dequant(r.get(profile.gain_bits), _GAIN_LOG_MIN, _GAIN_LOG_MAX, profile.gain_bits)
    shape = np.array(
        [_dequant(r.get(profile.shape_bits), -_SHAPE_RANGE, _SHAPE_RANGE, profile.shape_bits)
         for _ in range(profile.n_bands)]
    )
    return FrameParams(voiced=voiced, f0=f0 if voiced else 0.0, gain=gain, shape=shape)


# ------------------------------------------------------------------------------------------
# Analysis
# ------------------------------------------------------------------------------------------
_ANALYSIS_WIN = 640  # 40 ms centred window: long enough for robust YIN pitch at F0_MIN
_LPC_ORDER = 18      # all-pole envelope order at 16 kHz (~9 formant pairs)


def _analyze(window: np.ndarray, frame: np.ndarray, profile: CodecProfile, fs: int,
             envelope: str = "lpc") -> FrameParams:
    """Analyze a centred ``window`` (pitch + envelope) but take the gain from the exact frame.

    Pitch and the spectral envelope want context (a longer window), while the gain must track
    the 20 ms frame's energy so the reconstructed temporal envelope stays tight.
    """
    centers = mel_centers(profile.n_bands, fs)
    f0, _ = estimate_pitch(window, fs)
    if envelope == "cepstral":
        freqs, log_env = cepstral_envelope(window, fs, n_fft=1024)
        env = np.interp(centers, freqs, log_env)
    else:
        env = lpc_envelope(window, fs, _LPC_ORDER, centers)
    shape = env - env.mean()
    rms = float(np.sqrt(np.mean(np.asarray(frame, dtype=np.float64) ** 2) + 1e-12))
    gain = float(np.clip(np.log(rms + 1e-9), _GAIN_LOG_MIN, _GAIN_LOG_MAX))
    return FrameParams(voiced=f0 > 0, f0=f0, gain=gain, shape=shape)


def analyze_frame(frame: np.ndarray, profile: CodecProfile, fs: int) -> FrameParams:
    return _analyze(frame, frame, profile, fs)


# ------------------------------------------------------------------------------------------
# Synthesis (stateful decoder) — phase-continuous harmonic + shaped-noise, with concealment
# ------------------------------------------------------------------------------------------
class Synthesizer:
    """Turns a stream of (possibly missing) frames into audio with phase continuity.

    ``conceal`` is an optional callable ``(history, gap_index) -> FrameParams | None`` invoked
    for every missing frame; returning ``None`` yields silence (the baseline). The PLC module
    supplies the clever version. Keeping concealment here means the synthesizer's internal
    phase/gain state is available to it, which is what makes extrapolation sound continuous.
    """

    def __init__(self, profile: CodecProfile, fs: int = SAMPLE_RATE,
                 aperiodicity: float = 0.08, aperiodic_hp_hz: float = 2500.0):
        self.profile = profile
        self.fs = fs
        self.hop = int(round(fs * profile.frame_ms / 1000.0))
        self.centers = mel_centers(profile.n_bands, fs)
        self._aperiodicity = aperiodicity
        self._aperiodic_hp = aperiodic_hp_hz
        self.reset()

    def reset(self) -> None:
        self._phase = np.zeros(_KMAX)
        self._prev: Optional[FrameParams] = None
        self._prev_amps = np.zeros(_KMAX)
        self._rng = np.random.default_rng(1234)
        self.history: List[FrameParams] = []

    def _amps(self, p: FrameParams) -> np.ndarray:
        amps = np.zeros(_KMAX)
        if not p.voiced or p.f0 <= 0:
            return amps
        k = np.arange(1, _KMAX + 1)
        freqs = k * p.f0
        valid = freqs < (self.fs / 2.0 - 50.0)
        logs = np.interp(freqs[valid], self.centers, p.shape)
        amps[valid] = np.exp(logs)
        return amps

    def _shaped_noise(self, shape: np.ndarray, hp_hz: float = 0.0) -> np.ndarray:
        """Random-phase noise shaped to a spectral envelope, optionally high-passed."""
        hop = self.hop
        nfft = 1
        while nfft < hop:
            nfft <<= 1
        N = np.fft.rfft(self._rng.standard_normal(nfft))
        freqs = np.fft.rfftfreq(nfft, 1.0 / self.fs)
        target = np.exp(np.interp(freqs, self.centers, shape))
        if hp_hz > 0:
            target = target * np.clip((freqs - hp_hz) / hp_hz, 0.0, 1.0)
        return np.fft.irfft(target * np.exp(1j * np.angle(N)), n=nfft)[:hop]

    def _render_voiced(self, prev: Optional[FrameParams], cur: FrameParams) -> np.ndarray:
        hop = self.hop
        n = np.arange(hop)
        f0_prev = prev.f0 if (prev and prev.voiced and prev.f0 > 0) else cur.f0
        f0_t = f0_prev + (cur.f0 - f0_prev) * (n / hop)
        cur_amps = self._amps(cur)
        prev_amps = self._prev_amps if (prev and prev.voiced) else np.zeros(_KMAX)
        out = np.zeros(hop)
        k = np.arange(1, _KMAX + 1)
        active = np.where((cur_amps > 0) | (prev_amps > 0))[0]
        for ki in active:
            inst = 2.0 * np.pi * (k[ki] * f0_t) / self.fs
            phase = self._phase[ki] + np.cumsum(inst)
            amp_t = prev_amps[ki] + (cur_amps[ki] - prev_amps[ki]) * (n / hop)
            out += amp_t * np.sin(phase)
            self._phase[ki] = (self._phase[ki] + float(np.sum(inst))) % (2.0 * np.pi)
        self._prev_amps = cur_amps
        # Mixed excitation: real voiced speech is not a pure buzz — a touch of high-band
        # aperiodic (breath) noise removes the robotic quality and lifts neural-MOS naturalness.
        harm_rms = float(np.sqrt(np.mean(out * out) + 1e-12))
        if harm_rms > 0:
            noise = self._shaped_noise(cur.shape, hp_hz=self._aperiodic_hp)
            noise *= (self._aperiodicity * harm_rms) / (np.sqrt(np.mean(noise * noise) + 1e-12))
            out = out + noise
        return out

    def _render_unvoiced(self, cur: FrameParams) -> np.ndarray:
        self._prev_amps = np.zeros(_KMAX)
        return self._shaped_noise(cur.shape)

    def render(self, cur: Optional[FrameParams]) -> np.ndarray:
        """Render one frame (``None`` = silence) and advance state."""
        hop = self.hop
        if cur is None:
            self._prev = None
            self._prev_amps = np.zeros(_KMAX)
            return np.zeros(hop, dtype=np.float32)

        prev = self._prev
        prev_v = 1.0 if (prev and prev.voiced) else 0.0
        cur_v = 1.0 if cur.voiced else 0.0

        voiced_sig = self._render_voiced(prev, cur) if (cur_v or prev_v) else np.zeros(hop)
        unvoiced_sig = self._render_unvoiced(cur) if (cur_v < 1.0 or prev_v < 1.0) else np.zeros(hop)

        n = np.arange(hop)
        v_t = prev_v + (cur_v - prev_v) * (n / hop)
        mix = v_t * voiced_sig + (1.0 - v_t) * unvoiced_sig

        raw_rms = float(np.sqrt(np.mean(mix * mix) + 1e-12))
        target_rms = float(np.exp(cur.gain))
        mix *= target_rms / (raw_rms + 1e-9)

        self._prev = cur
        self.history.append(cur)
        return mix.astype(np.float32)


# ------------------------------------------------------------------------------------------
# Codec facade
# ------------------------------------------------------------------------------------------
class Codec(Protocol):
    profile: CodecProfile

    def encode(self, signal: np.ndarray) -> List[bytes]: ...
    def decode(self, packets: Sequence[Optional[bytes]]) -> np.ndarray: ...


class ParametricCodec:
    """Harmonic+noise parametric codec at a given profile (the default Lyra stand-in)."""

    def __init__(self, profile: CodecProfile | str = "6.0k", fs: int = SAMPLE_RATE,
                 envelope: str = "cepstral", aperiodicity: float = 0.08, aperiodic_hp_hz: float = 2500.0):
        self.profile = profile if isinstance(profile, CodecProfile) else profile_for(profile)
        self.fs = fs
        self.hop = FRAME_LEN
        self.envelope = envelope
        self.aperiodicity = aperiodicity
        self.aperiodic_hp_hz = aperiodic_hp_hz

    def frames(self, signal: np.ndarray) -> List[np.ndarray]:
        x = np.asarray(signal, dtype=np.float64)
        n = int(np.ceil(len(x) / self.hop))
        x = np.pad(x, (0, n * self.hop - len(x)))
        return [x[i * self.hop:(i + 1) * self.hop] for i in range(n)]

    def encode_params(self, signal: np.ndarray) -> List[FrameParams]:
        x = np.asarray(signal, dtype=np.float64)
        n = int(np.ceil(len(x) / self.hop))
        x = np.pad(x, (0, n * self.hop - len(x)))
        half = _ANALYSIS_WIN // 2
        xpad = np.pad(x, (half, half))
        params: List[FrameParams] = []
        for i in range(n):
            frame = x[i * self.hop:(i + 1) * self.hop]
            c = i * self.hop + self.hop // 2 + half
            window = xpad[c - half:c + half]
            params.append(_analyze(window, frame, self.profile, self.fs, self.envelope))
        return params

    def encode(self, signal: np.ndarray) -> List[bytes]:
        return [pack(p, self.profile) for p in self.encode_params(signal)]

    def decode(self, packets: Sequence[Optional[bytes]]) -> np.ndarray:
        synth = Synthesizer(self.profile, self.fs, self.aperiodicity, self.aperiodic_hp_hz)
        out = [synth.render(unpack(p, self.profile) if p is not None else None) for p in packets]
        return np.concatenate(out).astype(np.float32) if out else np.zeros(0, np.float32)
