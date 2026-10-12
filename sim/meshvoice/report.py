"""Rendering helpers: CSV rows and fixed-width text tables for the sweep output."""

from __future__ import annotations

import csv
import io
from typing import Dict, List, Sequence


def to_csv(rows: Sequence[Dict], path: str) -> None:
    if not rows:
        with open(path, "w", newline="") as f:
            f.write("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def text_table(rows: Sequence[Dict], columns: Sequence[str] | None = None) -> str:
    if not rows:
        return "(no rows)\n"
    cols = list(columns) if columns else list(rows[0].keys())
    widths = {c: len(c) for c in cols}
    rendered: List[List[str]] = []
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c, "")
            s = f"{v:.3f}" if isinstance(v, float) else str(v)
            widths[c] = max(widths[c], len(s))
            cells.append(s)
        rendered.append(cells)
    out = io.StringIO()
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    out.write(header + "\n")
    out.write("  ".join("-" * widths[c] for c in cols) + "\n")
    for cells in rendered:
        out.write("  ".join(cell.ljust(widths[cols[i]]) for i, cell in enumerate(cells)) + "\n")
    return out.getvalue()
