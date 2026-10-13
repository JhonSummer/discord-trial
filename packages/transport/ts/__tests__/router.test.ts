import { utf8ToBytes } from '@noble/hashes/utils';

import { MeshRouter } from '../src';

const texts = (r: MeshRouter) => r.delivered.map((d) => new TextDecoder().decode(d));

function wire(a: MeshRouter, b: MeshRouter): void {
  a.connect(b.nodeId, (data) => b.onFrame(data, a.nodeId));
  b.connect(a.nodeId, (data) => a.onFrame(data, b.nodeId));
}

function chain(...routers: MeshRouter[]): void {
  for (let i = 0; i + 1 < routers.length; i++) wire(routers[i], routers[i + 1]);
}

test('line multi-hop delivery (originator does not self-deliver)', () => {
  const [a, b, c, d] = ['A', 'B', 'C', 'D'].map((n) => new MeshRouter(n));
  chain(a, b, c, d);
  a.originate(utf8ToBytes('ping'));
  for (const r of [b, c, d]) expect(texts(r)).toEqual(['ping']);
  expect(texts(a)).toEqual([]);
});

test('star fan-out from a leaf reaches the hub and every other leaf', () => {
  const hub = new MeshRouter('H');
  const leaves = [0, 1, 2, 3].map((i) => new MeshRouter(`L${i}`));
  for (const leaf of leaves) wire(hub, leaf);
  leaves[0].originate(utf8ToBytes('hello'));
  expect(texts(hub)).toEqual(['hello']);
  for (const leaf of leaves.slice(1)) expect(texts(leaf)).toEqual(['hello']);
  expect(texts(leaves[0])).toEqual([]);
});

test('cyclic graph delivers exactly once (loop-safe dedup)', () => {
  const [a, b, c] = ['A', 'B', 'C'].map((n) => new MeshRouter(n));
  wire(a, b);
  wire(b, c);
  wire(c, a); // triangle: a frame can arrive by two paths
  a.originate(utf8ToBytes('once'));
  expect(texts(b)).toEqual(['once']);
  expect(texts(c)).toEqual(['once']);
});

test('TTL limits reach', () => {
  const [a, b, c, d] = ['A', 'B', 'C', 'D'].map((n) => new MeshRouter(n, { ttl: 2 }));
  chain(a, b, c, d);
  a.originate(utf8ToBytes('short'));
  expect(texts(b)).toEqual(['short']); // 1 hop
  expect(texts(c)).toEqual(['short']); // 2 hops
  expect(texts(d)).toEqual([]); // 3 hops: beyond the TTL budget
});

test('store-and-forward holds a frame until the link returns', () => {
  const a = new MeshRouter('A');
  const b = new MeshRouter('B');
  wire(a, b);
  a.setOnline('B', false); // link to B is down
  a.originate(utf8ToBytes('later'));
  expect(texts(b)).toEqual([]); // queued, not lost
  a.setOnline('B', true); // B comes back
  expect(texts(b)).toEqual(['later']);
});

test('dedup cache is bounded (LRU eviction)', () => {
  const r = new MeshRouter('R', { seenCap: 4 });
  for (let i = 0; i < 10; i++) r.remember(Uint8Array.of(i));
  expect(r.seenSize).toBe(4);
});
