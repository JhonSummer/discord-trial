"""TreeKEM-style group key agreement (MLS-inspired) for E2EE group chat.

Members sit at the leaves of a left-balanced binary tree (here a perfect tree over a
power-of-two number of leaf slots, so heap indexing is exact). A commit rotates the
committer's leaf and its direct path, encrypting each path secret to the *resolution* of the
copath so every other member can re-derive the shared root secret. Properties this gives us:

- **Group agreement:** after a commit every current member derives the same group key.
- **Forward secrecy across epochs:** epoch keys chain through one-way HKDF, so a leaked epoch
  key reveals nothing about earlier epochs.
- **Post-compromise security & removal:** a removed member's leaf+path are blanked and the
  tree re-keyed, so it cannot derive the next epoch key.
- **Logarithmic updates in steady state:** once the tree is populated, a commit encrypts to
  O(log N) intermediate node keys rather than to every member.

Reference prototype of the TreeKEM *idea*, not RFC 9420 wire-compatible and not audited;
production should use a conformant MLS stack (e.g. OpenMLS).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .primitives import aead_decrypt, aead_encrypt, hkdf


class GroupError(Exception):
    pass


def _raw(priv: X25519PrivateKey) -> bytes:
    return priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _priv_from_secret(secret: bytes) -> X25519PrivateKey:
    return X25519PrivateKey.from_private_bytes(hkdf(secret, 32, info=b"treekem/node"))


def _next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p <<= 1
    return p


def _hpke_seal(recipient_pub: bytes, plaintext: bytes) -> bytes:
    eph = X25519PrivateKey.generate()
    shared = eph.exchange(X25519PublicKey.from_public_bytes(recipient_pub))
    key = hkdf(shared, 32, info=b"treekem/hpke")
    nonce, ct = aead_encrypt(key, plaintext)
    return _raw(eph) + nonce + ct


def _hpke_open(recipient_priv: X25519PrivateKey, blob: bytes) -> bytes:
    eph_pub, nonce, ct = blob[:32], blob[32:44], blob[44:]
    shared = recipient_priv.exchange(X25519PublicKey.from_public_bytes(eph_pub))
    key = hkdf(shared, 32, info=b"treekem/hpke")
    return aead_decrypt(key, nonce, ct)


@dataclass
class Commit:
    committer: int
    epoch: int
    leaf_pub: bytes
    path_pub: Dict[int, bytes]
    ciphertexts: Dict[int, List[Tuple[int, bytes]]]

    @property
    def ciphertext_count(self) -> int:
        return sum(len(v) for v in self.ciphertexts.values())


class GroupMember:
    """One member's private view of the ratchet tree + epoch secrets."""

    def __init__(self, slot: int, size: int):
        self.slot = slot
        self.size = size
        self.leaf_priv = X25519PrivateKey.generate()
        self.node_pub: Dict[int, bytes] = {}
        self.known_priv: Dict[int, X25519PrivateKey] = {}
        self.epoch = 0
        self.init_secret = b"\x00" * 32
        self.group_key = b""
        self.active = True

    # --- tree helpers (perfect tree, heap layout; leaves at [size, 2*size)) ---
    def leaf(self, slot: int) -> int:
        return self.size + slot

    def _direct_path(self, leaf: int) -> List[int]:
        node = leaf
        path = []
        while node > 1:
            node //= 2
            path.append(node)
        return path

    def _resolution(self, idx: int) -> List[int]:
        if self.node_pub.get(idx) is not None:
            return [idx]
        if idx >= self.size:  # blank leaf
            return []
        return self._resolution(2 * idx) + self._resolution(2 * idx + 1)

    def _derive_epoch(self, root_secret: bytes) -> None:
        commit_secret = hkdf(root_secret, 32, info=b"treekem/commit")
        epoch_secret = hkdf(commit_secret, 32, salt=self.init_secret, info=b"treekem/epoch")
        self.group_key = hkdf(epoch_secret, 32, info=b"treekem/app")
        self.init_secret = hkdf(epoch_secret, 32, info=b"treekem/init")
        self.epoch += 1

    def commit(self) -> Commit:
        if not self.active:
            raise GroupError("inactive member cannot commit")
        leaf = self.leaf(self.slot)
        path = self._direct_path(leaf)

        leaf_secret = os.urandom(32)
        self.leaf_priv = _priv_from_secret(leaf_secret)
        self.node_pub[leaf] = _raw(self.leaf_priv)
        self.known_priv[leaf] = self.leaf_priv

        secrets = []
        cur = hkdf(leaf_secret, 32, info=b"treekem/path")
        for _ in path:
            secrets.append(cur)
            cur = hkdf(cur, 32, info=b"treekem/path")

        on_path_children = [leaf] + path[:-1]
        path_pub: Dict[int, bytes] = {}
        ciphertexts: Dict[int, List[Tuple[int, bytes]]] = {}
        for k, node in enumerate(path):
            s_k = secrets[k]
            node_priv = _priv_from_secret(s_k)
            self.node_pub[node] = _raw(node_priv)
            self.known_priv[node] = node_priv
            path_pub[node] = self.node_pub[node]
            sibling = on_path_children[k] ^ 1
            encs = [(res, _hpke_seal(self.node_pub[res], s_k)) for res in self._resolution(sibling)]
            ciphertexts[node] = encs

        root_secret = secrets[-1]
        commit = Commit(self.slot, self.epoch, self.node_pub[leaf], path_pub, ciphertexts)
        self._derive_epoch(root_secret)
        return commit

    def process_commit(self, commit: Commit) -> None:
        if not self.active:
            raise GroupError("inactive member cannot process commits")
        committer_leaf = self.leaf(commit.committer)
        self.node_pub[committer_leaf] = commit.leaf_pub
        for node, pub in commit.path_pub.items():
            self.node_pub[node] = pub

        if commit.committer == self.slot:
            return  # already applied in commit()

        a, b = committer_leaf, self.leaf(self.slot)
        while a != b:
            a //= 2
            b //= 2
        lca = a  # committer path node whose ciphertext we can open

        entry = commit.ciphertexts.get(lca)
        if not entry:
            raise GroupError("no ciphertext at meeting node; tree views diverged")
        secret = None
        for res_idx, blob in entry:
            priv = self.known_priv.get(res_idx)
            if priv is not None:
                secret = _hpke_open(priv, blob)
                break
        if secret is None:
            raise GroupError("member cannot open any copath ciphertext")

        node = lca
        s = secret
        while True:
            self.known_priv[node] = _priv_from_secret(s)
            if node == 1:
                break
            node //= 2
            s = hkdf(s, 32, info=b"treekem/path")
        root_secret = s
        self._derive_epoch(root_secret)


