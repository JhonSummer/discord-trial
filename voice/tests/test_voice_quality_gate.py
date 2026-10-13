"""The committed Lyra voice-quality gate.

This is the hard requirement: the optimized voice path must clear strong STOI / PESQ / ViSQOL /
DNSMOS / PLCMOS bars under realistic mesh conditions, at every bitrate, and must beat the naive
baseline by a margin. Thresholds live in ``voiceq.thresholds`` and are measured exactly the way
the benchmark reports them (``voiceq.bench.evaluate_corpus``), averaged over the vendored clips
and seeds. See ``voice/results/benchmark.md`` for the full before/after matrix.

The cells are computed once (module fixture) because the neural MOS models make each run cost real
time; the gate is marked ``voicegate`` so it is easy to target or (if ever needed) deselect, but it
runs by default.
"""

from __future__ import annotations

import pytest

from voiceq.bench import Cell, evaluate_corpus
from voiceq.metrics import availability
from voiceq.pipeline import BASELINE, OPTIMIZED, OPTIMIZED_ABR, OPTIMIZED_FEC
from voiceq.thresholds import (
    GATE_ABR_BY_CONDITION,
    GATE_ABR_EFFICIENCY,
    GATE_ABR_ROBUSTNESS,
    GATE_BY_CONDITION,
    GATE_IMPROVEMENT,
    GATE_MODERATE_BY_BITRATE,
)

pytestmark = pytest.mark.voicegate


def _value(cell: Cell, metric: str) -> float:
    if metric.startswith("rob_"):
        return cell.rob_scores[metric]
    if metric == "abs_stoi":
        return cell.abs_scores["stoi"]
    return cell.abs_scores[metric]  # dnsmos_ovrl, plcmos (no-reference)


@pytest.fixture(scope="module")
def cells():
    """Evaluate every gate cell once (averaged over the corpus + seeds)."""
    needed = {("optimized", c, "9.2k") for c in GATE_BY_CONDITION}
    needed |= {("optimized", "moderate", b) for b in GATE_MODERATE_BY_BITRATE}
    needed |= {("baseline", c, "9.2k") for c in GATE_IMPROVEMENT}
    # Adaptive-protection cells + the fixed-FEC / no-redundancy cells it is compared against.
    needed |= {("optimized_abr", c, "9.2k") for c in GATE_ABR_BY_CONDITION}
    needed |= {("optimized_fec", c, "9.2k") for c in ("clean", "light", "heavy", "burst")}
    needed |= {("optimized", c, "9.2k") for c in ("burst",)}
    cfg = {"optimized": OPTIMIZED, "baseline": BASELINE,
           "optimized_fec": OPTIMIZED_FEC, "optimized_abr": OPTIMIZED_ABR}
    return {key: evaluate_corpus(cfg[key[0]], key[1], key[2]) for key in needed}


def test_metric_backends_all_available():
    # The gate is a hard requirement: a missing metric backend is a setup failure, not a skip.
    assert availability() == {"stoi": True, "pesq": True, "visqol": True, "dnsmos": True, "plcmos": True}


@pytest.mark.parametrize("condition", list(GATE_BY_CONDITION))
def test_optimized_clears_bar_by_condition(cells, condition):
    cell = cells[("optimized", condition, "9.2k")]
    for metric, floor in GATE_BY_CONDITION[condition].items():
        got = _value(cell, metric)
        assert got >= floor, f"9.2k/{condition} optimized {metric}={got:.3f} < {floor} (loss={cell.loss:.2%}, lat={cell.latency_ms:.0f}ms)"


@pytest.mark.parametrize("bitrate", list(GATE_MODERATE_BY_BITRATE))
def test_optimized_clears_bar_every_bitrate(cells, bitrate):
    cell = cells[("optimized", "moderate", bitrate)]
    for metric, floor in GATE_MODERATE_BY_BITRATE[bitrate].items():
        got = _value(cell, metric)
        assert got >= floor, f"{bitrate}/moderate optimized {metric}={got:.3f} < {floor}"


@pytest.mark.parametrize("condition", list(GATE_IMPROVEMENT))
def test_optimization_beats_baseline(cells, condition):
    opt = cells[("optimized", condition, "9.2k")]
    base = cells[("baseline", condition, "9.2k")]
    for metric, min_delta in GATE_IMPROVEMENT[condition].items():
        delta = _value(opt, metric) - _value(base, metric)
        assert delta >= min_delta, (
            f"9.2k/{condition}: optimization only improved {metric} by {delta:.3f} "
            f"(< {min_delta}); baseline={_value(base, metric):.3f} optimized={_value(opt, metric):.3f}"
        )


