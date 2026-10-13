"""Phase 2 — moving frames across transports.

``MeshRouter`` is the transport-agnostic flood/TTL/dedup/store-and-forward core; ``MeshNode``
adds the event DAG and anti-entropy. The concrete Bluetooth GATT binding lives in ``ble`` and is
verified headless against Bumble's emulated stack in ``emulation`` / ``tests``.
"""

from .node import MeshNode
from .router import MeshRouter

__all__ = ["MeshRouter", "MeshNode"]
