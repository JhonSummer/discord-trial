"""MeshNode: a device's view — router + event DAG + anti-entropy.

Posting a message links it to the DAG's current heads (causal ``prev``), signs it, and floods
it. Received envelopes are ingested into the DAG. Flooding delivers in real time while nodes are
connected; anti-entropy (``sync_with``) catches a node up after a partition by exchanging only
the events each side is missing.

A relay/mesh node cannot verify an envelope's signature for an author it doesn't know (the
envelope carries only the author's fingerprint, not their public key) — that verification
happens at the app layer once the author is a known contact. The mesh treats the ciphertext as
fully opaque.
"""

from __future__ import annotations

from typing import Optional

from cryptocore.identity import IdentityKeyPair
from messenger.protocol.dag import EventDAG
from messenger.protocol.envelope import Envelope, Snowflake, make_envelope
from messenger.protocol.frame import DEFAULT_TTL

from .router import MeshRouter


class MeshNode:
    def __init__(self, identity: IdentityKeyPair, node_id: int, *, ttl: int = DEFAULT_TTL):
        self.identity = identity
        self.snowflake = Snowflake(node_id)
        self.dag = EventDAG()
        self.router = MeshRouter(node_id, ttl=ttl)
        self.router.on_deliver = self._ingest

    def post(self, room: bytes, ciphertext: bytes, epoch: int = 0) -> Envelope:
        env = make_envelope(self.identity, room, self.dag.heads(), epoch, ciphertext, self.snowflake)
        self.dag.add(env)
        self.router.originate(env.to_bytes())
        return env

    def _ingest(self, payload: bytes) -> None:
        self.dag.add(Envelope.from_bytes(payload))

    def sync_with(self, other: "MeshNode") -> None:
        """Symmetric anti-entropy: exchange exactly the events each side lacks, then converge."""
        mine, theirs = self.dag.ids(), other.dag.ids()
        to_me = other.dag.missing_for(mine)
        to_other = self.dag.missing_for(theirs)
        self.dag.merge(to_me)
        other.dag.merge(to_other)
