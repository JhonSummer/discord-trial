"""Mesh-frame loss masks and the quality gate. Audio metrics run in run_quality.py."""

import hashlib
import json
import os

import pytest

from quality.channel import (
    BITRATES,
    CONDITIONS,
    all_masks,
    condition_by_name,
    loss_pattern_flag,
    mask_from_pattern,
    simulate,
)
from quality.gate import evaluate, load_thresholds, passes
from quality.run_quality import read_csv
from quality.speech import FIXTURE_SHA256, N_FRAMES, N_SAMPLES, fixture_path, load_pcm16


def test_fixture_matches_pinned_waveform():
    assert os.path.isfile(fixture_path())
    digest = hashlib.sha256(open(fixture_path(), "rb").read()).hexdigest()
    assert digest == FIXTURE_SHA256
    pcm = load_pcm16()
    assert len(pcm) == N_SAMPLES * 2


def test_clean_path_plays_every_frame():
    received, meta = simulate(condition_by_name("clean"), 9200, N_FRAMES)
    assert received == [True] * N_FRAMES
    assert meta["frames_lost"] == 0
    assert meta["lost_late"] == 0
    assert 20.0 < meta["sim_mte_p95_ms"] < 150.0


def test_loss_pattern_round_trips_every_condition():
    for bitrate in BITRATES:
        for condition in CONDITIONS:
            received, meta = simulate(condition, bitrate, n_frames=200)
            pattern = loss_pattern_flag(received)
            assert mask_from_pattern(200, pattern) == received
            assert meta["frames"] == 200
            assert meta["frames_lost"] == received.count(False)


def test_residual_loss_and_hops_move_the_mask():
    one_hop, one_meta = simulate(condition_by_name("loss_5pct"), 3200, n_frames=400)
    assert one_meta["lost_random"] == one_hop.count(False)
    assert one_meta["loss_fraction"] == pytest.approx(0.05, abs=0.03)

    hop3, hop3_meta = simulate(condition_by_name("hop3"), 3200, n_frames=400)
    hop5, hop5_meta = simulate(condition_by_name("hop5"), 3200, n_frames=400)
    assert hop5_meta["frames_lost"] > hop3_meta["frames_lost"]
    assert hop3.count(False) == hop3_meta["frames_lost"]


def test_tight_jitter_buffer_drops_late_frames_and_a_wide_one_does_not():
    tight, tight_meta = simulate(condition_by_name("jitter_tight"), 3200, n_frames=200)
    assert tight_meta["lost_late"] > 0
    assert tight_meta["lost_random"] == 0
    assert tight.count(False) == tight_meta["lost_late"]

    clean, clean_meta = simulate(condition_by_name("clean"), 3200, n_frames=200)
    assert clean_meta["lost_late"] == 0
    assert all(clean)


def test_loaded_relay_congests_9200_and_passes_3200():
    # Overload is about 12% at 9.2 kbps, so the 500 ms queue limit is only
    # crossed on the full 12 s fixture, not on a short clip.
    heavy, heavy_meta = simulate(condition_by_name("relay_load"), 9200, n_frames=600)
    light, light_meta = simulate(condition_by_name("relay_load"), 3200, n_frames=600)
    assert heavy_meta["lost_congestion"] > 0
    assert heavy.count(False) == heavy_meta["frames_lost"]
    assert light_meta["lost_congestion"] == 0


def test_gate_requires_every_metric_and_every_cell():
    thresholds = {
        "calibrated": True,
        "gates": {
            "clean": {"3200": {"min_visqol": 3.0, "min_dnsmos_ovrl": 2.5, "min_stoi": 0.8}},
        },
    }
    good = {"condition": "clean", "bitrate": "3200", "visqol_mos": 3.2, "dnsmos_ovrl": 2.7, "stoi": 0.9}
    assert passes(good, thresholds)
    assert evaluate([good], thresholds) == []

    short = dict(good, stoi=0.5)
    assert not passes(short, thresholds)
    failures = evaluate([short], thresholds)
    assert any("stoi" in failure for failure in failures)

    assert evaluate([], thresholds) == ["gated cells missing from the result table: clean @ 3200"]
    assert evaluate([good], {"calibrated": False, "gates": {}}) == ["thresholds.json is not calibrated"]


def test_delay_alignment_reports_positive_lag_when_degraded_is_late():
    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    from quality.score import align_delay, apply_delay

    rng = np.random.default_rng(0)
    reference = rng.normal(size=8000)
    delay = 320
    degraded = np.concatenate([np.zeros(delay), reference[:-delay]])
    found = align_delay(reference, degraded, max_lag=640)
    assert found == delay
    aligned_ref, aligned_deg = apply_delay(reference, degraded, found)
    assert np.allclose(aligned_ref, aligned_deg)

    early = np.concatenate([reference[delay:], np.zeros(delay)])
    assert align_delay(reference, early, max_lag=640) == -delay


def test_committed_masks_match_the_simulator():
    path = os.path.join(os.path.dirname(__file__), "..", "quality", "results", "masks.json")
    with open(path, encoding="utf-8") as fh:
        committed = json.load(fh)
    assert committed == all_masks()


def test_committed_quality_table_meets_gate():
    results = os.path.join(os.path.dirname(__file__), "..", "quality", "results", "quality.csv")
    rows = read_csv(results)
    thresholds = load_thresholds()
    assert thresholds["calibrated"] is True
    assert evaluate(rows, thresholds) == []
    assert all(row["passes_gate"] == "yes" for row in rows)
