"""PLCMOS neural MOS (speechmos; INTERSPEECH 2023 model, weights vendored in-wheel).

PLCMOS is trained specifically to score packet-loss-concealed speech, so it is the most
on-target no-reference predictor for a mesh voice path: it rewards concealment that sounds
continuous and penalizes the warbles/dropouts that naive loss handling produces.
"""

from __future__ import annotations

from typing import Dict

import numpy as np


def available() -> bool:
    try:
        from speechmos import plcmos  # noqa: F401
        return True
    except Exception:
        return False


def compute(deg: np.ndarray, sr: int) -> Dict[str, float]:
    from speechmos import plcmos

    x = np.clip(np.asarray(deg, dtype=np.float32), -1.0, 1.0)
    return {"plcmos": float(plcmos.run(x, sr)["plcmos"])}
