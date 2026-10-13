"""Summaries over a ``SimResult``: latency percentiles, loss breakdown, link utilization.

Percentiles use linear interpolation (NIST / numpy "linear" method) and are implemented in
the standard library so the simulator has no hard numpy dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .simulator import SimResult


def percentile(xs: List[float], p: float) -> float:
    if not xs:
        return float("nan")
    if not 0.0 <= p <= 100.0:
        raise ValueError("p must be in [0, 100]")
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


@dataclass
class CallSummary:
    call_id: int
    delivered_on_time: int
    lost_total: int
    loss_fraction: float
    mte_p50_ms: float
    mte_p95_ms: float
    mte_p99_ms: float


@dataclass
class AggregateSummary:
    num_calls: int
    generated: int
    delivered_on_time: int
    lost_random: int
    lost_congestion: int
    lost_late: int
    loss_fraction: float
    mte_p50_ms: float
    mte_p95_ms: float
    mte_p99_ms: float
    max_link_utilization: float
    busiest_link: Tuple[int, int]
    max_queue_ms: float

    def meets(self, max_p95_ms: float, max_loss: float) -> bool:
        if math.isnan(self.mte_p95_ms):
            return False
        return self.mte_p95_ms <= max_p95_ms and self.loss_fraction <= max_loss


def _mte_ms(result: SimResult, call_id=None) -> List[float]:
    out = []
    for dp in result.delivered:
        if dp.late:
            continue
        if call_id is not None and dp.call_id != call_id:
            continue
        out.append(dp.mouth_to_ear_s * 1000.0)
    return out


def per_call(result: SimResult) -> List[CallSummary]:
    # generated packets per call (all calls share duration/interval math via Call)
    gen_by_call: Dict[int, int] = {}
    for call in result.calls:
        interval = call.packet_interval_s
        n = 0
        k = 0
        capture = call.start_s + call.phase_s
        while capture + interval <= result.params.duration_s + 1e-9:
            n += 1
            k += 1
            capture = call.start_s + call.phase_s + k * interval
        gen_by_call[call.call_id] = n

    on_time: Dict[int, int] = {c.call_id: 0 for c in result.calls}
    for dp in result.delivered:
        if not dp.late:
            on_time[dp.call_id] += 1

    summaries = []
    for call in result.calls:
        gen = gen_by_call[call.call_id]
        ot = on_time[call.call_id]
        lost = gen - ot
        mte = _mte_ms(result, call.call_id)
        summaries.append(CallSummary(
            call_id=call.call_id,
            delivered_on_time=ot,
            lost_total=lost,
            loss_fraction=(lost / gen) if gen else 0.0,
            mte_p50_ms=percentile(mte, 50),
            mte_p95_ms=percentile(mte, 95),
            mte_p99_ms=percentile(mte, 99),
        ))
    return summaries


def summarize(result: SimResult) -> AggregateSummary:
    mte = _mte_ms(result)
    on_time = len(mte)
    loss = (result.total_lost / result.generated) if result.generated else 0.0

    busiest = (-1, -1)
    max_util = 0.0
    for key, u in result.link_utilization.items():
        if u > max_util:
            max_util = u
            busiest = key
    max_queue = max(result.link_max_queue_ms.values(), default=0.0)

    return AggregateSummary(
        num_calls=len(result.calls),
        generated=result.generated,
        delivered_on_time=on_time,
        lost_random=result.lost_random,
        lost_congestion=result.lost_congestion,
        lost_late=result.lost_late,
        loss_fraction=loss,
        mte_p50_ms=percentile(mte, 50),
        mte_p95_ms=percentile(mte, 95),
        mte_p99_ms=percentile(mte, 99),
        max_link_utilization=max_util,
        busiest_link=busiest,
        max_queue_ms=max_queue,
    )
