"""Unified voice-quality metrics.

Two families, deliberately kept side by side because they answer different questions:

* **Full-reference** (``stoi``, ``estoi``, ``pesq``, ``visqol``): compare the recovered
  waveform against the clean reference. Valid on any speech, real or synthetic, because they
  measure *degradation*. These are the backbone of the gate.
* **No-reference / neural MOS** (``dnsmos_*``, ``plcmos``): learned predictors of perceived
  quality from the degraded signal alone. They are trained on natural speech, so the gate runs
  them on the vendored real-speech clips; ``plcmos`` in particular is trained specifically to
  judge packet-loss-concealed audio, which is exactly what the mesh conditions produce.

Every adapter degrades gracefully: if its backend is not importable the metric reports
``available=False`` instead of raising, so partial environments still get partial scores.
``score_pair`` is the one call the pipeline/bench/gate use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List

import numpy as np

from ..audio import align_to_reference

# Higher is better for every metric here; these are the published-scale maxima (STOI/ESTOI in
# [0,1]; PESQ-wb up to 4.64; DNSMOS/PLCMOS/ViSQOL on the 1-5 MOS scale).
METRIC_RANGE: Dict[str, float] = {
    "stoi": 1.0,
    "estoi": 1.0,
    "pesq": 4.64,
    "visqol": 5.0,
    "dnsmos_ovrl": 5.0,
    "dnsmos_sig": 5.0,
    "dnsmos_bak": 5.0,
    "dnsmos_p808": 5.0,
    "plcmos": 5.0,
}

FULL_REFERENCE = {"stoi", "estoi", "pesq", "visqol"}
NO_REFERENCE = {"dnsmos_ovrl", "dnsmos_sig", "dnsmos_bak", "dnsmos_p808", "plcmos"}


@dataclass
class MetricResult:
    name: str
    value: float
    available: bool = True
    full_reference: bool = True
    detail: str = ""


def _safe(fn: Callable[[], Dict[str, float]], names: List[str], full_ref: bool) -> Dict[str, MetricResult]:
    try:
        vals = fn()
        return {k: MetricResult(k, float(vals[k]), True, full_ref) for k in names if k in vals}
    except Exception as exc:  # noqa: BLE001 - a missing/odd backend must not break scoring
        return {k: MetricResult(k, float("nan"), False, full_ref, detail=f"{type(exc).__name__}: {exc}") for k in names}


def score_pair(
    ref: np.ndarray,
    deg: np.ndarray,
    sr: int = 16_000,
    *,
    align: bool = True,
    include: Dict[str, bool] | None = None,
) -> Dict[str, MetricResult]:
    """Score degraded ``deg`` against clean ``ref`` across every available metric.

    ``align`` delay-compensates ``deg`` to ``ref`` first (full-reference metrics need it). The
    neural MOS predictors are evaluated on the aligned, length-matched degraded signal so all
    metrics describe the same stretch of audio.
    """
    from . import dnsmos as _dnsmos
    from . import pesq as _pesq
    from . import plcmos as _plcmos
    from . import stoi as _stoi
    from . import visqol as _visqol

    if align:
        ref_a, deg_a = align_to_reference(ref, deg, sr=sr)
    else:
        from ..audio import align_lengths

        ref_a, deg_a = align_lengths(ref, deg)

    want = {k: True for k in METRIC_RANGE}
    if include:
        want.update(include)

    out: Dict[str, MetricResult] = {}
    if want.get("stoi") or want.get("estoi"):
        out.update(_safe(lambda: _stoi.compute(ref_a, deg_a, sr), ["stoi", "estoi"], True))
    if want.get("pesq"):
        out.update(_safe(lambda: _pesq.compute(ref_a, deg_a, sr), ["pesq"], True))
    if want.get("visqol"):
        out.update(_safe(lambda: _visqol.compute(ref_a, deg_a, sr), ["visqol"], True))
    if any(want.get(k) for k in ("dnsmos_ovrl", "dnsmos_sig", "dnsmos_bak", "dnsmos_p808")):
        out.update(_safe(lambda: _dnsmos.compute(deg_a, sr), ["dnsmos_ovrl", "dnsmos_sig", "dnsmos_bak", "dnsmos_p808"], False))
    if want.get("plcmos"):
        out.update(_safe(lambda: _plcmos.compute(deg_a, sr), ["plcmos"], False))
    return out


def values(results: Dict[str, MetricResult]) -> Dict[str, float]:
    """Flatten to ``name -> value`` for available metrics only."""
    return {k: r.value for k, r in results.items() if r.available}


def availability() -> Dict[str, bool]:
    """Which metric backends import in this environment (for diagnostics/reporting)."""
    from . import dnsmos as _dnsmos
    from . import pesq as _pesq
    from . import plcmos as _plcmos
    from . import stoi as _stoi
    from . import visqol as _visqol

    return {
        "stoi": _stoi.available(),
        "pesq": _pesq.available(),
        "visqol": _visqol.available(),
        "dnsmos": _dnsmos.available(),
        "plcmos": _plcmos.available(),
    }
