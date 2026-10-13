"""TreeKEM-style group key agreement: agreement, epoch rotation, add/remove, app messages."""

import pytest

from cryptocore import Group, GroupError


def test_group_create_reaches_agreement():
    g = Group.create(3)
    assert g.all_agree()
    key = g.group_key(0)
    assert key and all(g.group_key(s) == key for s in g.active_slots())


def test_commit_rotates_the_key_but_keeps_agreement():
    g = Group.create(4)
    before = g.group_key(0)
    g.commit(2)
    assert g.all_agree()
    assert g.group_key(0) != before          # epoch key advanced
    assert all(g.group_key(s) == g.group_key(0) for s in g.active_slots())


def test_group_application_message_roundtrip():
    g = Group.create(3)
    blob = g.member(0).encrypt_message(b"secret for the group")
    assert g.member(1).decrypt_message(blob) == b"secret for the group"
    assert g.member(2).decrypt_message(blob) == b"secret for the group"


def test_application_message_from_a_past_epoch_is_rejected():
    g = Group.create(3)
    blob = g.member(0).encrypt_message(b"stale")
    g.commit(1)                                  # everyone advances an epoch
    with pytest.raises(GroupError):
        g.member(2).decrypt_message(blob)        # wrong epoch


def test_add_member_then_everyone_including_newcomer_agrees():
    g = Group.create(3)
    new_slot, _ = g.add(adder=0)
    assert g.all_agree()
    blob = g.member(0).encrypt_message(b"welcome aboard")
    assert g.member(new_slot).decrypt_message(blob) == b"welcome aboard"


def test_removed_member_is_excluded_from_future_epochs():
    g = Group.create(4)
    victim, _ = g.remove(2, remover=0)
    assert g.all_agree()                         # remaining members still agree
    assert 2 not in g.active_slots()
    # The removed member holds only its stale key and cannot derive the new epoch key.
    assert victim.group_key != g.group_key(0)
    # ...and it can neither send nor read on the group any more.
    with pytest.raises(GroupError):
        victim.encrypt_message(b"still here?")
    post_removal = g.member(0).encrypt_message(b"after the removal")
    with pytest.raises(GroupError):
        victim.decrypt_message(post_removal)
    # A current member reads it fine.
    assert g.member(1).decrypt_message(post_removal) == b"after the removal"


def test_epochs_chain_forward_secretly():
    g = Group.create(3)
    epoch1_key = g.group_key(0)
    g.commit(0)
    epoch2_key = g.group_key(0)
    g.commit(1)
    epoch3_key = g.group_key(0)
    assert len({epoch1_key, epoch2_key, epoch3_key}) == 3   # every epoch key is distinct
