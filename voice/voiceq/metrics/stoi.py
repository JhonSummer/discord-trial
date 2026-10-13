"""STOI / ESTOI intelligibility (pystoi, pure-Python; always available once installed)."""

from __future__ import annotations

from typing import Dict

import numpy as np


def available() -> bool:
    try:
        import pystoi  # noqa: F401
        return True
    except Exception:
        return False


def compute(ref: np.ndarray, deg: np.ndarray, sr: int) -> Dict[str, float]:
    from pystoi import stoi

    ref = np.asarray(ref, dtype=np.float64)
    deg = np.asarray(deg, dtype=np.float64)
    return {
        "stoi": float(stoi(ref, deg, sr, extended=False)),
        "estoi": float(stoi(ref, deg, sr, extended=True)),
    }
