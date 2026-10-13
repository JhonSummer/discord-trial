"""Benchmark runner: score the voice path across bitrate x condition x config x seed.

For each cell we report two complementary views (see ``voice/README.md``):

* **absolute** quality of the recovered audio vs the *clean uncoded* speech — the real
  end-to-end number, bounded by the stand-in codec. DNSMOS/PLCMOS are no-reference neural MOS,
  so they are absolute by construction.
* **robustness** of the mesh path vs the *clean-channel coded* audio — isolates what loss/jitter
  + the jitter buffer + PLC do, independent of codec fidelity. This is what the optimization
  moves, and where the before/after gap is largest.

``evaluate`` is the single cell evaluator shared with the committed gate so thresholds are
measured exactly the way the bench reports them. ``python -m voiceq.bench`` writes the committed
tables under ``voice/results/``.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from . import SAMPLE_RATE, corpus
from .codec import ParametricCodec
from .channel import CONDITIONS
from .metrics import score_pair
from .pipeline import PRESETS, PipelineConfig, run_pipeline

_ABS_METRICS = ("stoi", "estoi", "pesq", "visqol", "dnsmos_ovrl", "dnsmos_sig", "dnsmos_p808", "plcmos")
_ROB_METRICS = ("stoi", "pesq", "visqol")


@dataclass
class Cell:
    bitrate: str
    condition: str
    config: str
    loss: float
    present_rate: float
    latency_ms: float
    eff_bitrate_bps: int
    abs_scores: Dict[str, float]      # vs clean uncoded speech
    rob_scores: Dict[str, float]      # vs clean-channel coded speech


def _mean(dicts: List[Dict[str, float]]) -> Dict[str, float]:
    keys = set().union(*dicts) if dicts else set()
    out = {}
    for k in keys:
        vals = [d[k] for d in dicts if k in d and not np.isnan(d[k])]
        out[k] = float(np.mean(vals)) if vals else float("nan")
    return out


def evaluate(clean: np.ndarray, config: PipelineConfig, condition: str, bitrate: str,
             seeds: Sequence[int] = (1, 2, 3), coded_ref: Optional[np.ndarray] = None) -> Cell:
    """Evaluate one (config, condition, bitrate) cell, averaged over ``seeds``."""
    cfg = PipelineConfig(**{**config.__dict__, "bitrate": bitrate})
    if coded_ref is None:
        c = ParametricCodec(bitrate, aperiodicity=cfg.aperiodicity)
        coded_ref = c.decode(c.encode(clean))

    abs_list, rob_list = [], []
    loss = pres = lat = 0.0
    eff = 0
    for s in seeds:
        out = run_pipeline(clean, cfg, condition, seed=s)
        abs_r = score_pair(clean, out.audio, SAMPLE_RATE,
                           include={k: True for k in _ABS_METRICS})
        rob_r = score_pair(coded_ref, out.audio, SAMPLE_RATE,
                           include={k: (k in _ROB_METRICS) for k in
                                    ("stoi", "estoi", "pesq", "visqol", "dnsmos_ovrl",
                                     "dnsmos_sig", "dnsmos_bak", "dnsmos_p808", "plcmos")})
        abs_list.append({k: r.value for k, r in abs_r.items() if r.available})
        rob_list.append({f"rob_{k}": r.value for k, r in rob_r.items() if r.available and k in _ROB_METRICS})
        loss += out.channel_loss
        pres += out.present_rate
        lat += out.mean_latency_ms
        eff = out.effective_bitrate_bps
    n = len(seeds)
    return Cell(
        bitrate=bitrate, condition=condition, config=cfg.label or config.label,
        loss=loss / n, present_rate=pres / n, latency_ms=lat / n, eff_bitrate_bps=eff,
        abs_scores=_mean(abs_list), rob_scores=_mean(rob_list),
    )


def run_matrix(bitrates: Sequence[str], conditions: Sequence[str], configs: Sequence[PipelineConfig],
               clips: Optional[Dict[str, np.ndarray]] = None, seeds: Sequence[int] = (1, 2, 3)) -> List[Cell]:
    clips = clips or corpus.all_references()
    cells: List[Cell] = []
    for bitrate in bitrates:
        coded = {name: ParametricCodec(bitrate).decode(ParametricCodec(bitrate).encode(sig))
                 for name, sig in clips.items()}
        for cond in conditions:
            for config in configs:
                per_clip = [evaluate(sig, config, cond, bitrate, seeds, coded[name])
                            for name, sig in clips.items()]
                cells.append(_merge_cells(per_clip))
    return cells


def _merge_cells(cells: List[Cell]) -> Cell:
    c0 = cells[0]
    return Cell(
        bitrate=c0.bitrate, condition=c0.condition, config=c0.config,
        loss=float(np.mean([c.loss for c in cells])),
        present_rate=float(np.mean([c.present_rate for c in cells])),
        latency_ms=float(np.mean([c.latency_ms for c in cells])),
        eff_bitrate_bps=c0.eff_bitrate_bps,
        abs_scores=_mean([c.abs_scores for c in cells]),
        rob_scores=_mean([c.rob_scores for c in cells]),
    )


def _fmt_table(cells: List[Cell]) -> str:
    hdr = ("| bitrate | condition | config | loss% | present% | lat ms | kbps | "
           "STOI | PESQ | ViSQOL* | DNSMOS | PLCMOS | STOI(ch) | ViSQOL*(ch) |")
    sep = "|" + "---|" * 13
    lines = [hdr, sep]
    for c in cells:
        a, r = c.abs_scores, c.rob_scores
        g = lambda d, k: f"{d.get(k, float('nan')):.3f}"
        lines.append(
            f"| {c.bitrate} | {c.condition} | {c.config} | {c.loss*100:.1f} | "
            f"{c.present_rate*100:.1f} | {c.latency_ms:.0f} | {c.eff_bitrate_bps/1000:.1f} | "
            f"{g(a,'stoi')} | {g(a,'pesq')} | {g(a,'visqol')} | {g(a,'dnsmos_ovrl')} | {g(a,'plcmos')} | "
            f"{g(r,'rob_stoi')} | {g(r,'rob_visqol')} |"
        )
    return "\n".join(lines)


def _csv(cells: List[Cell]) -> str:
    cols = ["bitrate", "condition", "config", "loss", "present_rate", "latency_ms", "eff_bitrate_bps",
            "abs_stoi", "abs_estoi", "abs_pesq", "abs_visqol", "abs_dnsmos_ovrl", "abs_dnsmos_p808",
            "abs_plcmos", "rob_stoi", "rob_pesq", "rob_visqol"]
    rows = [",".join(cols)]
    for c in cells:
        a, r = c.abs_scores, c.rob_scores
        rows.append(",".join(str(x) for x in [
            c.bitrate, c.condition, c.config, f"{c.loss:.4f}", f"{c.present_rate:.4f}",
            f"{c.latency_ms:.2f}", c.eff_bitrate_bps,
            f"{a.get('stoi', float('nan')):.4f}", f"{a.get('estoi', float('nan')):.4f}",
            f"{a.get('pesq', float('nan')):.4f}", f"{a.get('visqol', float('nan')):.4f}",
            f"{a.get('dnsmos_ovrl', float('nan')):.4f}", f"{a.get('dnsmos_p808', float('nan')):.4f}",
            f"{a.get('plcmos', float('nan')):.4f}", f"{r.get('rob_stoi', float('nan')):.4f}",
            f"{r.get('rob_pesq', float('nan')):.4f}", f"{r.get('rob_visqol', float('nan')):.4f}",
        ]))
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Lyra voice-quality benchmark")
    ap.add_argument("--bitrates", nargs="+", default=["3.2k", "6.0k", "9.2k"])
    ap.add_argument("--conditions", nargs="+", default=list(CONDITIONS))
    ap.add_argument("--configs", nargs="+", default=["baseline", "optimized", "optimized_fec"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "results"))
    args = ap.parse_args()

    configs = [PRESETS[c] for c in args.configs]
    cells = run_matrix(args.bitrates, args.conditions, configs, seeds=args.seeds)
    os.makedirs(args.outdir, exist_ok=True)
    table = _fmt_table(cells)
    with open(os.path.join(args.outdir, "benchmark.md"), "w") as f:
        f.write("# Lyra voice-quality benchmark\n\n")
        f.write(f"Averaged over clips={len(corpus.all_references())} seeds={args.seeds}.\n\n")
        f.write(table + "\n")
    with open(os.path.join(args.outdir, "benchmark.csv"), "w") as f:
        f.write(_csv(cells) + "\n")
    print(table)
    print(f"\nwrote {args.outdir}/benchmark.md and benchmark.csv")


if __name__ == "__main__":
    main()
