"""Phase 2 — the wire format both transports carry.

The same signed, content-opaque ``Envelope`` rides either transport, wrapped in a ``Frame`` for
each mesh hop. The ``EventDAG`` gives causal, deterministic ordering and set-reconciliation so
diverged devices converge; the CRDTs do the same for non-message metadata. Nothing in this layer
can read message content — it only carries, orders, and reconciles opaque ciphertext.
"""

from .crdt import LWWRegister, ORSet
from .dag import EventDAG
from .envelope import EPOCH_MS, Envelope, Snowflake, make_envelope
from .frame import DEFAULT_TTL, Frame

__all__ = [
    "Envelope", "Snowflake", "make_envelope", "EPOCH_MS",
    "Frame", "DEFAULT_TTL",
    "EventDAG",
    "LWWRegister", "ORSet",
]
