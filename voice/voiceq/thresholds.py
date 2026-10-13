"""Committed voice-quality targets — the hard bar the Lyra voice path must clear.

These thresholds are the contract enforced by ``voice/tests/test_voice_quality_gate.py``. They
are set below the measured scores of the *optimized* path (averaged over the vendored clips and
seeds; see ``voice/results/benchmark.md``) with margin for cross-environment numeric drift, and
— critically — *above* what the naive baseline achieves, so the gate fails if the jitter-buffer
and PLC optimizations regress.

Two metric families (see ``voice/README.md``):

* ``rob_*`` — full-reference scores against the *clean-channel coded* audio. These isolate the
  mesh + jitter-buffer + PLC behavior from codec fidelity and carry the strong absolute bars.
* ``dnsmos_ovrl`` / ``plcmos`` — no-reference neural MOS on the recovered audio (absolute perceived
  quality / concealment quality).
* ``abs_stoi`` — intelligibility against the clean *uncoded* speech (bounded by the stand-in codec).

Real Lyra (a neural codec) would raise the absolute numbers; the harness, thresholds and gate are
codec-agnostic, so swapping it in only tightens these bars.
"""

from __future__ import annotations

from typing import Dict

# Floors for the OPTIMIZED path at 9.2 kbps, per mesh condition.
GATE_BY_CONDITION: Dict[str, Dict[str, float]] = {
    "clean":    {"rob_stoi": 0.999, "rob_visqol": 4.90, "dnsmos_ovrl": 2.40, "plcmos": 2.10, "abs_stoi": 0.78},
    "light":    {"rob_stoi": 0.90,  "rob_visqol": 4.10, "dnsmos_ovrl": 2.30, "plcmos": 1.95, "abs_stoi": 0.78},
    "moderate": {"rob_stoi": 0.82,  "rob_visqol": 3.70, "dnsmos_ovrl": 2.20, "plcmos": 1.60, "abs_stoi": 0.70},
    "heavy":    {"rob_stoi": 0.75,  "rob_visqol": 3.50, "dnsmos_ovrl": 2.10, "plcmos": 1.50, "abs_stoi": 0.64},
}

# Floors for the OPTIMIZED path at "moderate", per bitrate (the voice path must work at every rate).
GATE_MODERATE_BY_BITRATE: Dict[str, Dict[str, float]] = {
    "3.2k": {"rob_stoi": 0.80, "dnsmos_ovrl": 2.00, "plcmos": 1.50},
    "6.0k": {"rob_stoi": 0.82, "dnsmos_ovrl": 2.10, "plcmos": 1.55},
    "9.2k": {"rob_stoi": 0.82, "dnsmos_ovrl": 2.20, "plcmos": 1.60},
}

# The optimization must beat the naive baseline by at least this much (optimized - baseline),
# at 9.2 kbps. Proves the jitter-buffer + PLC work is doing the lifting, not the codec.
GATE_IMPROVEMENT: Dict[str, Dict[str, float]] = {
    "moderate": {"rob_stoi": 0.18, "dnsmos_ovrl": 0.70, "plcmos": 0.25},
    "heavy":    {"rob_stoi": 0.30, "dnsmos_ovrl": 0.80, "plcmos": 0.25},
}