class Group:
    """In-process coordinator used to build groups and route commits for tests/demos."""

    def __init__(self, size: int):
        self.size = size
        self.members: List[Optional[GroupMember]] = [None] * size

    @classmethod
    def create(cls, n: int) -> "Group":
        size = _next_pow2(max(n, 2))
        g = cls(size)
        for slot in range(n):
            g.members[slot] = GroupMember(slot, size)
        # publish everyone's leaf public key into every member's view
        leaf_pubs = {g.members[s].leaf(s): _raw(g.members[s].leaf_priv) for s in range(n)}
        for s in range(n):
            g.members[s].node_pub.update(leaf_pubs)
            g.members[s].known_priv[g.members[s].leaf(s)] = g.members[s].leaf_priv
        g.commit(0)  # founder establishes the first epoch key
        return g

    def active_slots(self) -> List[int]:
        return [s for s, m in enumerate(self.members) if m and m.active]

    def commit(self, slot: int) -> Commit:
        committer = self.members[slot]
        if committer is None:
            raise GroupError("no such member")
        commit = committer.commit()
        for s in self.active_slots():
            if s != slot:
                self.members[s].process_commit(commit)
        return commit

    def group_key(self, slot: int) -> bytes:
        return self.members[slot].group_key

    def all_agree(self) -> bool:
        keys = {self.members[s].group_key for s in self.active_slots()}
        return len(keys) == 1 and b"" not in keys

    def _blank_path(self, leaf: int, include_leaf: bool = True) -> None:
        # Blank the ancestor path so the next commit re-keys it. For a *removal* the leaf
        # itself is blanked too; for an *add* the new leaf must stay published so the
        # committer can seal the fresh path secret to it (otherwise the newcomer is excluded).
        nodes = self.members[self.active_slots()[0]]._direct_path(leaf)
        if include_leaf:
            nodes = [leaf] + nodes
        for s in self.active_slots():
            m = self.members[s]
            for nd in nodes:
                m.node_pub.pop(nd, None)
                m.known_priv.pop(nd, None)

    def add(self, adder: int = 0) -> Tuple[int, Commit]:
        free = next((s for s, m in enumerate(self.members) if m is None), None)
        if free is None:
            raise GroupError("group is full (grow not supported in this prototype)")
        newm = GroupMember(free, self.size)
        self.members[free] = newm
        leaf = newm.leaf(free)
        new_leaf_pub = _raw(newm.leaf_priv)
        # welcome: new member receives the public tree snapshot
        snapshot = dict(self.members[adder].node_pub)
        newm.node_pub.update(snapshot)
        newm.init_secret = self.members[adder].init_secret
        newm.epoch = self.members[adder].epoch
        newm.known_priv[leaf] = newm.leaf_priv
        for s in self.active_slots():
            self.members[s].node_pub[leaf] = new_leaf_pub
        self._blank_path(leaf, include_leaf=False)  # keep the newcomer's leaf visible to the committer
        commit = self.commit(adder)  # re-key so the new member derives the epoch secret
        return free, commit

    def remove(self, slot: int, remover: int = 0) -> Tuple[GroupMember, Commit]:
        victim = self.members[slot]
        if victim is None or slot == remover:
            raise GroupError("invalid removal")
        leaf = victim.leaf(slot)
        self._blank_path(leaf)
        victim.active = False
        self.members[slot] = None
        for s in self.active_slots():
            self.members[s].node_pub.pop(leaf, None)
        commit = self.commit(remover)
        return victim, commit
