"""DNSMOS P.835 neural MOS (speechmos; ONNX weights vendored in-wheel, runs offline).

Returns the three P.835 axes — signal (``sig``), background (``bak``) and overall (``ovrl``) —
plus the P.808 single-scalar MOS. The overall axis is the headline no-reference number the gate
tracks on real speech.
"""

from __future__ import annotations

from typing import Dict

import numpy as np


def available() -> bool:
    try:
        from speechmos import dnsmos  # noqa: F401
        return True
    except Exception:
        return False


def compute(deg: np.ndarray, sr: int) -> Dict[str, float]:
    from speechmos import dnsmos

    x = np.clip(np.asarray(deg, dtype=np.float32), -1.0, 1.0)
    r = dnsmos.run(x, sr)
    return {
        "dnsmos_ovrl": float(r["ovrl_mos"]),
        "dnsmos_sig": float(r["sig_mos"]),
        "dnsmos_bak": float(r["bak_mos"]),
        "dnsmos_p808": float(r["p808_mos"]),
    }
