import math

import pytest

from messenger.crypto.mls import Group, GroupError


def test_fresh_group_agrees_on_a_key():
    g = Group.create(4)
    assert g.all_agree()
    assert len(g.group_key(0)) == 32


def test_commit_rotates_the_group_key():
    g = Group.create(4)
    before = g.group_key(0)
    g.commit(2)
    assert g.all_agree()
    assert g.group_key(0) != before


def test_every_member_derives_the_same_key():
    g = Group.create(4)
    g.commit(1)
    keys = {g.group_key(s) for s in g.active_slots()}
    assert len(keys) == 1


def test_epoch_keys_are_all_distinct():
    g = Group.create(4)
    seen = {g.group_key(0)}
    for slot in (1, 2, 3, 0, 1, 2):
        g.commit(slot)
        seen.add(g.group_key(0))
    assert len(seen) == 7  # initial + six commits, no repeats (forward secrecy chain)


def test_add_member_rekeys_and_includes_newcomer():
    g = Group.create(3)  # size 4 -> one free slot
    before = g.group_key(0)
    slot, _commit = g.add()
    assert g.all_agree()
    assert g.group_key(slot) == g.group_key(0)
    assert g.group_key(0) != before


def test_full_group_cannot_add():
    g = Group.create(4)
    with pytest.raises(GroupError):
        g.add()


def test_removed_member_is_excluded_from_new_epoch():
    g = Group.create(4)
    before = g.group_key(1)
    victim, _commit = g.remove(2)
    assert g.all_agree()
    assert victim.active is False
    assert victim.group_key != g.group_key(0)  # stale key, cannot follow forward
    assert g.group_key(1) != before


def test_remaining_members_still_converge_after_removal():
    g = Group.create(4)
    g.remove(3)
    g.commit(1)
    assert g.all_agree()
    assert set(g.active_slots()) == {0, 1, 2}


def test_steady_state_commit_is_logarithmic():
    g = Group.create(8)
    for s in range(8):
        g.commit(s)  # populate every internal node
    c = g.commit(0)
    assert g.all_agree()
    assert c.ciphertext_count <= math.ceil(math.log2(8))  # O(log N), not O(N)


def test_non_power_of_two_membership():
    g = Group.create(5)  # size 8, slots 0..4 active
    assert set(g.active_slots()) == {0, 1, 2, 3, 4}
    assert g.all_agree()
