"""Frame: the mesh hop unit.

A frame wraps an opaque ``payload`` (a serialized, encrypted ``Envelope``) with a hop-budget
``ttl``. The mesh never parses the payload. Dedup is by a content-addressed ``msg_id`` =
SHA-256(payload) truncated — recomputed on receipt, so a relay cannot forge an id to poison
another node's dedup cache or evict a real message.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from cryptocore.primitives import sha256

from .wire import pack, unpack

MSG_ID_LEN = 16
DEFAULT_TTL = 7  # hops; BLE meshes are shallow, so a small budget covers realistic diameters


@dataclass(frozen=True)
class Frame:
    ttl: int
    payload: bytes

    @property
    def msg_id(self) -> bytes:
        return sha256(self.payload)[:MSG_ID_LEN]

    @property
    def alive(self) -> bool:
        return self.ttl > 0

    def hop(self) -> "Frame":
        """The frame as a relay forwards it: one less hop of budget."""
        return Frame(self.ttl - 1, self.payload)

    def to_bytes(self) -> bytes:
        return b"\xf1" + struct.pack(">B", max(0, min(self.ttl, 0xFF))) + pack(self.payload)

    @classmethod
    def from_bytes(cls, buf: bytes) -> "Frame":
        if buf[:1] != b"\xf1":
            raise ValueError("unknown frame version")
        ttl = buf[1]
        payload, _ = unpack(buf, 2)
        return cls(ttl, payload)
