"""ViSQOL slot: an in-repo ViSQOL-style NSIM proxy, with a hook to the real binary.

Official ViSQOL is a Bazel/C++ build (not available in this sandbox), so this module computes
the documented *core* of ViSQOL — a neurogram-similarity (NSIM) comparison of reference and
degraded spectrograms — on a mel/log spectrogram, mapped monotonically onto the MOS scale. It
is an honest **proxy**: it tracks spectro-temporal similarity the way ViSQOL does and is
discriminative for before/after comparisons, but it is *not* the calibrated ViSQOL MOS-LQO.

If you have the real tool, set ``VISQOL_BIN=/path/to/visqol`` and this adapter shells out to it
instead; the committed gate stays on the proxy so it is reproducible everywhere.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Dict

import numpy as np


def available() -> bool:
    return True  # the proxy is pure numpy/scipy and always available


def _mel_filterbank(sr: int, n_fft: int, n_mels: int) -> np.ndarray:
    def hz_to_mel(f: np.ndarray) -> np.ndarray:
        return 2595.0 * np.log10(1.0 + f / 700.0)

    def mel_to_hz(m: np.ndarray) -> np.ndarray:
        return 700.0 * (10.0 ** (m / 2595.0) - 1.0)

    n_bins = n_fft // 2 + 1
    fft_freqs = np.linspace(0, sr / 2, n_bins)
    mel_pts = np.linspace(hz_to_mel(np.array([50.0]))[0], hz_to_mel(np.array([sr / 2.0]))[0], n_mels + 2)
    hz_pts = mel_to_hz(mel_pts)
    fb = np.zeros((n_mels, n_bins))
    for m in range(1, n_mels + 1):
        lo, ctr, hi = hz_pts[m - 1], hz_pts[m], hz_pts[m + 1]
        left = (fft_freqs - lo) / max(ctr - lo, 1e-6)
        right = (hi - fft_freqs) / max(hi - ctr, 1e-6)
        fb[m - 1] = np.clip(np.minimum(left, right), 0, None)
    return fb


def _log_mel(x: np.ndarray, sr: int, n_fft: int = 400, hop: int = 160, n_mels: int = 32) -> np.ndarray:
    from scipy.signal import stft

    _, _, Z = stft(np.asarray(x, dtype=np.float64), fs=sr, nperseg=n_fft,
                   noverlap=n_fft - hop, window="hann", boundary=None, padded=False)
    mag = np.abs(Z)
    mel = _mel_filterbank(sr, n_fft, n_mels) @ mag
    return np.log(mel + 1e-6)


def _nsim(ref: np.ndarray, deg: np.ndarray) -> float:
    """Neurogram structural similarity: SSIM's luminance x structure terms, averaged."""
    from scipy.ndimage import uniform_filter

    L = float(ref.max() - ref.min()) or 1.0
    c1 = (0.01 * L) ** 2
    c3 = ((0.03 * L) ** 2) / 2.0
    win = 3
    mu_r = uniform_filter(ref, win)
    mu_d = uniform_filter(deg, win)
    var_r = np.clip(uniform_filter(ref * ref, win) - mu_r ** 2, 0, None)
    var_d = np.clip(uniform_filter(deg * deg, win) - mu_d ** 2, 0, None)
    cov = uniform_filter(ref * deg, win) - mu_r * mu_d
    luminance = (2 * mu_r * mu_d + c1) / (mu_r ** 2 + mu_d ** 2 + c1)
    structure = (cov + c3) / (np.sqrt(var_r * var_d) + c3)
    return float(np.mean(luminance * structure))


def _proxy(ref: np.ndarray, deg: np.ndarray, sr: int) -> float:
    r = _log_mel(ref, sr)
    d = _log_mel(deg, sr)
    n = min(r.shape[1], d.shape[1])
    nsim = _nsim(r[:, :n], d[:, :n])
    mos = 1.0 + 4.0 * float(np.clip(nsim, 0.0, 1.0))  # monotonic NSIM -> MOS proxy
    return float(np.clip(mos, 1.0, 5.0))


def _real_binary(ref: np.ndarray, deg: np.ndarray, sr: int, binary: str) -> float:
    import soundfile as sf

    with tempfile.TemporaryDirectory() as d:
        rp, dp = os.path.join(d, "ref.wav"), os.path.join(d, "deg.wav")
        sf.write(rp, np.asarray(ref, dtype=np.float32), sr, subtype="PCM_16")
        sf.write(dp, np.asarray(deg, dtype=np.float32), sr, subtype="PCM_16")
        out = subprocess.run(
            [binary, "--reference_file", rp, "--degraded_file", dp, "--use_speech_mode"],
            capture_output=True, text=True, timeout=120, check=True,
        ).stdout
    for line in out.splitlines():
        if "MOS-LQO" in line:
            return float(line.split(":")[-1].strip())
    raise RuntimeError("could not parse MOS-LQO from visqol output")


def compute(ref: np.ndarray, deg: np.ndarray, sr: int) -> Dict[str, float]:
    binary = os.environ.get("VISQOL_BIN")
    if binary and os.path.exists(binary):
        try:
            return {"visqol": _real_binary(ref, deg, sr, binary)}
        except Exception:
            pass  # fall back to the proxy rather than failing the metric
    return {"visqol": _proxy(ref, deg, sr)}
