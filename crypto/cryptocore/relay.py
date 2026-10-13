"""An untrusted store-and-forward relay — the server side of the hybrid messenger.

The design (see ``../docs/02-crypto-identity.md``) keeps the server *honest-but-curious*: it
moves bytes between devices and keeps a key-transparency log, but it never holds message keys
and must not be able to read content. This module is that relay reduced to its Phase 1
essence: a set of per-recipient mailboxes that store and forward opaque blobs.

The relay routes by an opaque handle (in the prototype, a device's identity fingerprint hex)
and treats every payload as bytes it cannot interpret. A 1:1 message is posted to one mailbox;
a group message is *fanned out* — the same ciphertext copied into each member's mailbox — so
the relay performs delivery without ever learning the plaintext. Everything confidential was
sealed by the Noise session (``handshake`` / ``ratchet``) or the MLS epoch key (``mls``)
before it ever reached here. The relay deliberately has no field capable of holding key
material; ``peek`` and ``stored_payloads`` expose the entirety of what it can observe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass
class RelayMessage:
    """One opaque item in transit. ``payload`` is ciphertext the relay never interprets."""
    seq: int
    recipient: str
    payload: bytes
    sender: Optional[str] = None


class UntrustedRelay:
    """In-process model of the blob relay: opaque bytes in, opaque bytes out, no keys."""

    def __init__(self) -> None:
        self._mailboxes: Dict[str, List[RelayMessage]] = {}
        self._seq = 0
        self.posted = 0
        self.delivered = 0

    def post(self, recipient: str, payload: bytes, sender: Optional[str] = None) -> int:
        """Accept one opaque blob for ``recipient`` and return its relay sequence number."""
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError("relay transports opaque bytes only")
        self._seq += 1
        msg = RelayMessage(self._seq, recipient, bytes(payload), sender)
        self._mailboxes.setdefault(recipient, []).append(msg)
        self.posted += 1
        return msg.seq

    def fanout(self, recipients: Iterable[str], payload: bytes,
               sender: Optional[str] = None) -> List[int]:
        """Deliver one group ciphertext to many mailboxes (server-side fanout)."""
        return [self.post(r, payload, sender) for r in recipients]

    def deliver(self, recipient: str) -> List[RelayMessage]:
        """Pop and return everything queued for ``recipient`` (store-and-forward drain)."""
        msgs = self._mailboxes.pop(recipient, [])
        self.delivered += len(msgs)
        return msgs

    def peek(self, recipient: str) -> List[RelayMessage]:
        """Honest-but-curious view of a mailbox: exactly what the relay can see (bytes only)."""
        return list(self._mailboxes.get(recipient, []))

    def pending(self, recipient: Optional[str] = None) -> int:
        if recipient is not None:
            return len(self._mailboxes.get(recipient, []))
        return sum(len(q) for q in self._mailboxes.values())

    def stored_payloads(self) -> List[bytes]:
        """Every blob currently held — the whole of what a curious relay could ever leak."""
        return [m.payload for q in self._mailboxes.values() for m in q]
