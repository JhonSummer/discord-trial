#!/usr/bin/env python3
"""Run the mesh-voice sweep and write evidence artifacts to ``sim/results/``.

Produces four tables:
  A. single-relay concurrent-call capacity per codec / BLE profile (vs analytic bound)
  B. per-hop mouth-to-ear latency growth on a line
  C. realistic random-geometric cluster capacity
  D. adaptive-bitrate vs fixed 9.2 kbps on a loaded relay

Run from the ``sim/`` directory:  python3 run_sweep.py
"""

from __future__ import annotations

import math
import os
from typing import Dict, List

from meshvoice.codec import LYRA_V2_3200, LYRA_V2_6000, LYRA_V2_9200
from meshvoice.network import LinkParams, random_geometric
from meshvoice.metrics import summarize
from meshvoice.report import text_table, to_csv
from meshvoice.scenarios import (
    QoS, adaptive_shared_relay, analytic_capacity, breaking_point, call_bitrate_bps,
    line_result, make_calls, random_pairs_paths, shared_relay,
)
from meshvoice.simulator import SimParams, Simulator

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# BLE profiles, expressed as *already-usable* application-layer goodput. The 0.1% residual
# error rate is what remains after BLE link-layer retransmission on a workable link.
BLE_CLASSIC = LinkParams(capacity_bps=37_500.0, connection_interval_ms=15.0, per=0.001)
BLE5_FAST = LinkParams(capacity_bps=250_000.0, connection_interval_ms=7.5, per=0.001)

OVERHEAD = 12.0  # bytes/packet: SRTP + mesh envelope header (RTP-sized, uncompressed)
QOS = QoS(max_p95_ms=200.0, max_loss=0.02)
SIM = SimParams(duration_s=10.0, encode_ms=10.0, decode_ms=5.0, jitter_buffer_ms=60.0, seed=7)
HOP_SEEDS = range(20, 28)  # average the per-hop table over several phase/loss realizations

CODECS = [LYRA_V2_9200, LYRA_V2_6000, LYRA_V2_3200]
BLE_PROFILES = [("ble_classic_37.5k", BLE_CLASSIC), ("ble5_250k", BLE5_FAST)]


def table_a_capacity() -> List[Dict]:
    rows = []
    for prof_name, prof in BLE_PROFILES:
        for codec in CODECS:
            build = lambda n, c=codec, p=prof: shared_relay(n, c, p, overhead_bytes=OVERHEAD, seed=11)
            bp = breaking_point(build, QOS, SIM, n_max=96)
            analytic = analytic_capacity(codec, prof, overhead_bytes=OVERHEAD)
            rows.append({
                "ble_profile": prof_name,
                "codec": codec.name,
                "call_kbps_on_wire": round(call_bitrate_bps(codec, overhead_bytes=OVERHEAD) / 1000.0, 2),
                "analytic_max_calls": round(analytic, 2),
                "simulated_breaking_point": bp,
            })
    return rows


def table_b_hops() -> List[Dict]:
    rows = []
    for hops in range(1, 8):
        p95s, losses = [], []
        for s in HOP_SEEDS:
            sim = SimParams(duration_s=SIM.duration_s, encode_ms=SIM.encode_ms,
                            decode_ms=SIM.decode_ms, jitter_buffer_ms=SIM.jitter_buffer_ms, seed=s)
            agg = line_result(hops, LYRA_V2_9200, BLE_CLASSIC, sim, overhead_bytes=OVERHEAD, seed=s)
            p95s.append(agg.mte_p95_ms)
            losses.append(agg.loss_fraction * 100.0)
        mean_p95 = sum(p95s) / len(p95s)
        mean_loss = sum(losses) / len(losses)
        rows.append({
            "hops": hops,
            "mean_mte_p95_ms": round(mean_p95, 1),
            "mean_loss_pct": round(mean_loss, 2),
            "meets_200ms_2pct": (mean_p95 <= QOS.max_p95_ms and mean_loss <= QOS.max_loss * 100.0),
        })
    return rows


