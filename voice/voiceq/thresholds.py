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

# --- Adaptive bitrate / adaptive protection (``OPTIMIZED_ABR``, see ``voiceq.abr``) ----------
# The "beat the bar on Bluetooth" lever from docs/03: redundancy depth tracks measured loss, so
# the stream pays no FEC overhead on a clean link yet ramps to two-deep protection under bursts.

# Floors for the ABR path at 9.2 kbps, per condition. Adaptivity must not cost quality: these are
# as strong as the fixed optimized bars (set below the measured ABR scores with margin).
GATE_ABR_BY_CONDITION: Dict[str, Dict[str, float]] = {
    "clean":    {"rob_stoi": 0.999, "dnsmos_ovrl": 2.40, "plcmos": 2.10, "abs_stoi": 0.78},
    "light":    {"rob_stoi": 0.92,  "dnsmos_ovrl": 2.30, "plcmos": 2.05, "abs_stoi": 0.77},
    "moderate": {"rob_stoi": 0.85,  "dnsmos_ovrl": 2.25, "plcmos": 1.85, "abs_stoi": 0.72},
    "heavy":    {"rob_stoi": 0.83,  "dnsmos_ovrl": 2.20, "plcmos": 1.75, "abs_stoi": 0.66},
    "burst":    {"rob_stoi": 0.78,  "dnsmos_ovrl": 2.25, "plcmos": 1.70, "abs_stoi": 0.65},
}

# Efficiency: adaptive protection must spend the redundancy bitrate *only when the link needs it*.
# On a clean link it must add no overhead (stay at the base rate) and so undercut always-on FEC's
# fixed +3.2 kbps; on a light link it must still be cheaper than always-on FEC.
ABR_BASE_BPS = 9200
GATE_ABR_EFFICIENCY = {
    "clean_max_bps": 9300,          # ~no protection overhead on a clean link
    "clean_min_saving_bps": 2800,   # vs always-on FEC (which pays +3200 regardless of loss)
    "quality_tol": {"rob_stoi": 0.005, "dnsmos_ovrl": 0.05, "plcmos": 0.05},  # clean parity w/ FEC
}

# Robustness: because it adapts *depth*, ABR recovers bursts that fixed one-frame FEC cannot, so on
# the hardest losses it must *beat* always-on FEC — and beat the no-redundancy optimized path by a
# wide margin. Deltas are (ABR - other) at 9.2 kbps.
GATE_ABR_ROBUSTNESS = {
    "heavy": {"vs_fec":       {"rob_stoi": 0.02, "plcmos": 0.07}},
    "burst": {"vs_fec":       {"rob_stoi": -0.01},                 # at least matches fixed FEC
             "vs_optimized":  {"rob_stoi": 0.02, "plcmos": 0.05}},  # clearly beats no-redundancy
}
