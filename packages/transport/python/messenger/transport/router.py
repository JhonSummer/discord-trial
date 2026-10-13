"""MeshRouter: flood routing with TTL, content-addressed dedup, and store-and-forward.

Transport-agnostic on purpose. A "link" to a neighbor is just a ``send(data: bytes)`` callable:
in tests it calls the peer's ``on_frame`` directly; over Bluetooth it writes to a GATT
characteristic; over the internet it writes to a socket. The exact same routing logic is what
the emulation suite exercises on Bumble's BLE stack and what the phone runs on real radios.

Dedup is by ``Frame.msg_id`` (a hash of the payload), which makes flooding loop-safe on cyclic
graphs: a frame already seen is never re-delivered or re-forwarded.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from typing import Callable, Dict, List, Optional

from messenger.protocol.frame import DEFAULT_TTL, Frame

Send = Callable[[bytes], None]


class MeshRouter:
    def __init__(self, node_id, *, ttl: int = DEFAULT_TTL, seen_cap: int = 8192):
        self.node_id = node_id
        self.default_ttl = ttl
        self.seen_cap = seen_cap
        self._seen: "OrderedDict[bytes, None]" = OrderedDict()
        self._links: Dict[object, Send] = {}
        self._online: Dict[object, bool] = {}
        self._store: Dict[object, List[bytes]] = defaultdict(list)
        self.delivered: List[bytes] = []            # payloads handed to the local app
        self.on_deliver: Optional[Callable[[bytes], None]] = None
        self.forwarded = 0                          # stat: frames pushed onto links

    # --- neighbor management -------------------------------------------------
    def connect(self, neighbor_id, send: Send, *, online: bool = True) -> None:
        self._links[neighbor_id] = send
        self._online[neighbor_id] = online
        if online:
            self._flush(neighbor_id)

    def set_online(self, neighbor_id, online: bool) -> None:
        was = self._online.get(neighbor_id, False)
        self._online[neighbor_id] = online
        if online and not was:
            self._flush(neighbor_id)

    @property
    def neighbors(self) -> List[object]:
        return list(self._links)

    # --- message flow --------------------------------------------------------
    def originate(self, payload: bytes) -> Frame:
        """This node creates a new message and floods it to the mesh."""
        frame = Frame(self.default_ttl, payload)
        self._remember(frame.msg_id)  # record our own id so the echo doesn't loop back in
        self._flood(frame, exclude=None)
        return frame

    def on_frame(self, data: bytes, from_id=None) -> None:
        """A frame arrived from ``from_id``. Dedup, deliver locally, then relay if TTL allows."""
        frame = Frame.from_bytes(data)
        if not self._remember(frame.msg_id):
            return  # already seen -> drop (loop/duplicate guard)
        self._deliver(frame.payload)
        nxt = frame.hop()
        if nxt.alive:
            self._flood(nxt, exclude=from_id)

    # --- internals -----------------------------------------------------------
    def _remember(self, msg_id: bytes) -> bool:
        if msg_id in self._seen:
            self._seen.move_to_end(msg_id)
            return False
        self._seen[msg_id] = None
        if len(self._seen) > self.seen_cap:
            self._seen.popitem(last=False)  # evict oldest
        return True

    def _deliver(self, payload: bytes) -> None:
        self.delivered.append(payload)
        if self.on_deliver is not None:
            self.on_deliver(payload)

    def _flood(self, frame: Frame, exclude) -> None:
        data = frame.to_bytes()
        for nid in self._links:
            if nid != exclude:
                self._send_to(nid, data)

    def _send_to(self, neighbor_id, data: bytes) -> None:
        if self._online.get(neighbor_id, False):
            self.forwarded += 1
            self._links[neighbor_id](data)
        else:
            self._store[neighbor_id].append(data)  # store-and-forward until it returns

    def _flush(self, neighbor_id) -> None:
        queued = self._store.pop(neighbor_id, [])
        for data in queued:
            self.forwarded += 1
            self._links[neighbor_id](data)
