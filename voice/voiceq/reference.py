"""Deterministic clean-speech reference, synthesized in-process.

Why synth and not a recording? A committed quality gate has to be byte-reproducible and must
not reach the network or vendor an opaque audio blob, so we build the reference from a
source-filter (formant) model: a glottal/noise excitation driven through a time-varying
cascade of formant resonators, with coarticulated formant transitions, an F0 contour with
jitter/shimmer, and phrase-level prosody. The result is connected, intelligible pseudo-speech
with a natural spectral balance — enough structure for STOI/PESQ (full-reference) and for the
neural MOS predictors (no-reference) to behave like they do on real speech.

``clean_reference()`` is pure and deterministic for a given seed. Callers that want to score
against *real* speech can hand any 16 kHz WAV to the pipeline instead; this is the default so
the gate stands on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np
from scipy.signal import lfilter

from . import SAMPLE_RATE


@dataclass(frozen=True)
class Phone:
    """One speech sound: formant targets (Hz), bandwidths (Hz), and voicing/noise mix."""

    name: str
    formants: Tuple[float, ...]
    bandwidths: Tuple[float, ...]
    voicing: float  # 0 = voiceless, 1 = fully voiced
    noise: float    # fricative/aspiration noise gain
    kind: str = "vowel"  # vowel | sonorant | fricative | stop | silence


# A compact male-speaker inventory (formant centres in Hz). Values follow the usual
# Peterson-Barney / Klatt neighbourhoods; exact Hz matter far less than smooth transitions.
_V = lambda n, f1, f2, f3: Phone(n, (f1, f2, f3, 3500.0), (80, 90, 120, 180), 1.0, 0.0, "vowel")
INVENTORY: Dict[str, Phone] = {
    "a": _V("a", 730, 1090, 2440),
    "e": _V("e", 530, 1840, 2480),
    "i": _V("i", 270, 2290, 3010),
    "o": _V("o", 570, 840, 2410),
    "u": _V("u", 300, 870, 2240),
    "schwa": _V("schwa", 500, 1500, 2500),
    "ae": _V("ae", 660, 1720, 2410),
    "l": Phone("l", (360, 1300, 2400, 3400), (60, 90, 120, 180), 1.0, 0.0, "sonorant"),
    "r": Phone("r", (320, 1100, 1600, 3300), (70, 100, 140, 200), 1.0, 0.0, "sonorant"),
    "m": Phone("m", (280, 1000, 2200, 3200), (60, 110, 160, 220), 1.0, 0.0, "sonorant"),
    "n": Phone("n", (280, 1700, 2600, 3400), (60, 110, 160, 220), 1.0, 0.0, "sonorant"),
    "w": Phone("w", (300, 820, 2200, 3200), (70, 100, 140, 200), 1.0, 0.0, "sonorant"),
    "z": Phone("z", (320, 1400, 2500, 5200), (120, 200, 300, 1200), 0.6, 0.9, "fricative"),
    "v": Phone("v", (350, 1100, 2200, 4200), (120, 200, 300, 1000), 0.6, 0.7, "fricative"),
    "s": Phone("s", (500, 1500, 4200, 6500), (200, 400, 900, 1400), 0.0, 1.0, "fricative"),
    "sh": Phone("sh", (500, 1600, 2600, 4000), (200, 400, 700, 1200), 0.0, 1.0, "fricative"),
    "f": Phone("f", (400, 1200, 2400, 5000), (200, 400, 800, 1600), 0.0, 0.9, "fricative"),
    "t": Phone("t", (400, 1600, 3000, 6000), (300, 600, 1000, 1600), 0.0, 1.0, "stop"),
    "d": Phone("d", (350, 1600, 2600, 4200), (120, 300, 500, 1000), 0.7, 0.8, "stop"),
    "k": Phone("k", (450, 1800, 2400, 5000), (300, 600, 1000, 1600), 0.0, 1.0, "stop"),
    "p": Phone("p", (400, 1100, 2200, 4000), (300, 600, 1000, 1600), 0.0, 0.9, "stop"),
    "b": Phone("b", (350, 1100, 2200, 3600), (120, 300, 500, 900), 0.7, 0.6, "stop"),
    "sil": Phone("sil", (500, 1500, 2500, 3500), (100, 120, 160, 200), 0.0, 0.0, "silence"),
}

# Phrases chosen for broad phonetic coverage (vowels, sonorants, fricatives, stops, pauses).
_PHRASES: Tuple[Tuple[str, ...], ...] = (
    ("sil", "w", "i", "sh", "u", "d", "a", "l", "w", "e", "z", "sil",
     "k", "i", "p", "o", "u", "r", "v", "o", "i", "s", "sil"),
    ("sil", "t", "e", "l", "schwa", "m", "i", "sil", "a", "n", "d", "sil",
     "l", "i", "s", "schwa", "n", "sil"),
    ("sil", "s", "e", "n", "d", "ae", "sil", "sh", "o", "r", "t", "sil",
     "m", "e", "s", "ae", "sh", "sil"),
)


@dataclass
class _Timing:
    vowel_ms: float = 150.0
    sonorant_ms: float = 95.0
    fricative_ms: float = 110.0
    stop_ms: float = 70.0
    silence_ms: float = 110.0
    transition_ms: float = 45.0

    def duration(self, phone: Phone) -> float:
        return {
            "vowel": self.vowel_ms,
            "sonorant": self.sonorant_ms,
            "fricative": self.fricative_ms,
            "stop": self.stop_ms,
            "silence": self.silence_ms,
        }[phone.kind]


def _resonator(f: float, bw: float, fs: int) -> Tuple[float, Tuple[float, float, float]]:
    """Klatt second-order resonator coefficients for centre ``f`` / bandwidth ``bw``."""
    r = np.exp(-np.pi * bw / fs)
    theta = 2.0 * np.pi * f / fs
    b1 = 2.0 * r * np.cos(theta)
    c1 = -(r * r)
    a0 = 1.0 - b1 - c1
    return a0, (1.0, -b1, -c1)


def _apply_formant_cascade(
    src: np.ndarray, formants: np.ndarray, bandwidths: np.ndarray, fs: int, block: int = 32
) -> np.ndarray:
    """Time-varying cascade of formant resonators, filter state carried across blocks."""
    n, n_formants = formants.shape
    y = src.astype(np.float64)
    for k in range(n_formants):
        out = np.empty(n, dtype=np.float64)
        zi = np.zeros(2, dtype=np.float64)
        for s in range(0, n, block):
            e = min(n, s + block)
            f = float(np.mean(formants[s:e, k]))
            bw = float(np.mean(bandwidths[s:e, k]))
            a0, a = _resonator(f, bw, fs)
            seg, zi = lfilter([a0], a, y[s:e], zi=zi)
            out[s:e] = seg
        y = out
    return y


def _f0_contour(n: int, fs: int, base_hz: float, rng: np.random.Generator) -> np.ndarray:
    """Declining phrase pitch with vibrato, micro-jitter and a final fall."""
    t = np.arange(n) / fs
    dur = max(t[-1], 1e-6)
    declination = base_hz * (1.0 - 0.18 * (t / dur))
    vibrato = 1.0 + 0.015 * np.sin(2.0 * np.pi * 4.7 * t)
    jitter = 1.0 + 0.01 * rng.standard_normal(n).cumsum() / np.sqrt(np.arange(1, n + 1))
    final_fall = 1.0 - 0.12 * np.clip((t - 0.85 * dur) / (0.15 * dur), 0, 1)
    return declination * vibrato * jitter * final_fall


def _glottal_excitation(f0: np.ndarray, fs: int, rng: np.random.Generator) -> np.ndarray:
    """Impulse train at F0 with jitter/shimmer, shaped to a speech-like -12 dB/oct tilt."""
    n = len(f0)
    exc = np.zeros(n, dtype=np.float64)
    phase = 0.0
    for i in range(n):
        phase += f0[i] / fs * (1.0 + 0.012 * rng.standard_normal())  # period jitter
        if phase >= 1.0:
            phase -= 1.0
            exc[i] = 1.0 + 0.06 * rng.standard_normal()  # shimmer
    # One-pole low-pass approximates the glottal-flow spectral tilt before the vocal tract.
    exc = lfilter([1.0], [1.0, -0.97], exc)
    return exc


def _raised_cosine_env(length: int, ramp: int) -> np.ndarray:
    env = np.ones(length, dtype=np.float64)
    ramp = max(1, min(ramp, length // 2))
    w = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, ramp))
    env[:ramp] = w
    env[-ramp:] = w[::-1]
    return env


def _build_tracks(
    phones: Sequence[Phone], timing: _Timing, fs: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per-sample formant/bandwidth tracks plus voicing and noise envelopes (coarticulated)."""
    seg_lens = [max(1, int(round(timing.duration(p) / 1000.0 * fs))) for p in phones]
    total = sum(seg_lens)
    n_formants = len(phones[0].formants)
    formants = np.zeros((total, n_formants))
    bandwidths = np.zeros((total, n_formants))
    voicing = np.zeros(total)
    noise = np.zeros(total)

    # Piecewise-linear interpolation of formant targets across segment centres gives the
    # transitions that make connected speech (and the cues the metrics key on).
    centres = []
    pos = 0
    for ln in seg_lens:
        centres.append(pos + ln / 2.0)
        pos += ln
    centres = np.array(centres)
    idx = np.arange(total)
    for k in range(n_formants):
        fvals = np.array([p.formants[k] for p in phones])
        bvals = np.array([p.bandwidths[k] for p in phones])
        formants[:, k] = np.interp(idx, centres, fvals)
        bandwidths[:, k] = np.interp(idx, centres, bvals)

    ramp = max(1, int(round(timing.transition_ms / 1000.0 * fs)))
    pos = 0
    for p, ln in zip(phones, seg_lens):
        env = _raised_cosine_env(ln, ramp)
        voicing[pos:pos + ln] = p.voicing * env
        noise[pos:pos + ln] = p.noise * env
        pos += ln
    return formants, bandwidths, voicing, noise


