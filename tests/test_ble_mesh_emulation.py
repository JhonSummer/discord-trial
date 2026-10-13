"""CI-style BLE mesh tests driven headless on Bumble's emulated controller + link layer.

Every frame here travels as a real GATT write (central -> peripheral) or notification
(peripheral -> central), fragmented to the ATT MTU and reassembled per link. No radios, no phones.
This is the "it actually works on a BLE stack" verification the project is built around.
"""

import asyncio
import os

from harness import EmulatedMesh


def run(coro):
    return asyncio.run(coro)


def test_line_multihop_delivery():
    async def scenario():
        m = EmulatedMesh(4)
        await m.start()
        await m.line()  # 0-1-2-3
        m.originate(0, b"hello-mesh")
        await m.settle()
        return [m.delivered(i) for i in range(4)]

    d = run(scenario())
    assert d[0] == []  # originator does not self-deliver
    assert d[1] == d[2] == d[3] == [b"hello-mesh"]


def test_star_fanout_leaf_to_leaves():
    async def scenario():
        m = EmulatedMesh(5)
        await m.start()
        await m.star()  # 0 is the hub
        m.originate(2, b"hi")  # a leaf speaks
        await m.settle()
        return [m.delivered(i) for i in range(5)]

    d = run(scenario())
    assert d[2] == []            # originating leaf
    assert d[0] == [b"hi"]       # hub relays
    assert d[1] == d[3] == d[4] == [b"hi"]  # reaches the other leaves via the hub


def test_ring_is_loop_safe_and_delivers_once():
    async def scenario():
        m = EmulatedMesh(4)
        await m.start()
        await m.ring()  # 0-1-2-3-0, two paths to every node
        m.originate(0, b"once")
        await m.settle()
        return [m.delivered(i) for i in range(4)]

    d = run(scenario())
    assert d[0] == []
    assert d[1] == d[2] == d[3] == [b"once"]  # dedup kept it to one despite the cycle


def test_large_payload_fragments_and_reassembles_across_hops():
    payload = os.urandom(1024)  # ~52 GATT chunks at the 20-byte minimum-MTU size

    async def scenario():
        m = EmulatedMesh(3)
        await m.start()
        await m.line()
        m.originate(0, payload)
        await m.settle()
        return [m.delivered(i) for i in (1, 2)]

    assert run(scenario()) == [[payload], [payload]]


def test_ttl_limits_reach():
    async def scenario():
        m = EmulatedMesh(4, ttl=2)
        await m.start()
        await m.line()
        m.originate(0, b"short")
        await m.settle()
        return [m.delivered(i) for i in range(4)]

    d = run(scenario())
    assert d[1] == [b"short"]  # 1 hop
    assert d[2] == [b"short"]  # 2 hops
    assert d[3] == []          # 3 hops: dropped once the TTL budget runs out


def test_duplicate_origination_is_deduped():
    async def scenario():
        m = EmulatedMesh(3)
        await m.start()
        await m.line()
        m.originate(0, b"dup")
        m.originate(0, b"dup")  # same content -> same msg_id
        await m.settle()
        return [m.delivered(i) for i in (1, 2)]

    # identical payload is one logical message; each node delivers it once
    assert run(scenario()) == [[b"dup"], [b"dup"]]
