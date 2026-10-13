"""Headless BLE mesh on Bumble's emulated controller + link layer.

``EmulatedMesh`` spins up N virtual devices on one in-process ``LocalLink``, mounts the real mesh
GATT service (``messenger.transport.ble``) on each, and wires arbitrary topologies by opening real
GATT connections. Each device drives a real ``MeshRouter``; frames travel as genuine GATT writes
(central -> peripheral) and notifications (peripheral -> central), fragmented to the ATT MTU and
reassembled per link. No radios, no phones — this runs in CI.

Role convention per undirected edge (i, j): the lower index is the central (writes), the higher is
the peripheral (notifies back). A node can hold several connections in either role.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Set, Tuple

from bumble.controller import Controller
from bumble.device import Connection, Device, Peer
from bumble.gatt import Characteristic, CharacteristicValue, Service
from bumble.hci import Address
from bumble.host import Host
from bumble.link import LocalLink
from bumble.testing.test_utils import async_barrier
from bumble.transport.common import AsyncPipeSink

from messenger.transport.ble import MESH_FRAME_UUID, MESH_SERVICE_UUID, Reassembler, fragment
from messenger.transport.router import MeshRouter


class EmulatedMesh:
    def __init__(self, n: int, *, ttl: int = 7):
        if n > 10:
            raise ValueError("this harness names up to 10 virtual devices")
        self.n = n
        self.link = LocalLink()
        addresses = [":".join([f"F{i}"] * 6) for i in range(n)]
        self.controllers = [
            Controller(f"C{i}", link=self.link, public_address=addresses[i]) for i in range(n)
        ]
        self.devices = [
            Device(address=Address(addresses[i]),
                   host=Host(self.controllers[i], AsyncPipeSink(self.controllers[i])))
            for i in range(n)
        ]
        self.routers = [MeshRouter(i, ttl=ttl) for i in range(n)]
        self.chars: List[Characteristic] = []

        self._tasks: Set[asyncio.Task] = set()
        self._reasm: Dict[Tuple[int, int], Reassembler] = {}   # (node, neighbor) -> reassembler
        self._central_char: Dict[Tuple[int, int], object] = {}  # (central, periph) -> char proxy
        self._periph_conn: Dict[Tuple[int, int], Connection] = {}  # (periph, central) -> connection
        self._incoming: List[Dict[Connection, int]] = [dict() for _ in range(n)]  # periph: conn->central
        self.edges: List[Tuple[int, int]] = []

        for i in range(n):
            self._install_service(i)

    # --- setup ---------------------------------------------------------------
    def _install_service(self, i: int) -> None:
        def on_write(connection, value, i=i):
            central = self._incoming[i].get(connection)
            if central is not None:
                self._reasm[(i, central)].feed(bytes(value))

        char = Characteristic(
            MESH_FRAME_UUID,
            Characteristic.Properties.WRITE
            | Characteristic.Properties.WRITE_WITHOUT_RESPONSE
            | Characteristic.Properties.NOTIFY,
            Characteristic.WRITEABLE,
            CharacteristicValue(write=on_write),
        )
        self.devices[i].add_service(Service(MESH_SERVICE_UUID, [char]))
        self.chars.append(char)

    async def start(self) -> None:
        for dev in self.devices:
            await dev.power_on()

    async def connect(self, a: int, b: int) -> None:
        i, j = min(a, b), max(a, b)  # i central, j peripheral
        central_dev, periph_dev = self.devices[i], self.devices[j]

        conn_future = asyncio.get_running_loop().create_future()
        periph_dev.once(periph_dev.EVENT_CONNECTION, conn_future.set_result)
        await periph_dev.start_advertising(advertising_interval_min=1.0)
        central_conn = await central_dev.connect(periph_dev.random_address)
        periph_conn = await conn_future
        await periph_dev.stop_advertising()

        # peripheral j: route writes from central i, and send to i via notify
        self._incoming[j][periph_conn] = i
        self._periph_conn[(j, i)] = periph_conn
        self._reasm[(j, i)] = Reassembler(
            lambda msg, j=j, i=i: self.routers[j].on_frame(msg, from_id=i)
        )
        self.routers[j].connect(i, self._notify_sender(j, i))

        # central i: discover j's frame characteristic, subscribe for notifications, send via write
        self._reasm[(i, j)] = Reassembler(
            lambda msg, i=i, j=j: self.routers[i].on_frame(msg, from_id=j)
        )
        peer = Peer(central_conn)
        await peer.discover_all()
        char = peer.get_characteristics_by_uuid(MESH_FRAME_UUID)[0]
        await char.subscribe(lambda value, i=i, j=j: self._reasm[(i, j)].feed(bytes(value)))
        self._central_char[(i, j)] = char
        self.routers[i].connect(j, self._write_sender(i, j))

        self.edges.append((i, j))

    # --- topologies ----------------------------------------------------------
    async def line(self) -> None:
        for k in range(self.n - 1):
            await self.connect(k, k + 1)

    async def star(self) -> None:
        for k in range(1, self.n):
            await self.connect(0, k)

    async def ring(self) -> None:
        for k in range(self.n):
            await self.connect(k, (k + 1) % self.n)

    # --- message flow --------------------------------------------------------
    def originate(self, i: int, payload: bytes) -> None:
        self.routers[i].originate(payload)

    def _write_sender(self, i: int, j: int):
        def send(data: bytes) -> None:
            self._spawn(self._write_frag(i, j, data))
        return send

    async def _write_frag(self, i: int, j: int, data: bytes) -> None:
        char = self._central_char[(i, j)]
        for chunk in fragment(data):
            await char.write_value(chunk, with_response=True)

    def _notify_sender(self, j: int, i: int):
        def send(data: bytes) -> None:
            self._spawn(self._notify_frag(j, i, data))
        return send

    async def _notify_frag(self, j: int, i: int, data: bytes) -> None:
        conn = self._periph_conn[(j, i)]
        char = self.chars[j]
        for chunk in fragment(data):
            await self.devices[j].notify_subscriber(conn, char, chunk)

    # --- scheduling ----------------------------------------------------------
    def _spawn(self, coro) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def settle(self, idle_rounds: int = 3) -> None:
        """Run the event loop until the flood is fully quiescent (no in-flight GATT ops)."""
        idle = 0
        while idle < idle_rounds:
            if self._tasks:
                await asyncio.gather(*list(self._tasks), return_exceptions=True)
                idle = 0
            else:
                idle += 1
            await async_barrier()

    def delivered(self, i: int) -> List[bytes]:
        return self.routers[i].delivered