def table_c_cluster() -> List[Dict]:
    rows = []
    for prof_name, prof in BLE_PROFILES:
        for codec in (LYRA_V2_9200, LYRA_V2_3200):
            g = random_geometric(24, radius=0.33, params=prof, seed=3)
            pb = codec.packet_bits(1, OVERHEAD)
            edges = g.num_edges

            def build(n, g=g, codec=codec, pb=pb):
                paths = random_pairs_paths(g, n, pb, routing="latency", hop_limit=5, seed=100 + n)
                return g, make_calls(paths, codec, overhead_bytes=OVERHEAD, seed=200 + n)

            bp = breaking_point(build, QOS, SIM, n_max=60)
            # characterize the cluster at its breaking point
            gg, calls = build(max(bp, 1))
            agg = summarize(Simulator(gg, calls, SIM).run())
            avg_hops = (sum(len(c.path) - 1 for c in calls) / len(calls)) if calls else 0.0
            rows.append({
                "ble_profile": prof_name,
                "codec": codec.name,
                "nodes": 24,
                "edges": edges,
                "avg_hops_at_bp": round(avg_hops, 2),
                "max_concurrent_calls": bp,
                "p95_ms_at_bp": round(agg.mte_p95_ms, 1),
                "loss_pct_at_bp": round(agg.loss_fraction * 100.0, 2),
            })
    return rows


def table_d_adaptive() -> List[Dict]:
    rows = []
    prof = BLE_CLASSIC
    fixed_build = lambda n: shared_relay(n, LYRA_V2_9200, prof, overhead_bytes=OVERHEAD, seed=11)
    adaptive_build = lambda n: adaptive_shared_relay(n, prof, overhead_bytes=OVERHEAD, seed=11)
    rows.append({"relay": "fixed_9.2k", "breaking_point": breaking_point(fixed_build, QOS, SIM, n_max=96)})
    rows.append({"relay": "adaptive_9.2k->3.2k", "breaking_point": breaking_point(adaptive_build, QOS, SIM, n_max=96)})
    return rows


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)

    a = table_a_capacity()
    b = table_b_hops()
    c = table_c_cluster()
    d = table_d_adaptive()

    to_csv(a, os.path.join(RESULTS_DIR, "capacity.csv"))
    to_csv(b, os.path.join(RESULTS_DIR, "latency_vs_hops.csv"))
    to_csv(c, os.path.join(RESULTS_DIR, "cluster.csv"))
    to_csv(d, os.path.join(RESULTS_DIR, "adaptive.csv"))

    out = []
    out.append("# Mesh-voice simulation results\n")
    out.append("_Generated by `python3 run_sweep.py`. QoS target: p95 mouth-to-ear "
               f"<= {QOS.max_p95_ms:.0f} ms and loss <= {QOS.max_loss*100:.0f}%. "
               f"Per-packet overhead {OVERHEAD:.0f} B; jitter buffer {SIM.jitter_buffer_ms:.0f} ms._\n")
    out.append("\n## A. Single-relay concurrent-call capacity\n\n```\n" + text_table(a) + "```\n")
    out.append("\n## B. Per-hop mouth-to-ear latency (one call, Lyra 9.2k, classic BLE)\n\n```\n" + text_table(b) + "```\n")
    out.append("\n## C. Random-geometric cluster capacity (24 nodes)\n\n```\n" + text_table(c) + "```\n")
    out.append("\n## D. Adaptive bitrate vs fixed on a loaded relay (classic BLE)\n\n```\n" + text_table(d) + "```\n")
    summary = "".join(out)

    with open(os.path.join(RESULTS_DIR, "summary.md"), "w") as f:
        f.write(summary)

    print(summary)


if __name__ == "__main__":
    main()
