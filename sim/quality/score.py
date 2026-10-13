"""ViSQOL (speech), DNSMOS P.835, and STOI.

ViSQOL and STOI are intrusive (they see the clean reference). DNSMOS P.835 is
a neural MOS predictor and does not. DNSMOS follows the published non-personalized
polynomial in Microsoft's ``dnsmos_local.py`` (ICASSP 2022, arXiv:2110.01763)
against the official ``sig_bak_ovr.onnx`` graph. The graph is downloaded from
the DNS-Challenge repository and checked against a pinned sha256; it is not
committed here.
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from typing import Dict, Tuple

import numpy as np

DNSMOS_URL = (
    "https://github.com/microsoft/DNS-Challenge/raw/master/DNSMOS/DNSMOS/sig_bak_ovr.onnx"
)
DNSMOS_SHA256 = "269fbebdb513aa23cddfbb593542ecc540284a91849ac50516870e1ac78f6edd"
DNSMOS_INPUT_SECONDS = 9.01
SAMPLE_RATE = 16000

# np.poly1d coefficient order: highest degree first. Non-personalized P.835.
_POLY_SIG = (-0.08397278, 1.22083953, 0.0052439)
_POLY_BAK = (-0.13166888, 1.60915514, -0.39604546)
_POLY_OVR = (-0.06766283, 1.11546468, 0.04602535)

_dnsmos_session = None
_visqol_api = None


def _poly(coeffs: Tuple[float, ...], x: float) -> float:
    value = 0.0
    for coeff in coeffs:
        value = value * x + coeff
    return value


def dnsmos_model_path(cache_dir: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "sig_bak_ovr.onnx")
    if os.path.isfile(path):
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if digest != DNSMOS_SHA256:
            raise RuntimeError(f"DNSMOS model at {path} sha256 is {digest}, expected {DNSMOS_SHA256}")
        return path
    request = urllib.request.Request(DNSMOS_URL, headers={"User-Agent": "meshvoice-quality"})
    with urllib.request.urlopen(request, timeout=60) as response:
        blob = response.read()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != DNSMOS_SHA256:
        raise RuntimeError(f"downloaded DNSMOS model sha256 is {digest}, expected {DNSMOS_SHA256}")
    tmp = path + ".partial"
    with open(tmp, "wb") as fh:
        fh.write(blob)
    os.replace(tmp, path)
    return path


def _session(cache_dir: str):
    global _dnsmos_session
    if _dnsmos_session is None:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        _dnsmos_session = ort.InferenceSession(
            dnsmos_model_path(cache_dir),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
    return _dnsmos_session


def dnsmos_p835(samples: np.ndarray, cache_dir: str) -> Dict[str, float]:
    """Return SIG / BAK / OVRL for a 16 kHz mono waveform in [-1, 1]."""
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    if audio.size < int(DNSMOS_INPUT_SECONDS * SAMPLE_RATE):
        raise ValueError(
            f"DNSMOS P.835 wants at least {DNSMOS_INPUT_SECONDS} s; got {audio.size / SAMPLE_RATE:.2f} s"
        )
    session = _session(cache_dir)
    fs = SAMPLE_RATE
    length = int(DNSMOS_INPUT_SECONDS * fs)
    n_hops = int(np.floor(len(audio) / fs) - DNSMOS_INPUT_SECONDS) + 1
    if n_hops < 1:
        raise ValueError("DNSMOS hop count is zero")
    sig_raw, bak_raw, ovr_raw = [], [], []
    for idx in range(n_hops):
        seg = audio[idx * fs : int((idx + DNSMOS_INPUT_SECONDS) * fs)]
        if len(seg) < length:
            continue
        pred = session.run(None, {"input_1": seg.astype(np.float32)[np.newaxis, :]})[0][0]
        sig_raw.append(float(pred[0]))
        bak_raw.append(float(pred[1]))
        ovr_raw.append(float(pred[2]))
    if not ovr_raw:
        raise RuntimeError("DNSMOS produced no hops")
    sig = float(np.mean([_poly(_POLY_SIG, x) for x in sig_raw]))
    bak = float(np.mean([_poly(_POLY_BAK, x) for x in bak_raw]))
    ovr = float(np.mean([_poly(_POLY_OVR, x) for x in ovr_raw]))
    return {"dnsmos_sig": sig, "dnsmos_bak": bak, "dnsmos_ovrl": ovr, "dnsmos_hops": float(len(ovr_raw))}


def visqol_mos(reference: np.ndarray, degraded: np.ndarray) -> float:
    """Speech-mode ViSQOL MOS-LQO using the lattice mapper (C++ default)."""
    global _visqol_api
    if _visqol_api is None:
        from visqol import VisqolApi

        api = VisqolApi()
        api.create(mode="speech", use_lattice_model=True)
        _visqol_api = api
    result = _visqol_api.measure_from_arrays(
        np.asarray(reference, dtype=np.float64),
        np.asarray(degraded, dtype=np.float64),
        SAMPLE_RATE,
    )
    return float(result.moslqo)


def align_delay(reference: np.ndarray, degraded: np.ndarray, max_lag: int = 640) -> int:
    """Samples by which ``degraded`` lags ``reference`` (positive = degraded is late).

    Lyra's algorithmic delay is one 20 ms frame. STOI does not compensate delay
    on its own, so the intrusive score is computed after this shift. The search
    is limited to ±``max_lag`` (default ±40 ms) so concealment cannot invent a
    large alignment.
    """
    from scipy.signal import correlate, correlation_lags

    n = min(len(reference), len(degraded))
    # Copy: subtracting the mean must not rewrite the caller's waveform.
    ref = np.array(reference[:n], dtype=np.float64, copy=True)
    deg = np.array(degraded[:n], dtype=np.float64, copy=True)
    ref -= ref.mean()
    deg -= deg.mean()
    corr = correlate(deg, ref, mode="full", method="fft")
    lags = correlation_lags(len(deg), len(ref), mode="full")
    window = (lags >= -max_lag) & (lags <= max_lag)
    # correlate(deg, ref) peaks at how far deg lags ref. Positive means the
    # degraded waveform is late (Lyra's algorithmic delay is this sign).
    return int(lags[window][np.argmax(corr[window])])


def apply_delay(reference: np.ndarray, degraded: np.ndarray, delay: int) -> Tuple[np.ndarray, np.ndarray]:
    """Drop the unmatched edges so both arrays describe the same time span."""
    if delay > 0:
        ref = reference[: len(reference) - delay]
        deg = degraded[delay:]
    elif delay < 0:
        ref = reference[-delay:]
        deg = degraded[: len(degraded) + delay]
    else:
        ref, deg = reference, degraded
    n = min(len(ref), len(deg))
    if n <= 0:
        raise RuntimeError("delay alignment removed the whole signal")
    return ref[:n], deg[:n]


def stoi_score(reference: np.ndarray, degraded: np.ndarray) -> Tuple[float, int]:
    from pystoi import stoi

    delay = align_delay(reference, degraded)
    ref, deg = apply_delay(reference, degraded, delay)
    return float(stoi(ref, deg, SAMPLE_RATE, extended=False)), delay


def read_wav(path: str) -> np.ndarray:
    import soundfile as sf

    audio, sample_rate = sf.read(path, always_2d=False)
    if sample_rate != SAMPLE_RATE:
        raise RuntimeError(f"{path} sample rate is {sample_rate}, expected {SAMPLE_RATE}")
    audio = np.asarray(audio, dtype=np.float64)
    if audio.ndim != 1:
        raise RuntimeError(f"{path} is not mono")
    return audio


def score_pair(reference: np.ndarray, degraded: np.ndarray, cache_dir: str) -> Dict[str, float]:
    mos = visqol_mos(reference, degraded)
    dns = dnsmos_p835(degraded, cache_dir)
    intelligibility, lag = stoi_score(reference, degraded)
    return {
        "visqol_mos": mos,
        "dnsmos_sig": dns["dnsmos_sig"],
        "dnsmos_bak": dns["dnsmos_bak"],
        "dnsmos_ovrl": dns["dnsmos_ovrl"],
        "stoi": intelligibility,
        "stoi_lag_samples": float(lag),
    }
