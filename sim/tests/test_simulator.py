import math

import pytest

from meshvoice.codec import LYRA_V2_3200, LYRA_V2_9200
from meshvoice.metrics import summarize
from meshvoice.network import Graph, LinkParams, line
from meshvoice.scenarios import make_calls, shared_relay
from meshvoice.simulator import Call, SimParams, Simulator


def _single_link(capacity=37_500.0, ci=0.0, per=0.0):
    g = Graph()
    g.add_link(0, 1, LinkParams(capacity_bps=capacity, connection_interval_ms=ci, per=per))
    return g


def test_single_stream_latency_matches_hand_calc():
    g = _single_link(ci=0.0)
    call = Call(0, [0, 1], LYRA_V2_9200, overhead_bytes=0.0)
    params = SimParams(duration_s=2.0, encode_ms=10.0, decode_ms=5.0, jitter_buffer_ms=60.0, seed=1)
    res = Simulator(g, [call], params).run()

    service_ms = (LYRA_V2_9200.packet_bits() / 37_500.0) * 1000.0  # ~4.9 ms
    expected_mte = 20.0 + 10.0 + service_ms + 5.0  # interval + encode + net + decode

    agg = summarize(res)
    assert res.total_lost == 0
    assert agg.delivered_on_time == agg.generated
    assert agg.mte_p50_ms == pytest.approx(expected_mte, abs=0.5)
    assert agg.mte_p95_ms == pytest.approx(expected_mte, abs=0.5)


def test_latency_grows_with_hops():
    params = SimParams(duration_s=2.0, jitter_buffer_ms=200.0, seed=2)
    p50s = []
    for hops in (1, 2, 4, 6):
        g = line(hops + 1, LinkParams(capacity_bps=37_500.0, connection_interval_ms=0.0))
        calls = make_calls([list(range(hops + 1))], LYRA_V2_9200, seed=0)
        agg = summarize(Simulator(g, calls, params).run())
        p50s.append(agg.mte_p50_ms)
    assert all(b > a for a, b in zip(p50s, p50s[1:]))  # strictly increasing


def test_below_capacity_is_lossless_above_is_not():
    params = SimParams(duration_s=6.0, jitter_buffer_ms=60.0, seed=3)

    g, calls = shared_relay(3, LYRA_V2_9200, LinkParams(capacity_bps=37_500.0, connection_interval_ms=0.0),
                            overhead_bytes=0.0, seed=3)
    low = summarize(Simulator(g, calls, params).run())
    assert low.loss_fraction == pytest.approx(0.0, abs=1e-9)
    assert low.lost_congestion == 0

    g, calls = shared_relay(6, LYRA_V2_9200, LinkParams(capacity_bps=37_500.0, connection_interval_ms=0.0),
                            overhead_bytes=0.0, seed=3)
    high = summarize(Simulator(g, calls, params).run())
    assert high.loss_fraction > 0.05
    assert high.lost_congestion > 0
    assert high.max_link_utilization > 0.98


def test_random_loss_statistics():
    per = 0.1
    g = _single_link(ci=0.0, per=per)
    call = Call(0, [0, 1], LYRA_V2_9200)
    params = SimParams(duration_s=40.0, jitter_buffer_ms=1000.0, seed=123)
    res = Simulator(g, [call], params).run()
    observed = res.lost_random / res.generated
    assert observed == pytest.approx(per, abs=0.02)
    assert res.lost_congestion == 0


def test_jitter_buffer_late_loss():
    # Connection-interval access creates up to one CI of arrival jitter even for a single
    # unloaded call; a tiny jitter buffer drops the late packets, a large one absorbs them.
    g = _single_link(capacity=37_500.0, ci=15.0, per=0.0)
    call = Call(0, [0, 1], LYRA_V2_3200, overhead_bytes=0.0)
    params_tiny = SimParams(duration_s=6.0, jitter_buffer_ms=1.0, seed=7)
    params_big = SimParams(duration_s=6.0, jitter_buffer_ms=1000.0, seed=7)

    tiny = summarize(Simulator(g, [call], params_tiny).run())
    big = summarize(Simulator(g, [call], params_big).run())

    assert tiny.lost_late > 0
    assert tiny.lost_congestion == 0  # it's jitter, not saturation
    assert big.lost_late == 0
    assert big.loss_fraction == pytest.approx(0.0, abs=1e-9)


