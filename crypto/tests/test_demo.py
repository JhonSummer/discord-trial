"""Smoke test for the runnable Phase 1 deliverable demo (``crypto/demo.py``)."""

from demo import run_demo


def test_demo_runs_the_full_deliverable():
    r = run_demo(verbose=False)
    assert r["safety_number_match"]
    assert r["alice_to_bob_ok"]
    assert r["bob_to_alice_ok"]
    assert r["group_delivered_ok"]
    assert r["evicted_member_blocked"]
    assert r["relay_saw_plaintext"] is False
    assert r["relay_posted"] == r["relay_delivered"] == 6
