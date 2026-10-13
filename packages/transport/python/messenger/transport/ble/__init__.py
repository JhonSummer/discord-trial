"""Bluetooth GATT binding for the mesh transport.

The mesh is one GATT service with a single frame characteristic (write + notify). Over a single
connection the central writes frames to the peripheral's characteristic and the peripheral
notifies the central back, so one link is bidirectional. Frames are length-prefixed and fragmented
to the ATT MTU (see ``fragment``) and reassembled per link direction.

This module is the transport-agnostic GATT contract — the same UUIDs and framing the phone uses on
real radios. The headless device/connection orchestration for CI lives in the ``emulation``
harness, which drives this contract over Bumble's emulated stack.
"""

from .fragment import DEFAULT_CHUNK, Reassembler, fragment

# Fixed 128-bit UUIDs for the mesh service + frame characteristic.
MESH_SERVICE_UUID = "f0000a01-0451-4000-b000-6d6573680000"
MESH_FRAME_UUID = "f0000a02-0451-4000-b000-6d6573680000"

__all__ = ["MESH_SERVICE_UUID", "MESH_FRAME_UUID", "Reassembler", "fragment", "DEFAULT_CHUNK"]
