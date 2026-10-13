"""EventDAG: causal ordering + set-reconciliation over signed envelopes.

Every envelope names its causal parents (``prev``). The DAG produces a deterministic causal
order (topological, ties broken by the time-ordered Snowflake id) and supports anti-entropy:
``missing_for`` returns exactly the events a peer lacks, in an order safe to apply in sequence.
Two devices that diverged on a disconnected BLE island converge to identical history once they
exchange the difference in both directions.
"""

from __future__ import annotations

import heapq
from typing import Dict, Iterable, List, Set

from .envelope import Envelope


class EventDAG:
    def __init__(self) -> None:
        self.events: Dict[int, Envelope] = {}

    def __contains__(self, eid: int) -> bool:
        return eid in self.events

    def __len__(self) -> int:
        return len(self.events)

    def add(self, env: Envelope) -> bool:
        """Insert an event; returns True if it was new (idempotent on the eid)."""
        if env.eid in self.events:
            return False
        self.events[env.eid] = env
        return True

    def merge(self, envs: Iterable[Envelope]) -> int:
        return sum(1 for e in envs if self.add(e))

    def ids(self) -> Set[int]:
        return set(self.events)

    def heads(self) -> List[int]:
        """Current frontier: events that no present event names as a parent."""
        referenced: Set[int] = set()
        for e in self.events.values():
            referenced.update(p for p in e.prev if p in self.events)
        return sorted(eid for eid in self.events if eid not in referenced)

    def causal_order(self) -> List[Envelope]:
        """Topological order; among ready events the smallest (oldest) Snowflake id wins."""
        present = set(self.events)
        indeg = {eid: sum(1 for p in e.prev if p in present) for eid, e in self.events.items()}
        children: Dict[int, List[int]] = {eid: [] for eid in self.events}
        for eid, e in self.events.items():
            for p in e.prev:
                if p in present:
                    children[p].append(eid)

        ready = [eid for eid, d in indeg.items() if d == 0]
        heapq.heapify(ready)
        out: List[Envelope] = []
        while ready:
            eid = heapq.heappop(ready)
            out.append(self.events[eid])
            for c in children[eid]:
                indeg[c] -= 1
                if indeg[c] == 0:
                    heapq.heappush(ready, c)

        if len(out) < len(self.events):  # defensive: a cycle can't arise from honest causal links
            seen = {e.eid for e in out}
            out.extend(self.events[eid] for eid in sorted(self.events) if eid not in seen)
        return out

    def missing_for(self, their_ids: Set[int]) -> List[Envelope]:
        """Events I hold that the peer lacks, in causal order (parents before children)."""
        return [e for e in self.causal_order() if e.eid not in their_ids]