def synthesize(
    phrases: Sequence[Sequence[str]] = _PHRASES,
    *,
    fs: int = SAMPLE_RATE,
    base_f0: float = 118.0,
    seed: int = 20240921,
    timing: _Timing | None = None,
) -> np.ndarray:
    """Render phrases (sequences of inventory keys) into one connected speech waveform."""
    timing = timing or _Timing()
    rng = np.random.default_rng(seed)
    pieces: List[np.ndarray] = []
    gap = np.zeros(int(round(0.18 * fs)), dtype=np.float64)  # inter-phrase silence

    for pi, phrase in enumerate(phrases):
        phones = [INVENTORY[k] for k in phrase]
        formants, bandwidths, voicing, noise = _build_tracks(phones, timing, fs)
        n = formants.shape[0]
        f0 = _f0_contour(n, fs, base_f0 * (1.0 + 0.04 * pi), rng)

        voiced_src = _glottal_excitation(f0, fs, rng) * voicing
        noise_src = rng.standard_normal(n) * noise * 0.5
        src = voiced_src + noise_src

        shaped = _apply_formant_cascade(src, formants, bandwidths, fs)
        shaped = lfilter([1.0, -0.97], [1.0], shaped)  # lip-radiation (+6 dB/oct)

        peak = np.max(np.abs(shaped)) + 1e-9
        pieces.append((shaped / peak).astype(np.float64))
        pieces.append(gap)

    out = np.concatenate(pieces).astype(np.float32)
    return out


def clean_reference(seed: int = 20240921, fs: int = SAMPLE_RATE) -> np.ndarray:
    """The default committed reference utterance (~5 s of connected speech at 16 kHz)."""
    from .audio import normalize_rms

    return normalize_rms(synthesize(fs=fs, seed=seed), target_dbfs=-23.0)