def test_connection_interval_bounds_delay():
    ci = 20.0
    g = _single_link(ci=ci)
    call = Call(0, [0, 1], LYRA_V2_9200)
    params = SimParams(duration_s=3.0, jitter_buffer_ms=200.0, seed=9)
    res = Simulator(g, [call], params).run()
    net_delays_ms = [dp.network_delay_s * 1000.0 for dp in res.delivered]
    service_ms = (LYRA_V2_9200.packet_bits() / 37_500.0) * 1000.0
    assert min(net_delays_ms) >= 0.0
    # one hop: at most one connection-interval wait plus one serialization
    assert max(net_delays_ms) <= ci + service_ms + 1e-6


def test_determinism_same_seed():
    g, calls = shared_relay(4, LYRA_V2_9200, LinkParams(capacity_bps=37_500.0, connection_interval_ms=15.0, per=0.01),
                            overhead_bytes=12.0, seed=5)
    params = SimParams(duration_s=4.0, seed=5)
    a = summarize(Simulator(g, calls, params).run())

    g, calls = shared_relay(4, LYRA_V2_9200, LinkParams(capacity_bps=37_500.0, connection_interval_ms=15.0, per=0.01),
                            overhead_bytes=12.0, seed=5)
    b = summarize(Simulator(g, calls, params).run())

    assert a == b


def test_missing_link_raises():
    g = _single_link()
    bad = Call(0, [0, 1, 2], LYRA_V2_9200)  # link 1->2 does not exist
    with pytest.raises(ValueError):
        Simulator(g, [bad])


def test_overhead_reduces_delivered_capacity():
    params = SimParams(duration_s=4.0, jitter_buffer_ms=60.0, seed=3)
    link = LinkParams(capacity_bps=37_500.0, connection_interval_ms=0.0)

    g, calls = shared_relay(8, LYRA_V2_3200, link, overhead_bytes=0.0, seed=3)
    no_oh = summarize(Simulator(g, calls, params).run())
    g, calls = shared_relay(8, LYRA_V2_3200, link, overhead_bytes=40.0, seed=3)
    with_oh = summarize(Simulator(g, calls, params).run())

    assert with_oh.loss_fraction > no_oh.loss_fraction


def test_packet_fates_partition_generated_packets():
    g = _single_link(ci=15.0, per=0.05)
    call = Call(0, [0, 1], LYRA_V2_9200, overhead_bytes=12.0)
    params = SimParams(duration_s=5.0, jitter_buffer_ms=8.0, seed=4)
    res = Simulator(g, [call], params).run()

    assert len(res.fates) == res.generated
    keys = [(f.call_id, f.packet_index) for f in res.fates]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)
    assert sum(f.outcome == "random" for f in res.fates) == res.lost_random
    assert sum(f.outcome == "congestion" for f in res.fates) == res.lost_congestion
    assert sum(f.outcome == "late" for f in res.fates) == res.lost_late
    assert sum(f.outcome == "ok" for f in res.fates) == res.generated - res.total_lost


def test_fates_and_packet_trace_agree_on_network_drops():
    # Both traces describe the same run. ``fates`` classifies jitter-buffer late loss;
    # ``packet_trace`` keeps the raw network delay so the voice harness can apply its own buffer.
    g = _single_link(ci=15.0, per=0.05)
    call = Call(0, [0, 1], LYRA_V2_9200, overhead_bytes=12.0)
    params = SimParams(duration_s=5.0, jitter_buffer_ms=8.0, seed=4, trace=True)
    res = Simulator(g, [call], params).run()

    assert res.packet_trace is not None
    trace = res.packet_trace[call.call_id]
    assert len(trace.lost) == len(res.fates) == res.generated
    assert any(f.outcome == "late" for f in res.fates)
    for fate, lost, delay in zip(res.fates, trace.lost, trace.delay_s):
        if fate.outcome in ("random", "congestion"):
            assert lost is True
            assert math.isnan(delay)
        else:
            assert fate.outcome in ("ok", "late")
            assert lost is False
            assert not math.isnan(delay)
