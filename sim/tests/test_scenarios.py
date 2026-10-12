import pytest

from meshvoice.codec import LYRA_V2_3200, LYRA_V2_9200
from meshvoice.network import LinkParams
from meshvoice.scenarios import (
    QoS, adaptive_shared_relay, analytic_capacity, breaking_point, shared_relay,
)
from meshvoice.simulator import SimParams

# Clean-room params matching the napkin math in docs/03: usable 37.5 kbps per link, no
# connection-interval or loss confounds, generous jitter buffer.
CLEAN = LinkParams(capacity_bps=37_500.0, connection_interval_ms=0.0, per=0.0)
SIM = SimParams(duration_s=10.0, encode_ms=10.0, decode_ms=5.0, jitter_buffer_ms=60.0, seed=7)
QOS = QoS(max_p95_ms=200.0, max_loss=0.02)


def test_analytic_capacity_matches_napkin_math():
    assert analytic_capacity(LYRA_V2_9200, CLEAN) == pytest.approx(37_500 / 9_200, abs=0.01)
    assert analytic_capacity(LYRA_V2_3200, CLEAN) == pytest.approx(37_500 / 3_200, abs=0.01)


def test_breaking_point_9200_is_four():
    build = lambda n: shared_relay(n, LYRA_V2_9200, CLEAN, overhead_bytes=0.0, seed=11)
    bp = breaking_point(build, QOS, SIM, n_max=20)
    assert bp == 4  # floor(37.5 / 9.2) = 4, confirming the doc's estimate


def test_breaking_point_3200_is_eleven():
    build = lambda n: shared_relay(n, LYRA_V2_3200, CLEAN, overhead_bytes=0.0, seed=11)
    bp = breaking_point(build, QOS, SIM, n_max=30)
    assert bp == 11  # floor(37.5 / 3.2) = 11, confirming the doc's estimate


def test_lower_bitrate_supports_more_calls():
    bp9 = breaking_point(lambda n: shared_relay(n, LYRA_V2_9200, CLEAN, seed=11), QOS, SIM, n_max=30)
    bp3 = breaking_point(lambda n: shared_relay(n, LYRA_V2_3200, CLEAN, seed=11), QOS, SIM, n_max=30)
    assert bp3 > bp9


def test_adaptive_beats_fixed_capacity():
    fixed = breaking_point(lambda n: shared_relay(n, LYRA_V2_9200, CLEAN, overhead_bytes=0.0, seed=11),
                           QOS, SIM, n_max=30)
    adaptive = breaking_point(lambda n: adaptive_shared_relay(n, CLEAN, overhead_bytes=0.0, seed=11),
                              QOS, SIM, n_max=30)
    assert adaptive >= fixed
    assert adaptive >= 10  # downshifting to 3.2k unlocks ~11 calls on the same link