def test_severe_degrades_gracefully_not_catastrophically(cells):
    # Not a strong-quality bar (>60% effective loss is extreme) — just prove the optimized path
    # still beats the baseline and stays intelligible-ish rather than collapsing to noise.
    opt = evaluate_corpus(OPTIMIZED, "severe", "9.2k")
    base = evaluate_corpus(BASELINE, "severe", "9.2k")
    assert opt.rob_scores["rob_stoi"] > base.rob_scores["rob_stoi"] + 0.15
    assert opt.abs_scores["dnsmos_ovrl"] > base.abs_scores["dnsmos_ovrl"] + 0.3


# --- Adaptive bitrate / adaptive protection (OPTIMIZED_ABR) -----------------------------------

@pytest.mark.parametrize("condition", list(GATE_ABR_BY_CONDITION))
def test_abr_clears_bar_by_condition(cells, condition):
    # Adaptivity must not cost quality: the ABR path clears the same strong per-condition bars.
    cell = cells[("optimized_abr", condition, "9.2k")]
    for metric, floor in GATE_ABR_BY_CONDITION[condition].items():
        got = _value(cell, metric)
        assert got >= floor, (
            f"9.2k/{condition} abr {metric}={got:.3f} < {floor} "
            f"(loss={cell.loss:.2%}, {cell.eff_bitrate_bps/1000:.1f} kbps)"
        )


def test_abr_spends_bitrate_only_when_needed(cells):
    # On a clean link, adaptive protection must add no redundancy overhead (stay at the base rate)
    # and so undercut always-on FEC — at equal quality. On a light link it must still be cheaper.
    abr_clean = cells[("optimized_abr", "clean", "9.2k")]
    fec_clean = cells[("optimized_fec", "clean", "9.2k")]
    eff = GATE_ABR_EFFICIENCY
    assert abr_clean.eff_bitrate_bps <= eff["clean_max_bps"], (
        f"ABR paid {abr_clean.eff_bitrate_bps} bps of overhead on a clean link")
    saving = fec_clean.eff_bitrate_bps - abr_clean.eff_bitrate_bps
    assert saving >= eff["clean_min_saving_bps"], (
        f"ABR only saved {saving} bps vs always-on FEC on a clean link")
    for metric, tol in eff["quality_tol"].items():
        got, ref = _value(abr_clean, metric), _value(fec_clean, metric)
        assert got >= ref - tol, f"clean ABR {metric}={got:.3f} worse than FEC {ref:.3f} (tol {tol})"

    abr_light = cells[("optimized_abr", "light", "9.2k")]
    fec_light = cells[("optimized_fec", "light", "9.2k")]
    assert abr_light.eff_bitrate_bps < fec_light.eff_bitrate_bps, (
        f"ABR ({abr_light.eff_bitrate_bps}) not cheaper than FEC ({fec_light.eff_bitrate_bps}) on a light link")


def test_abr_beats_fixed_fec_on_hard_losses(cells):
    # Because it adapts depth, ABR recovers 2-in-a-row bursts that fixed one-frame FEC cannot.
    for condition, rules in GATE_ABR_ROBUSTNESS.items():
        abr = cells[("optimized_abr", condition, "9.2k")]
        if "vs_fec" in rules:
            fec = cells[("optimized_fec", condition, "9.2k")]
            for metric, min_delta in rules["vs_fec"].items():
                delta = _value(abr, metric) - _value(fec, metric)
                assert delta >= min_delta, (
                    f"{condition}: ABR {metric} only beat fixed FEC by {delta:.3f} (< {min_delta}); "
                    f"abr={_value(abr, metric):.3f} fec={_value(fec, metric):.3f}")
        if "vs_optimized" in rules:
            opt = cells[("optimized", condition, "9.2k")]
            for metric, min_delta in rules["vs_optimized"].items():
                delta = _value(abr, metric) - _value(opt, metric)
                assert delta >= min_delta, (
                    f"{condition}: ABR {metric} only beat no-redundancy optimized by {delta:.3f} "
                    f"(< {min_delta}); abr={_value(abr, metric):.3f} opt={_value(opt, metric):.3f}")
