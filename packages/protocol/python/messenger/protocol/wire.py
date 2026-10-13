"""Shared length-prefix framing: a big-endian uint32 length followed by that many bytes.

Deterministic and language-neutral so the TypeScript port serializes byte-for-byte the same.
"""

from __future__ import annotations

import struct
from typing import Tuple


def pack(b: bytes) -> bytes:
    return struct.pack(">I", len(b)) + b


def unpack(buf: bytes, off: int) -> Tuple[bytes, int]:
    (n,) = struct.unpack_from(">I", buf, off)
    off += 4
    return buf[off:off + n], off + n
