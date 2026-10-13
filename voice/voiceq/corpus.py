"""Clean-reference speech: the vendored real-speech fixtures, with a synthetic fallback.

The committed gate scores against real human speech (``voice/assets/speech/*.wav``, see the
``ATTRIBUTION.md`` there) because the neural MOS predictors are trained on natural speech and
are not meaningful otherwise. ``reference.clean_reference()`` stays available for environments
that would rather not ship the fixtures, and for full-reference-only experiments.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List

import numpy as np

from . import SAMPLE_RATE
from .audio import normalize_rms, read_wav, resample

_ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "speech")

# Ordered so index 0 is the primary gate clip; the rest broaden speaker coverage for the bench.
SAMPLE_NAMES: List[str] = ["sample1", "sample2", "sample3"]


def _path(name: str) -> str:
    return os.path.join(_ASSET_DIR, f"{name}.wav")


def available() -> bool:
    return all(os.path.exists(_path(n)) for n in SAMPLE_NAMES)


@lru_cache(maxsize=None)
def load_sample(name: str, target_dbfs: float = -23.0) -> np.ndarray:
    """Load one vendored clip as mono float32 @16 kHz, RMS-normalized for consistent levels."""
    path = _path(name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"speech fixture {name!r} missing at {path}; run voice/tools/vendor_speech.py or "
            f"fall back to reference.clean_reference()"
        )
    x, sr = read_wav(path)
    if sr != SAMPLE_RATE:
        x = resample(x, sr, SAMPLE_RATE)
    return normalize_rms(x, target_dbfs)


def primary_reference() -> np.ndarray:
    """The single clip the fast committed gate runs on."""
    if available():
        return load_sample(SAMPLE_NAMES[0])
    from .reference import clean_reference

    return clean_reference()


def all_references() -> Dict[str, np.ndarray]:
    """Every clean reference available (real clips if vendored, else the synthetic one)."""
    if available():
        return {n: load_sample(n) for n in SAMPLE_NAMES}
    from .reference import clean_reference

    return {"synthetic": clean_reference()}
