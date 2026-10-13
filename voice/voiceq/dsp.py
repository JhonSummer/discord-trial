"""Low-level speech DSP shared by the codec and PLC: pitch, spectral envelope, mel grid."""

from __future__ import annotations

from typing import Tuple

import numpy as np

F0_MIN = 70.0
F0_MAX = 330.0
_YIN_THRESH = 0.20  # absolute threshold on the cumulative-mean-normalized difference


def mel_centers(n_bands: int, fs: int, fmin: float = 60.0, fmax: float | None = None) -> np.ndarray:
    """Centre frequencies (Hz) of ``n_bands`` mel-spaced bands — the spectral-envelope grid."""
    fmax = fmax if fmax is not None else fs / 2.0
    hz_to_mel = lambda f: 2595.0 * np.log10(1.0 + f / 700.0)
    mel_to_hz = lambda m: 700.0 * (10.0 ** (m / 2595.0) - 1.0)
    mels = np.linspace(hz_to_mel(fmin), hz_to_mel(fmax), n_bands)
    return mel_to_hz(mels)


def _difference_function(x: np.ndarray, tau_max: int) -> np.ndarray:
    """YIN difference function d(tau) computed via FFT autocorrelation (octave-robust base)."""
    n = len(x)
    # autocorrelation
    size = 1
    while size < 2 * n:
        size <<= 1
    X = np.fft.rfft(x, size)
    acf = np.fft.irfft(X * np.conj(X), size)[:tau_max + 1]
    cumsq = np.concatenate(([0.0], np.cumsum(x * x)))
    e1 = cumsq[n - np.arange(tau_max + 1)] - cumsq[0]        # energy of x[0 : n-tau]
    e2 = cumsq[n] - cumsq[np.arange(tau_max + 1)]            # energy of x[tau : n]
    return e1 + e2 - 2.0 * acf


def yin_pitch(frame: np.ndarray, fs: int, fmin: float = F0_MIN, fmax: float = F0_MAX) -> Tuple[float, float]:
    """YIN pitch: ``(f0_hz, voicing in [0,1])``; f0 is 0 when the frame is unvoiced.

    YIN's cumulative-mean normalization plus absolute-threshold search finds the *fundamental*
    (not a harmonic), which the plain autocorrelation peak-pick got wrong (octave-up errors).
    """
    x = np.asarray(frame, dtype=np.float64)
    x = x - x.mean()
    if np.sqrt(np.mean(x * x) + 1e-20) < 1e-5:
        return 0.0, 0.0
    tau_min = max(2, int(fs / fmax))
    tau_max = min(len(x) - 1, int(fs / fmin))
    if tau_max <= tau_min:
        return 0.0, 0.0
    d = _difference_function(x, tau_max)
    cmnd = np.ones_like(d)
    running = np.cumsum(d[1:])
    cmnd[1:] = d[1:] * np.arange(1, len(d)) / np.maximum(running, 1e-12)

    search = cmnd[tau_min:tau_max + 1]
    below = np.where(search < _YIN_THRESH)[0]
    if len(below):
        tau = int(below[0]) + tau_min
        # walk to the local minimum of the dip for a crisper estimate
        while tau + 1 <= tau_max and cmnd[tau + 1] < cmnd[tau]:
            tau += 1
    else:
        tau = int(np.argmin(search)) + tau_min
    # parabolic interpolation around tau for sub-sample precision
    if tau_min < tau < tau_max:
        a, b, c = cmnd[tau - 1], cmnd[tau], cmnd[tau + 1]
        denom = a + c - 2 * b
        if abs(denom) > 1e-12:
            tau = tau + 0.5 * (a - c) / denom
    strength = float(np.clip(1.0 - cmnd[int(round(tau))], 0.0, 1.0))
    if cmnd[int(round(tau))] > 0.55:  # too aperiodic -> unvoiced
        return 0.0, strength
    return float(fs / tau), strength


def estimate_pitch(frame: np.ndarray, fs: int) -> Tuple[float, float]:
    return yin_pitch(frame, fs)


def cepstral_envelope(frame: np.ndarray, fs: int, n_fft: int = 512, lifter_ms: float = 2.5) -> Tuple[np.ndarray, np.ndarray]:
    """Smooth log-magnitude spectral envelope via low-quefrency cepstral liftering.

    Returns ``(freqs_hz, log_env)`` over the rFFT grid. The lifter length sets how much formant
    detail survives (longer = more detail).
    """
    x = np.asarray(frame, dtype=np.float64)
    w = np.hanning(len(x))
    X = np.fft.rfft(x * w, n=n_fft)
    log_mag = np.log(np.abs(X) + 1e-7)
    cep = np.fft.irfft(log_mag, n=n_fft)
    quef = int(fs * lifter_ms / 1000.0)
    lifter = np.zeros_like(cep)
    lifter[0] = 1.0
    lifter[1:quef] = 2.0
    lifter[quef] = 1.0
    env = np.fft.rfft(cep * lifter, n=n_fft).real
    freqs = np.fft.rfftfreq(n_fft, 1.0 / fs)
    return freqs, env


def sample_envelope(freqs: np.ndarray, log_env: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Sample a log-envelope at the mel band centres."""
    return np.interp(centers, freqs, log_env)


def _levinson(r: np.ndarray, order: int) -> Tuple[np.ndarray, float]:
    """Levinson-Durbin recursion: autocorrelation -> LPC coefficients ``a`` (a[0]=1) and error."""
    a = np.zeros(order + 1)
    a[0] = 1.0
    e = float(r[0])
    if e <= 0:
        return a, 1e-6
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1]) if i > 1 else r[i]
        k = -acc / e
        a[1:i + 1] += k * a[i - 1::-1][: i]
        e *= (1.0 - k * k)
        if e <= 0:
            break
    return a, max(e, 1e-9)


def lpc_envelope(window: np.ndarray, fs: int, order: int, centers: np.ndarray) -> np.ndarray:
    """All-pole (LPC) log spectral envelope sampled at mel centres — sharper formants than cepstrum."""
    x = np.asarray(window, dtype=np.float64)
    x = (x - x.mean()) * np.hanning(len(x))
    full = np.correlate(x, x, mode="full")[len(x) - 1:]
    r = full[: order + 1].copy()
    r[0] *= 1.0 + 1e-4  # ridge for numerical stability
    a, e = _levinson(r, order)
    w = 2.0 * np.pi * centers / fs
    k = np.arange(order + 1)
    A = np.exp(-1j * np.outer(w, k)) @ a
    h = np.sqrt(e) / (np.abs(A) + 1e-9)
    return np.log(h + 1e-9)
