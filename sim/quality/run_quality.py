"""Run clean speech through Lyra v2 under mesh loss and write the quality table.

From ``sim/``::

    python3 run_quality.py            # encode, impair, score, gate
    python3 run_quality.py --check    # re-gate the committed table, no codec

Exit status is 0 when every gated cell meets ``thresholds.json``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from typing import Dict, List, Mapping

from meshvoice.report import text_table

from .channel import BITRATES, CONDITIONS, all_masks, loss_pattern_flag, mask_from_pattern, simulate
from .gate import evaluate, load_thresholds, passes
from .speech import N_FRAMES, N_SAMPLES, fixture_path, load_pcm16

_PKG = os.path.dirname(__file__)
RESULTS_DIR = os.path.join(_PKG, "results")
WORK_DIR = os.path.join(_PKG, "work")
CACHE_DIR = os.path.join(_PKG, ".cache")

SCORE_KEYS = ("visqol_mos", "dnsmos_sig", "dnsmos_bak", "dnsmos_ovrl", "stoi")
CSV_FIELDS = (
    "condition", "role", "bitrate", "hops", "per", "jitter_buffer_ms", "n_calls",
    "frames", "frames_played", "frames_lost", "loss_fraction",
    "lost_random", "lost_congestion", "lost_late", "sim_mte_p95_ms",
    "visqol_mos", "dnsmos_sig", "dnsmos_bak", "dnsmos_ovrl", "stoi", "stoi_lag_samples",
    "passes_gate",
)


def _round_score(value: float) -> float:
    return round(float(value), 5)


def _blank_if_nan(value) -> object:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return value


def publish(row: Mapping, thresholds: Mapping) -> Dict:
    out = dict(row)
    for key in SCORE_KEYS:
        out[key] = _round_score(row[key])
    out["loss_fraction"] = round(float(row["loss_fraction"]), 5)
    out["sim_mte_p95_ms"] = _blank_if_nan(row.get("sim_mte_p95_ms"))
    if out["sim_mte_p95_ms"] != "":
        out["sim_mte_p95_ms"] = round(float(out["sim_mte_p95_ms"]), 2)
    out["stoi_lag_samples"] = int(row["stoi_lag_samples"])
    out["passes_gate"] = "yes" if passes(out, thresholds) else "no"
    return out


def reference_row(cache_dir: str) -> Dict:
    from .score import read_wav, score_pair

    load_pcm16()
    reference = read_wav(fixture_path())
    if len(reference) != N_SAMPLES:
        raise RuntimeError("reference length does not match the fixture contract")
    scores = score_pair(reference, reference, cache_dir)
    return {
        "condition": "reference",
        "role": "reference",
        "bitrate": "pcm",
        "hops": "",
        "per": "",
        "jitter_buffer_ms": "",
        "n_calls": "",
        "frames": N_FRAMES,
        "frames_played": N_FRAMES,
        "frames_lost": 0,
        "loss_fraction": 0.0,
        "lost_random": 0,
        "lost_congestion": 0,
        "lost_late": 0,
        "sim_mte_p95_ms": "",
        **scores,
    }


def sweep(work_dir: str, cache_dir: str) -> List[Dict]:
    from .lyra_codec import assert_packet_count, decode, encode
    from .score import read_wav, score_pair

    load_pcm16()
    reference = read_wav(fixture_path())
    rows = [reference_row(cache_dir)]
    for bitrate in BITRATES:
        encoded_dir = os.path.join(work_dir, f"enc_{bitrate}")
        encoded = encode(fixture_path(), bitrate, encoded_dir)
        assert_packet_count(encoded, bitrate, N_FRAMES)
        for condition in CONDITIONS:
            received, meta = simulate(condition, bitrate, N_FRAMES)
            pattern = loss_pattern_flag(received)
            if mask_from_pattern(N_FRAMES, pattern) != received:
                raise RuntimeError(
                    f"loss pattern for {condition.name} @ {bitrate} does not round-trip "
                    "through Lyra's float32 packet-loss ceil"
                )
            decoded_dir = os.path.join(work_dir, f"dec_{bitrate}_{condition.name}")
            wav_path = decode(encoded, bitrate, decoded_dir, pattern, suffix=f"_{condition.name}")
            degraded = read_wav(wav_path)
            if len(degraded) != len(reference):
                raise RuntimeError(
                    f"{condition.name} @ {bitrate} decoded {len(degraded)} samples, "
                    f"reference is {len(reference)}"
                )
            scores = score_pair(reference, degraded, cache_dir)
            meta = dict(meta)
            meta["bitrate"] = str(bitrate)
            rows.append({**meta, **scores})
            print(
                f"{condition.name:12} {bitrate:4}  "
                f"loss={meta['loss_fraction']:.3f}  "
                f"visqol={scores['visqol_mos']:.3f}  "
                f"dnsmos={scores['dnsmos_ovrl']:.3f}  "
                f"stoi={scores['stoi']:.3f}",
                flush=True,
            )
    return rows


def write_masks(path: str) -> None:
    masks = all_masks(N_FRAMES)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(masks, fh, indent=2)
        fh.write("\n")


def write_csv(rows: List[Mapping], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CSV_FIELDS), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CSV_FIELDS})


def read_csv(path: str) -> List[Dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def render_summary(rows: List[Mapping], thresholds: Mapping, failures: List[str]) -> str:
    lines = [
        "# Lyra mesh voice quality",
        "",
        "Clean 12 s Harvard-sentence speech (espeak-ng, 16 kHz) encoded with Lyra v2",
        "(google/lyra 1.3.2, `47698dad`) at 3.2 / 6 / 9.2 kbps. Each 20 ms frame is",
        "passed through the mesh simulator. Frames whose fate is not `ok` — residual",
        "packet error, congestion, or jitter-buffer late loss — are concealed by",
        "Lyra's decoder. Arrival jitter inside the buffer does not time-warp audio.",
        "",
        "Scores are ViSQOL speech-mode MOS-LQO (lattice mapper), DNSMOS P.835",
        "(non-personalized OVRL / SIG / BAK), and STOI after aligning Lyra's delay.",
        "ViSQOL and STOI compare against the clean fixture. DNSMOS does not use a",
        "reference. The `reference` row is the fixture scored against itself.",
        "",
        "`hold` rows are the usable-call cases (clean link, 2% residual loss, 3 hops).",
        "`watch` rows are stress (5% loss, a jitter buffer shorter than the connection",
        "interval, 5 hops, three calls on one classic-BLE relay). Both are gated.",
        "",
    ]
    show = [
        "condition", "role", "bitrate", "loss_fraction", "sim_mte_p95_ms",
        "visqol_mos", "dnsmos_ovrl", "stoi", "passes_gate",
    ]
    lines.append("## Scores")
    lines.append("")
    lines.append("```")
    lines.append(text_table(rows, show).rstrip())
    lines.append("```")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    if not thresholds.get("calibrated"):
        lines.append("Thresholds are not calibrated yet. The sweep wrote measurements only.")
    else:
        lines.append(thresholds.get("notes", "").strip())
        lines.append("")
        lines.append("| condition | bitrate | min ViSQOL | min DNSMOS OVRL | min STOI |")
        lines.append("| --- | --- | --- | --- | --- |")
        for condition, rates in thresholds["gates"].items():
            for bitrate, spec in rates.items():
                lines.append(
                    f"| {condition} | {bitrate} | {spec['min_visqol']} | "
                    f"{spec['min_dnsmos_ovrl']} | {spec['min_stoi']} |"
                )
        lines.append("")
        if failures:
            lines.append("Failures:")
            lines.append("")
            for failure in failures:
                lines.append(f"- {failure}")
        else:
            lines.append("Every gated cell meets its floor.")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```bash")
    lines.append("cd sim")
    lines.append("python3 -m venv .venv && .venv/bin/pip install -r requirements-quality.txt")
    lines.append("bash quality/setup_lyra.sh          # once; needs gcc-11 and bazelisk")
    lines.append(".venv/bin/python run_quality.py")
    lines.append(".venv/bin/python run_quality.py --check")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def finalize(rows: List[Mapping], thresholds: Mapping, results_dir: str) -> List[str]:
    published = [publish(row, thresholds) for row in rows]
    os.makedirs(results_dir, exist_ok=True)
    write_csv(published, os.path.join(results_dir, "quality.csv"))
    write_masks(os.path.join(results_dir, "masks.json"))
    failures = evaluate(published, thresholds) if thresholds.get("calibrated") else [
        "thresholds.json is not calibrated"
    ]
    summary = render_summary(published, thresholds, failures if thresholds.get("calibrated") else [])
    with open(os.path.join(results_dir, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write(summary)
    with open(os.path.join(results_dir, "scores.json"), "w", encoding="utf-8") as fh:
        json.dump(published, fh, indent=2)
        fh.write("\n")
    print(text_table(published, [
        "condition", "bitrate", "loss_fraction", "visqol_mos", "dnsmos_ovrl", "stoi", "passes_gate",
    ]))
    return failures


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lyra mesh voice-quality harness")
    parser.add_argument("--check", action="store_true", help="gate the committed table; do not run Lyra")
    parser.add_argument("--work", default=WORK_DIR)
    parser.add_argument("--cache", default=CACHE_DIR)
    parser.add_argument("--results", default=RESULTS_DIR)
    args = parser.parse_args(argv)
    thresholds = load_thresholds()
    if args.check:
        csv_path = os.path.join(args.results, "quality.csv")
        if not os.path.isfile(csv_path):
            print(f"missing {csv_path}; run the sweep first", file=sys.stderr)
            return 1
        rows = read_csv(csv_path)
        failures = evaluate(rows, thresholds)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1 if failures else 0
    rows = sweep(args.work, args.cache)
    failures = finalize(rows, thresholds, args.results)
    if not thresholds.get("calibrated"):
        print("wrote measurements; thresholds.json is not calibrated", file=sys.stderr)
        return 2
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
