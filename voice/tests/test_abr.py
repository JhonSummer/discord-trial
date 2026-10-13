"""Unit tests for the adaptive-protection controller (fast; no audio / neural models)."""

from __future__ import annotations

import numpy as np

from voiceq.abr import AbrConfig, plan_protection


def test_clean_link_gets_no_protection():
    present = np.ones(300, dtype=bool)
    depth = plan_protection(present, AbrConfig())
    assert depth.max() == 0  # no loss -> never spend redundancy bits


def test_sustained_loss_ramps_to_full_depth():
    cfg = AbrConfig()
    present = np.ones(300, dtype=bool)
    present[60:] = False  # a long outage well above the `high` threshold
    depth = plan_protection(present, cfg)
    assert depth.max() == cfg.max_depth
    # ...and it reaches the deepest level only after a feedback-lagged ramp, never instantly.
    first_deep = int(np.argmax(depth == cfg.max_depth))
    assert first_deep >= 60 + cfg.lag_frames


def test_controller_is_causal():
    # A burst confined to the tail must not raise protection before it (no peeking ahead).
    cfg = AbrConfig()
    present = np.ones(400, dtype=bool)
    present[300:] = False
    depth = plan_protection(present, cfg)
    assert depth[: 300 - cfg.lag_frames].max() == 0


def test_depth_moves_one_step_at_a_time():
    cfg = AbrConfig()
    rng = np.random.default_rng(0)
    present = rng.random(500) > 0.15
    depth = plan_protection(present, cfg)
    assert np.all(np.abs(np.diff(depth)) <= 1)
    assert depth.min() >= 0 and depth.max() <= cfg.max_depth
