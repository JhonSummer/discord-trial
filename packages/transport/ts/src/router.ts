// MeshRouter: flood routing with TTL, content-addressed dedup, and store-and-forward.
//
// Faithful port of the Python reference (packages/transport/python/.../router.py). Transport-
// agnostic on purpose: a "link" to a neighbor is just a `send(data)` callback — a direct call in
// tests, a GATT write over BLE, a socket write over the internet. Dedup by `Frame.msgId` (a hash of
// the payload) makes flooding loop-safe on cyclic graphs. The exact routing logic the Bumble
// emulation suite exercises on an emulated BLE stack is what the phone runs on real radios.
import { bytesToHex } from '@noble/hashes/utils';

import { DEFAULT_TTL, Frame } from '@messenger/protocol';

export type NodeId = string | number;
export type Send = (data: Uint8Array) => void;

export class MeshRouter {
  readonly delivered: Uint8Array[] = []; // payloads handed to the local app
  onDeliver: ((payload: Uint8Array) => void) | null = null;
  forwarded = 0; // stat: frames pushed onto links

  private readonly defaultTtl: number;
  private readonly seenCap: number;
  private readonly seen = new Map<string, true>(); // insertion-ordered -> LRU
  private readonly links = new Map<NodeId, Send>();
  private readonly online = new Map<NodeId, boolean>();
  private readonly store = new Map<NodeId, Uint8Array[]>();

  constructor(public readonly nodeId: NodeId, options: { ttl?: number; seenCap?: number } = {}) {
    this.defaultTtl = options.ttl ?? DEFAULT_TTL;
    this.seenCap = options.seenCap ?? 8192;
  }

  connect(neighborId: NodeId, send: Send, online = true): void {
    this.links.set(neighborId, send);
    this.online.set(neighborId, online);
    if (online) this.flush(neighborId);
  }

  setOnline(neighborId: NodeId, online: boolean): void {
    const was = this.online.get(neighborId) ?? false;
    this.online.set(neighborId, online);
    if (online && !was) this.flush(neighborId);
  }

  get neighbors(): NodeId[] {
    return [...this.links.keys()];
  }

  originate(payload: Uint8Array): Frame {
    const frame = new Frame(this.defaultTtl, payload);
    this.remember(frame.msgId); // record our own id so the echo doesn't loop back in
    this.flood(frame, null);
    return frame;
  }

  onFrame(data: Uint8Array, fromId: NodeId | null = null): void {
    const frame = Frame.fromBytes(data);
    if (!this.remember(frame.msgId)) return; // already seen -> drop (loop/duplicate guard)
    this.deliver(frame.payload);
    const next = frame.hop();
    if (next.alive) this.flood(next, fromId);
  }

  // Low-level dedup record; exposed (like the Python reference) so the LRU bound is testable.
  remember(msgId: Uint8Array): boolean {
    const key = bytesToHex(msgId);
    if (this.seen.has(key)) {
      this.seen.delete(key);
      this.seen.set(key, true); // move to most-recent
      return false;
    }
    this.seen.set(key, true);
    if (this.seen.size > this.seenCap) {
      const oldest = this.seen.keys().next().value as string;
      this.seen.delete(oldest); // evict oldest
    }
    return true;
  }

  get seenSize(): number {
    return this.seen.size;
  }

  private deliver(payload: Uint8Array): void {
    this.delivered.push(payload);
    if (this.onDeliver !== null) this.onDeliver(payload);
  }

  private flood(frame: Frame, exclude: NodeId | null): void {
    const data = frame.toBytes();
    for (const nid of this.links.keys()) {
      if (nid !== exclude) this.sendTo(nid, data);
    }
  }

  private sendTo(neighborId: NodeId, data: Uint8Array): void {
    if (this.online.get(neighborId) ?? false) {
      this.forwarded += 1;
      (this.links.get(neighborId) as Send)(data);
    } else {
      const queued = this.store.get(neighborId) ?? [];
      queued.push(data); // store-and-forward until the neighbor returns
      this.store.set(neighborId, queued);
    }
  }

  private flush(neighborId: NodeId): void {
    const queued = this.store.get(neighborId) ?? [];
    this.store.delete(neighborId);
    for (const data of queued) {
      this.forwarded += 1;
      (this.links.get(neighborId) as Send)(data);
    }
  }
}
