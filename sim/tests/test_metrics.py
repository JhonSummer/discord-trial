import math

import pytest

from meshvoice.metrics import percentile


def test_percentile_basic():
    xs = list(range(0, 101))
    assert percentile(xs, 0) == 0
    assert percentile(xs, 100) == 100
    assert percentile(xs, 50) == pytest.approx(50.0)
    assert percentile(xs, 95) == pytest.approx(95.0)


def test_percentile_interpolation():
    assert percentile([10.0, 20.0], 50) == pytest.approx(15.0)


def test_percentile_single_and_empty():
    assert percentile([7.0], 95) == 7.0
    assert math.isnan(percentile([], 50))


def test_percentile_invalid():
    with pytest.raises(ValueError):
        percentile([1.0], 150)
