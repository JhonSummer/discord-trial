"""Foundational checks: the reference synth is deterministic and the metrics behave sanely."""

from __future__ import annotations

import numpy as np
import pytest

from voiceq import SAMPLE_RATE
from voiceq import corpus
from voiceq.metrics import availability, score_pair, values
from voiceq.reference import clean_reference


def test_reference_is_deterministic_and_well_formed():
    a = clean_reference()
    b = clean_reference()
    assert a.dtype == np.float32
    assert np.array_equal(a, b)  # pure function of its seed
    assert SAMPLE_RATE * 3 < len(a) < SAMPLE_RATE * 12
    assert 0.0 < float(np.max(np.abs(a))) <= 1.0


def test_vendored_speech_fixtures_present():
    assert corpus.available(), "real-speech fixtures missing; run voice/tools/vendor_speech.py"
    ref = corpus.primary_reference()
    assert ref.dtype == np.float32 and len(ref) > SAMPLE_RATE  # at least a second


def test_all_metric_backends_available():
    # The committed gate requires the full metric set; a partial environment is a setup bug.
    assert availability() == {"stoi": True, "pesq": True, "visqol": True, "dnsmos": True, "plcmos": True}


def test_self_scores_hit_ceilings():
    ref = corpus.primary_reference()
    v = values(score_pair(ref, ref, SAMPLE_RATE))
    assert v["stoi"] > 0.99
    assert v["pesq"] > 4.5
    assert v["visqol"] > 4.9
    assert v["dnsmos_ovrl"] > 3.0  # real clean speech ceiling
    assert v["plcmos"] > 4.0


def test_degradation_lowers_full_reference_scores():
    ref = corpus.primary_reference()
    rng = np.random.default_rng(0)
    deg = (ref + 0.03 * rng.standard_normal(len(ref)).astype(np.float32)).astype(np.float32)
    v = values(score_pair(ref, deg, SAMPLE_RATE))
    assert v["stoi"] < 0.99
    assert v["pesq"] < 4.5
    assert v["visqol"] < 5.0
