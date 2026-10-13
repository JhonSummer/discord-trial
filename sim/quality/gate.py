"""Quality-gate floors for the Lyra mesh sweep.

``thresholds.json`` is the acceptance bar. A row passes when ViSQOL MOS-LQO,
DNSMOS P.835 OVRL, and STOI are all at least the floor for that condition and
bitrate. Floors are specific to the committed speech fixture and Lyra 1.3.2;
they are regression gates with headroom under the measured scores, not a claim
about a different talker or a future codec.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Mapping

_THRESHOLDS = os.path.join(os.path.dirname(__file__), "thresholds.json")

METRICS = (
    ("visqol_mos", "min_visqol"),
    ("dnsmos_ovrl", "min_dnsmos_ovrl"),
    ("stoi", "min_stoi"),
)


def load_thresholds(path: str | None = None) -> dict:
    with open(path or _THRESHOLDS, "r", encoding="utf-8") as fh:
        return json.load(fh)


def evaluate(rows: List[Mapping], thresholds: Mapping) -> List[str]:
    """Return human-readable failures. An empty list means every row passed."""
    if not thresholds.get("calibrated"):
        return ["thresholds.json is not calibrated"]
    gates: Dict = thresholds["gates"]
    failures: List[str] = []
    seen = set()
    for row in rows:
        condition = str(row["condition"])
        bitrate = str(row["bitrate"])
        seen.add((condition, bitrate))
        spec = gates.get(condition, {}).get(bitrate)
        if spec is None:
            failures.append(f"no gate for {condition} @ {bitrate}")
            continue
        for metric, floor_key in METRICS:
            value = float(row[metric])
            floor = float(spec[floor_key])
            if value < floor:
                failures.append(
                    f"{condition} @ {bitrate}: {metric} {value:.4f} < {floor_key} {floor:.4f}"
                )
    missing = []
    for condition, rates in gates.items():
        for bitrate in rates:
            if (condition, str(bitrate)) not in seen:
                missing.append(f"{condition} @ {bitrate}")
    if missing:
        failures.append("gated cells missing from the result table: " + ", ".join(missing))
    return failures


def passes(row: Mapping, thresholds: Mapping) -> bool:
    if not thresholds.get("calibrated"):
        return False
    spec = thresholds["gates"].get(str(row["condition"]), {}).get(str(row["bitrate"]))
    if spec is None:
        return False
    return all(float(row[metric]) >= float(spec[floor]) for metric, floor in METRICS)
