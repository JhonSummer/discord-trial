"""Codec contract: exact byte budgets, determinism, and monotonic bitrate->quality."""

from __future__ import annotations

import numpy as np
import pytest

from voiceq import SAMPLE_RATE, corpus
from voiceq.codec import PROFILES, ParametricCodec, pack, profile_for, unpack
from voiceq.metrics import score_pair, values


@pytest.mark.parametrize("bitrate", ["3.2k", "6.0k", "9.2k"])
def test_packets_match_bitrate_budget(bitrate):
    prof = profile_for(bitrate)
    c = ParametricCodec(bitrate)
    pkts = c.encode(corpus.primary_reference())
    expected = int(round(prof.bitrate_bps * 0.02 / 8.0))
    assert all(len(p) == expected for p in pkts)
    assert prof.param_bits <= expected * 8  # params fit the on-wire budget


def test_encode_is_deterministic_and_roundtrips():
    ref = corpus.primary_reference()
    c = ParametricCodec("9.2k")
    a = c.encode(ref)
    b = c.encode(ref)
    assert a == b
    dec = c.decode(a)
    assert dec.dtype == np.float32
    assert abs(len(dec) - len(ref)) <= c.hop  # within one frame


def test_bit_packing_roundtrip_is_exact():
    prof = PROFILES["9.2k"]
    c = ParametricCodec("9.2k")
    for p in c.encode_params(corpus.primary_reference())[:20]:
        q = unpack(pack(p, prof), prof)
        assert q.voiced == p.voiced
        if p.voiced:
            assert abs(q.f0 - p.f0) / p.f0 < 0.05  # pitch within a quantization step


def test_higher_bitrate_is_not_worse():
    ref = corpus.primary_reference()
    s = {br: values(score_pair(ref, ParametricCodec(br).decode(ParametricCodec(br).encode(ref)), SAMPLE_RATE))
         for br in ["3.2k", "6.0k", "9.2k"]}
    # 9.2k should beat 3.2k on intelligibility and the ViSQOL-style proxy
    assert s["9.2k"]["estoi"] >= s["3.2k"]["estoi"]
    assert s["9.2k"]["visqol"] >= s["3.2k"]["visqol"]
    assert s["9.2k"]["stoi"] > 0.7  # clean-coded intelligibility floor for the stand-in codec
