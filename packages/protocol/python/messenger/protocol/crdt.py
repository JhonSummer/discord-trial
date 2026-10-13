"""Convergent replicated types for server-less metadata that must merge without coordination.

Used for things like a room's display name (LWW) or its membership / reactions (OR-Set). Merges
are commutative, associative, and idempotent, so peers that sync in any order and any number of
times reach the same state — the same guarantee the event DAG gives message history.
"""

from __future__ import annotations

from typing import Dict, Generic, Optional, Set, Tuple, TypeVar

T = TypeVar("T")


class LWWRegister(Generic[T]):
    """Last-writer-wins register. Concurrent writes with equal timestamps break the tie on the
    actor id, deterministically, so every replica picks the same winner."""

    def __init__(self) -> None:
        self.value: Optional[T] = None
        self._stamp: Tuple[int, bytes] = (-1, b"")

    def set(self, value: T, ts: int, actor: bytes) -> None:
        stamp = (ts, actor)
        if stamp > self._stamp:
            self.value, self._stamp = value, stamp

    def merge(self, other: "LWWRegister[T]") -> None:
        if other._stamp > self._stamp:
            self.value, self._stamp = other.value, other._stamp


class ORSet(Generic[T]):
    """Observed-remove set (add-wins). A remove only cancels the add-tags it has actually seen,
    so an add concurrent with a remove survives — the intuitive outcome for membership."""

    def __init__(self) -> None:
        self._adds: Dict[T, Set[bytes]] = {}
        self._removes: Dict[T, Set[bytes]] = {}

    def add(self, elem: T, tag: bytes) -> None:
        self._adds.setdefault(elem, set()).add(tag)

    def remove(self, elem: T) -> None:
        observed = self._adds.get(elem, set()) - self._removes.get(elem, set())
        if observed:
            self._removes.setdefault(elem, set()).update(observed)

    def __contains__(self, elem: T) -> bool:
        return bool(self._adds.get(elem, set()) - self._removes.get(elem, set()))

    def elements(self) -> Set[T]:
        return {e for e in self._adds if self._adds[e] - self._removes.get(e, set())}

    def merge(self, other: "ORSet[T]") -> None:
        for elem, tags in other._adds.items():
            self._adds.setdefault(elem, set()).update(tags)
        for elem, tags in other._removes.items():
            self._removes.setdefault(elem, set()).update(tags)
