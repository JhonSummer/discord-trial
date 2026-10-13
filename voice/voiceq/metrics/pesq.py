"""ITU-T P.862.2 wideband PESQ (MOS-LQO) via the ``pesq`` C extension."""

from __future__ import annotations

from typing import Dict

import numpy as np


def available() -> bool:
    try:
        import pesq  # noqa: F401
        return True
    except Exception:
        return False


def compute(ref: np.ndarray, deg: np.ndarray, sr: int) -> Dict[str, float]:
    from pesq import pesq as _pesq

    mode = "wb" if sr >= 16000 else "nb"
    ref = np.asarray(ref, dtype=np.float32)
    deg = np.asarray(deg, dtype=np.float32)
    return {"pesq": float(_pesq(sr, ref, deg, mode))}
