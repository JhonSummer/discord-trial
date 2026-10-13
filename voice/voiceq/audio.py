"""Audio plumbing: framing, overlap-add, levels, resampling and WAV I/O.

Everything downstream speaks one dialect: mono ``float32`` in [-1, 1] at 16 kHz (Lyra's
sample rate, and what every metric here expects). Keeping that invariant in one place means
the codec, channel and metric code never has to think about sample formats.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

from . import SAMPLE_RATE


def to_mono_float(x: np.ndarray) -> np.ndarray:
    """Coerce any shape/dtype into mono ``float32`` in [-1, 1]."""
    x = np.asarray(x)
    if x.ndim == 2:
        x = x.mean(axis=1)
    x = x.astype(np.float32, copy=False)
    if np.issubdtype(np.asarray(x).dtype, np.integer):  # pragma: no cover - defensive
        x = x / 32768.0
    return np.ascontiguousarray(x, dtype=np.float32)


def frame_signal(x: np.ndarray, frame_len: int, hop: int) -> np.ndarray:
    """Slice ``x`` into overlapping frames ``(n_frames, frame_len)``, zero-padding the tail."""
    if hop <= 0 or frame_len <= 0:
        raise ValueError("frame_len and hop must be positive")
    x = np.asarray(x, dtype=np.float32)
    if len(x) < frame_len:
        x = np.pad(x, (0, frame_len - len(x)))
    n = 1 + (len(x) - frame_len) // hop
    needed = (n - 1) * hop + frame_len
    if needed < len(x):
        n += 1
        needed = (n - 1) * hop + frame_len
    if needed > len(x):
        x = np.pad(x, (0, needed - len(x)))
    idx = np.arange(frame_len)[None, :] + hop * np.arange(n)[:, None]
    return x[idx]


def overlap_add(frames: np.ndarray, hop: int, window: np.ndarray | None = None) -> np.ndarray:
    """Reconstruct a signal from frames with constant-overlap-add (COLA) normalization."""
    frames = np.asarray(frames, dtype=np.float32)
    n, frame_len = frames.shape
    out_len = (n - 1) * hop + frame_len
    out = np.zeros(out_len, dtype=np.float64)
    norm = np.zeros(out_len, dtype=np.float64)
    w = np.ones(frame_len) if window is None else np.asarray(window, dtype=np.float64)
    for i in range(n):
        s = i * hop
        out[s:s + frame_len] += frames[i] * w
        norm[s:s + frame_len] += w
    norm[norm < 1e-8] = 1.0
    return (out / norm).astype(np.float32)


def rms(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x * x) + 1e-20))


def normalize_rms(x: np.ndarray, target_dbfs: float = -23.0) -> np.ndarray:
    """Scale to a target RMS level, then guard against clipping (broadcast-era loudness)."""
    x = np.asarray(x, dtype=np.float32)
    target = 10.0 ** (target_dbfs / 20.0)
    g = target / (rms(x) + 1e-12)
    y = x * g
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 0.99:
        y = y * (0.99 / peak)
    return y.astype(np.float32)


def align_lengths(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Trim two signals to a common length (metrics need sample-aligned ref/deg)."""
    n = min(len(a), len(b))
    return np.asarray(a[:n], dtype=np.float32), np.asarray(b[:n], dtype=np.float32)


def estimate_delay(ref: np.ndarray, deg: np.ndarray, max_lag: int) -> int:
    """Integer sample lag (deg relative to ref) maximizing cross-correlation within ±max_lag.

    The voice path adds a fixed algorithmic delay (analysis window + jitter-buffer target);
    full-reference metrics (STOI/PESQ/ViSQOL) collapse if ref and deg are not sample-aligned,
    so we recover that delay once and compensate it rather than letting it masquerade as
    quality loss.
    """
    from scipy.signal import fftconvolve

    ref = np.asarray(ref, dtype=np.float64)
    deg = np.asarray(deg, dtype=np.float64)
    ref = ref - ref.mean()
    deg = deg - deg.mean()
    corr = fftconvolve(deg, ref[::-1], mode="full")
    zero = len(ref) - 1  # index of lag 0
    lo = max(0, zero - max_lag)
    hi = min(len(corr), zero + max_lag + 1)
    best = int(np.argmax(corr[lo:hi])) + lo
    return best - zero


def align_to_reference(
    ref: np.ndarray, deg: np.ndarray, max_lag_ms: float = 120.0, sr: int = SAMPLE_RATE
) -> Tuple[np.ndarray, np.ndarray]:
    """Delay-compensate ``deg`` to ``ref`` and trim both to a common length."""
    max_lag = int(round(max_lag_ms / 1000.0 * sr))
    lag = estimate_delay(ref, deg, max_lag)
    deg = np.asarray(deg, dtype=np.float32)
    if lag > 0:
        deg = deg[lag:]
    elif lag < 0:
        deg = np.pad(deg, (-lag, 0))
    return align_lengths(np.asarray(ref, dtype=np.float32), deg)


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return np.asarray(x, dtype=np.float32)
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(sr_in, sr_out)
    y = resample_poly(np.asarray(x, dtype=np.float64), sr_out // g, sr_in // g)
    return y.astype(np.float32)


def write_wav(path: str, x: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    import soundfile as sf

    sf.write(path, np.asarray(x, dtype=np.float32), sr, subtype="PCM_16")


def read_wav(path: str) -> Tuple[np.ndarray, int]:
    import soundfile as sf

    x, sr = sf.read(path, dtype="float32", always_2d=False)
    return to_mono_float(x), int(sr)
