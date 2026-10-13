"""Fragmentation / reassembly for frames that exceed the ATT MTU.

A GATT write or notification carries at most ``MTU - 3`` bytes, and the guaranteed-minimum MTU is
23, so a mesh frame (easily >100 bytes once it holds a signed envelope) must be split. Each
logical message is length-prefixed and chunked; the receiver streams chunks back into whole
messages. GATT writes/notifications over one connection are ordered and reliable, so a plain
length-prefixed byte-stream reassembler is sufficient — on real radios add retry/timeout, over the
emulated stack delivery is lossless.
"""

from __future__ import annotations

import struct
from typing import Callable, Iterator

ATT_DEFAULT_MTU = 23
ATT_OPCODE_OVERHEAD = 3
# Writing chunks this size is valid at the minimum MTU, so it always works regardless of any MTU
# negotiation — the mesh fragments to it rather than depending on a larger negotiated MTU.
DEFAULT_CHUNK = ATT_DEFAULT_MTU - ATT_OPCODE_OVERHEAD  # 20
LENGTH_PREFIX = 4


def fragment(message: bytes, chunk: int = DEFAULT_CHUNK) -> Iterator[bytes]:
    framed = struct.pack(">I", len(message)) + message
    for i in range(0, len(framed), chunk):
        yield framed[i:i + chunk]


class Reassembler:
    """Feed ordered chunks for one link direction; invokes ``on_message`` per whole message."""

    def __init__(self, on_message: Callable[[bytes], None]) -> None:
        self._buf = bytearray()
        self._on_message = on_message

    def feed(self, chunk: bytes) -> None:
        self._buf += chunk
        while len(self._buf) >= LENGTH_PREFIX:
            (n,) = struct.unpack_from(">I", self._buf, 0)
            if len(self._buf) < LENGTH_PREFIX + n:
                break
            message = bytes(self._buf[LENGTH_PREFIX:LENGTH_PREFIX + n])
            del self._buf[:LENGTH_PREFIX + n]
            self._on_message(message)
