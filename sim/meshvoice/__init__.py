"""meshvoice — discrete-event simulator for Lyra voice over a Bluetooth LE mesh.

Phase 0 de-risking tool for the hybrid internet+Bluetooth messenger. It models the
riskiest claim in the product — interactive voice calls carried over a multi-hop BLE
mesh under concurrent load — so the routing/codec design rests on measured numbers
rather than assumptions. Pure standard-library Python (numpy optional, not required).
"""

from .codec import CodecProfile, LYRA_V1_3000, LYRA_V2_3200, LYRA_V2_6000, LYRA_V2_9200, PROFILES, by_name
from .network import Graph, Link, LinkParams, line, ring, star, grid, random_geometric
from .routing import shortest_path, lowest_latency_path
from .simulator import Call, PacketFate, SimParams, Simulator, SimResult
from .metrics import percentile, summarize, CallSummary, AggregateSummary

__all__ = [
    "CodecProfile", "LYRA_V1_3000", "LYRA_V2_3200", "LYRA_V2_6000", "LYRA_V2_9200",
    "PROFILES", "by_name",
    "Graph", "Link", "LinkParams", "line", "ring", "star", "grid", "random_geometric",
    "shortest_path", "lowest_latency_path",
    "Call", "PacketFate", "SimParams", "Simulator", "SimResult",
    "percentile", "summarize", "CallSummary", "AggregateSummary",
]
