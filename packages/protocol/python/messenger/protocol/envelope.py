"""The Envelope: the unit both transports carry.

Signed by the author, content-opaque to every relay/mesh node (the ``ciphertext`` is E2EE
payload the carriers cannot read), and causally linked via ``prev`` parents for the DAG.
Snowflake IDs are time-sortable and generable offline, which the offline-first model needs.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

from messenger.crypto.identity import IdentityKeyPair, PublicIdentity
from messenger.crypto.primitives import sha256

from .wire import pack as _pack, unpack as _unpack

EPOCH_MS = 1_704_067_200_000  # 2024-01-01T00:00:00Z


class Snowflake:
    """64-bit time-ordered IDs: 42-bit ms timestamp | 10-bit node | 12-bit sequence."""

    def __init__(self, node_id: int):
        self.node_id = node_id & 0x3FF
        self.seq = 0
        self.last = 0

    def next(self, now_ms: Optional[int] = None) -> int:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        if now <= self.last:
            now = self.last  # clamp up: never emit a timestamp below the high-water mark,
            self.seq = (self.seq + 1) & 0xFFF  # so ids stay monotonic even if the clock drifts back
            if self.seq == 0:
                now = self.last + 1  # sequence exhausted this ms; roll into the next
        else:
            self.seq = 0
        self.last = now
        return ((now - EPOCH_MS) << 22) | (self.node_id << 12) | self.seq

    @staticmethod
    def timestamp_ms(eid: int) -> int:
        return (eid >> 22) + EPOCH_MS


@dataclass
class Envelope:
    eid: int
    room: bytes
    sender: bytes               # author identity fingerprint (32 bytes)
    prev: Tuple[int, ...]       # causal parents
    epoch: int                  # group key epoch
    ciphertext: bytes           # opaque to relays/mesh
    sig: bytes = b""

    def body(self) -> bytes:
        parents = struct.pack(">H", len(self.prev)) + b"".join(struct.pack(">Q", p) for p in self.prev)
        return (
            b"\x01"
            + struct.pack(">Q", self.eid)
            + struct.pack(">q", self.epoch)
            + _pack(self.room)
            + _pack(self.sender)
            + _pack(parents)
            + _pack(self.ciphertext)
        )

    def to_bytes(self) -> bytes:
        return self.body() + _pack(self.sig)

    @classmethod
    def from_bytes(cls, buf: bytes) -> "Envelope":
        if buf[:1] != b"\x01":
            raise ValueError("unknown envelope version")
        off = 1
        (eid,) = struct.unpack_from(">Q", buf, off); off += 8
        (epoch,) = struct.unpack_from(">q", buf, off); off += 8
        room, off = _unpack(buf, off)
        sender, off = _unpack(buf, off)
        parents_raw, off = _unpack(buf, off)
        ciphertext, off = _unpack(buf, off)
        sig, off = _unpack(buf, off)
        (count,) = struct.unpack_from(">H", parents_raw, 0)
        prev = tuple(struct.unpack_from(">Q", parents_raw, 2 + 8 * i)[0] for i in range(count))
        return cls(eid, room, sender, prev, epoch, ciphertext, sig)

    def verify(self, author: PublicIdentity) -> bool:
        return author.fingerprint == self.sender and author.verify(self.sig, self.body())


def make_envelope(author: IdentityKeyPair, room: bytes, prev, epoch: int,
                  ciphertext: bytes, snowflake: Snowflake) -> Envelope:
    env = Envelope(
        eid=snowflake.next(),
        room=room,
        sender=author.public.fingerprint,
        prev=tuple(prev),
        epoch=epoch,
        ciphertext=ciphertext,
    )
    env.sig = author.sign(env.body())
    return env
